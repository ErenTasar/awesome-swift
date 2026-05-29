"""AIDF v0.3 reference implementation.

AI Document Format - a universal, content-agnostic *sidecar* container for
LLM-native access. The original file stays canonical; an AIDF file is a
derived, regenerable projection beside it that an LLM can load selectively,
traverse and reconcile.

This module provides the four pieces the spec calls for:

    parse(text)      -> Doc          lexer + object-model builder
    validate(doc)    -> [str]        the forcing-function checks (empty = valid)
    linearize(doc)   -> str          deterministic graph -> prompt flatten
    measure(atom)    -> int          model-neutral budget proxy (characters)

See SPEC.md for the normative description.
"""

import re

# --- Profiles ---------------------------------------------------------------
# Each profile picks the required-field matrix and whether conflicting claims
# sharing a `key` must be reconciled.
PROFILES = {
    "reference": {"required": ["src"],      "reconcile": True},
    "news":      {"required": ["src", "t"], "reconcile": True},
    "note":      {"required": [],           "reconcile": False},
    "narrative": {"required": [],           "reconcile": False},
}

# Typed graph edges. `next`/`prev` are pure sequence and are suppressed from
# linearization annotations as noise.
RELATIONS   = {"supports", "contradicts", "supersedes", "superseded_by",
               "refines", "next", "prev", "parent"}

# Edges that count as "reconciling" two atoms that assert about the same `key`.
RECONCILERS = {"contradicts", "supersedes", "superseded_by", "refines"}


class Atom:
    """The atomic unit of retrieval, linearization and addressing."""
    def __init__(self, aid):
        self.id = aid
        self.attrs = {}
        self.rels = {}


class Page:
    """One cohesive, independently loadable unit under a budget."""
    def __init__(self):
        self.attrs = {}
        self.atoms = []


class Doc:
    """A whole AIDF document: version, profile, inherited meta, and pages."""
    def __init__(self):
        self.version = None
        self.profile = None
        self.meta = {}
        self.pages = []


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def parse(text):
    """Parse AIDF source text into a Doc object model."""
    doc = Doc()
    cur_page = None
    cur_atom = None
    mode = None
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.strip().startswith("//"):
            continue
        s = raw.strip()
        if s.startswith("@aidf"):
            doc.version = s.split()[1]
            continue
        if s.startswith("@profile"):
            doc.profile = s.split()[1]
            continue
        if s == "@meta":
            mode = "meta"
            continue
        if s.startswith("@page"):
            cur_page = Page()
            doc.pages.append(cur_page)
            mode = "page"
            cur_atom = None
            m = re.search(r"budget=(\d+)", s)
            if m:
                cur_page.attrs["budget"] = int(m.group(1))
            continue
        if s.startswith("@atom"):
            if cur_page is None:
                cur_page = Page()
                doc.pages.append(cur_page)
            parts = s.split()
            aid = parts[1] if len(parts) > 1 else f"a{len(cur_page.atoms)}"
            cur_atom = Atom(aid)
            cur_page.atoms.append(cur_atom)
            mode = "atom"
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            k = k.strip()
            v = v.strip()
            # literal block: `key: |` -> capture deeper-indented lines verbatim
            if v == "|" and mode == "atom":
                ti = _indent(raw)
                buf = []
                while i < len(lines):
                    nl = lines[i]
                    if nl.strip() == "":
                        buf.append("")
                        i += 1
                        continue
                    if _indent(nl) <= ti:
                        break
                    buf.append(nl[ti + 2:] if len(nl) >= ti + 2 else nl.lstrip(" "))
                    i += 1
                # trim trailing blank lines
                while buf and buf[-1] == "":
                    buf.pop()
                cur_atom.attrs[k] = "\n".join(buf)
                continue
            if mode == "atom" and k in RELATIONS:
                cur_atom.rels.setdefault(k, []).extend(
                    x.strip() for x in v.split(",") if x.strip())
            elif mode == "meta":
                doc.meta[k] = v
            elif mode == "page" and cur_atom is None:
                cur_page.attrs[k] = v
            elif mode == "atom":
                cur_atom.attrs[k] = v
        elif mode == "atom" and "txt" in cur_atom.attrs:
            cur_atom.attrs["txt"] += " " + s   # folded continuation
    return doc


