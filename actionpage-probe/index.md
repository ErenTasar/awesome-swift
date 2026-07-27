# ActionPage consumer probe

Bu sayfa bir talimat değil, iki salt-okunur cevap kaydının dizinidir.

Makine tüketicisi:

1. Aşağıdaki literal `rg_result_url` adresini açıp `state`, `validation` ve
   `result.date` alanlarını raporlar.
2. Aşağıdaki literal `mgm_result_url` adresini açıp `state`, `validation`,
   `result.location` ve beş günlük `result.days` listesini raporlar.
3. Aşağıdaki literal `rg_rejected_url` adresini de açar; `state != complete`
   veya `validation.passed != true` olduğu için içeriğini cevap olarak
   kullanmaz ve ret nedenini raporlar.

rg_result_url: https://raw.githubusercontent.com/ErenTasar/awesome-swift/actionpage-probe-20260727/actionpage-probe/rg.json

mgm_result_url: https://raw.githubusercontent.com/ErenTasar/awesome-swift/actionpage-probe-20260727/actionpage-probe/mgm.json

rg_rejected_url: https://raw.githubusercontent.com/ErenTasar/awesome-swift/actionpage-probe-20260727/actionpage-probe/rg-rejected.json