def resolve_inherited(doc, page, atom):
    """Effective attrs for an atom: meta <- page <- atom (later wins)."""
    merged = dict(doc.meta)
    merged.update({k: v for k, v in page.attrs.items() if k != "budget"})
    merged.update(atom.attrs)
    return merged


def measure(atom):
    """Model-neutral budget proxy: characters of the atom's body."""
    return len(atom.attrs.get("txt") or atom.attrs.get("sum") or "")


def validate(doc):
    """Return a list of validity errors; an empty list means the file is valid."""
    errs = []
    if doc.version is None:
        errs.append("missing @aidf version")
    if doc.profile not in PROFILES:
        errs.append(f"unknown/missing profile: {doc.profile}")
    prof = PROFILES.get(doc.profile, {"required": [], "reconcile": False})
    ids = set()
    claim_index = {}
    allp = [(p, a) for p in doc.pages for a in p.atoms]
    for p, a in allp:
        if a.id in ids:
            errs.append(f"duplicate id {a.id}")
        ids.add(a.id)
    for p, a in allp:
        inh = resolve_inherited(doc, p, a)
        if not (a.attrs.get("txt") or a.attrs.get("sum")):
            errs.append(f"{a.id}: empty")
        for k, v in list(a.attrs.items()) + list(inh.items()):
            if v == "?":
                errs.append(f"{a.id}: unfilled hole '{k}'")
        for rf in prof["required"]:
            if not inh.get(rf):
                errs.append(f"{a.id}: missing required '{rf}' ({doc.profile})")
        for rel, tgts in a.rels.items():
            for t in tgts:
                if t not in ids:
                    errs.append(f"{a.id}: dangling {rel}->{t}")
        if prof["reconcile"] and "key" in inh:
            claim_index.setdefault(inh["key"], []).append(a)
    for n, p in enumerate(doc.pages):
        b = p.attrs.get("budget")
        if b:
            total = sum(measure(a) for a in p.atoms)
            if total > b:
                if len(p.atoms) == 1:
                    if p.atoms[0].attrs.get("oversize") != "1":
                        errs.append(
                            f"page {n}: lone atom over budget needs oversize:1")
                else:
                    errs.append(
                        f"page {n}: over budget {total}>{b} "
                        f"({len(p.atoms)} atoms) split required")
    if prof["reconcile"]:
        for key, atoms in claim_index.items():
            if len(atoms) > 1 and not any(set(a.rels) & RECONCILERS for a in atoms):
                errs.append(
                    f"unreconciled claim '{key}' across {[a.id for a in atoms]}")
    return errs


def linearize(doc, resolution="full", drop_superseded=True, skim_chars=80):
    """Deterministically flatten the graph into a prompt string.

    resolution      "full" (txt, falls back to sum) or "sum" (skim).
    drop_superseded  omit atoms carrying a `superseded_by` edge (dead branches).
    skim_chars       truncation length when `sum` falls back to truncated `txt`.
    """
    out = [f"<aidf profile={doc.profile}>"]
    if doc.meta:
        out.append("meta: " + ", ".join(f"{k}={v}" for k, v in doc.meta.items()))
    for p in doc.pages:
        for a in p.atoms:
            if drop_superseded and "superseded_by" in a.rels:
                continue
            inh = resolve_inherited(doc, p, a)
            txt = a.attrs.get("txt")
            sm = a.attrs.get("sum")
            if resolution == "sum":
                body = sm or ((txt[:skim_chars] + "…")
                              if txt and len(txt) > skim_chars else txt) or ""
            else:
                body = txt or sm or ""
            tags = [f"{k}={inh[k]}" for k in ("conf", "src", "lang")
                    if inh.get(k) and inh.get(k) != doc.meta.get(k)]
            rels = [f"{r}->{','.join(t)}" for r, t in a.rels.items()
                    if r not in ("next", "prev")]
            ann = " ".join(tags + rels)
            out.append(f"  [{a.id}] {body}" + (f"  ({ann})" if ann else ""))
    out.append("</aidf>")
    return "\n".join(out)
