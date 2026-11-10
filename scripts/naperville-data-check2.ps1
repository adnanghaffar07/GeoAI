# Naperville focus, check 2 (read-only): every pavement-related request type, pothole requests per year and how
# many have a location, and what the Work Orders and Rainfall datasets hold.
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "naperville-data-check2.log"
"Naperville data check 2 $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
$base = "https://services1.arcgis.com/rXJ6QApc2sOtl1Pd/arcgis/rest/services"
function Q($url, $params) { Invoke-RestMethod ("$url/query?" + $params + "&f=json") -TimeoutSec 120 }
function Groups($url, $field, $where) {
  $stats = [uri]::EscapeDataString('[{"statisticType":"count","onStatisticField":"' + $field + '","outStatisticFieldName":"n"}]')
  (Q $url "where=$([uri]::EscapeDataString($where))&groupByFieldsForStatistics=$field&outStatistics=$stats&orderByFields=n%20DESC&resultRecordCount=2000").features
}
$words = "UPPER(DESCRIPTION) LIKE '%POTHOLE%' OR UPPER(DESCRIPTION) LIKE '%PAVEMENT%' OR UPPER(DESCRIPTION) LIKE '%ASPHALT%' OR UPPER(DESCRIPTION) LIKE '%PATCH%' OR UPPER(DESCRIPTION) LIKE '%STREET REPAIR%' OR UPPER(DESCRIPTION) LIKE '%ROAD%' OR UPPER(DESCRIPTION) LIKE '%CRACK%' OR UPPER(DESCRIPTION) LIKE '%CURB%' OR UPPER(DESCRIPTION) LIKE '%STREET%'"
foreach ($name in @("Service_Request", "Work_Orders_Data")) {
  Log ""; Log "=== $name ==="
  $url = "$base/$name/FeatureServer/0"
  try {
    $info = Invoke-RestMethod "$url`?f=json" -TimeoutSec 60
    Log ("FIELDS: " + (($info.fields | ForEach-Object { $_.name + ":" + $_.type.Replace('esriFieldType','') }) -join ", "))
    Log "ROWS: $((Q $url 'where=1%3D1&returnCountOnly=true').count)"
    $descField = ($info.fields | Where-Object { $_.name -match '^(DESCRIPTION|DESCRIPT|PROBLEM|WORKTYPE|WO_TYPE|TYPE|ACTIVITY|DESC)' } | Select-Object -First 1).name
    if (-not $descField) { $descField = ($info.fields | Where-Object { $_.type -eq 'esriFieldTypeString' -and $_.name -match 'desc|type|activity|problem|work' } | Select-Object -First 1).name }
    Log "TYPE FIELD: $descField"
    $where = $words.Replace("DESCRIPTION", $descField)
    Log "PAVEMENT-RELATED TYPES:"
    Groups $url $descField $where | ForEach-Object { Log ("    " + ($_.attributes | ConvertTo-Json -Compress)) }
    Log "ALL TYPES (count):"
    Groups $url $descField "1=1" | Select-Object -First 400 | ForEach-Object { Log ("    " + ($_.attributes | ConvertTo-Json -Compress)) }
    $sample = Q $url ("where=" + [uri]::EscapeDataString($where) + "&outFields=*&resultRecordCount=5&returnGeometry=true&outSR=4326")
    $sample.features | ForEach-Object { Log ("  SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress) + " GEOM: " + ($_.geometry | ConvertTo-Json -Compress)) }
  } catch { Log "ERROR: $($_.Exception.Message)" }
}
# Pothole requests per year and how many have a location
$url = "$base/Service_Request/FeatureServer/0"
try {
  Log ""; Log "=== Repair Pothole per year ==="
  foreach ($y in 2023..2026) {
    $w = [uri]::EscapeDataString("UPPER(DESCRIPTION) LIKE '%POTHOLE%' AND DATE_CREATED >= DATE '$y-01-01' AND DATE_CREATED < DATE '$($y+1)-01-01'")
    $wl = [uri]::EscapeDataString("UPPER(DESCRIPTION) LIKE '%POTHOLE%' AND LAT_DEGREE IS NOT NULL AND LAT_DEGREE <> 0 AND DATE_CREATED >= DATE '$y-01-01' AND DATE_CREATED < DATE '$($y+1)-01-01'")
    Log ("  $y : " + (Q $url "where=$w&returnCountOnly=true").count + " requests, " + (Q $url "where=$wl&returnCountOnly=true").count + " with a location")
  }
} catch { Log "ERROR: $($_.Exception.Message)" }
# Rainfall gauges
try {
  Log ""; Log "=== Rainfall ==="
  $r = Invoke-RestMethod "$base/Rainfall/FeatureServer?f=json" -TimeoutSec 60
  foreach ($l in @($r.layers) + @($r.tables)) {
    if (-not $l) { continue }
    $u = "$base/Rainfall/FeatureServer/$($l.id)"
    $i = Invoke-RestMethod "$u`?f=json" -TimeoutSec 60
    Log ("LAYER $($l.id) $($l.name): " + (($i.fields | ForEach-Object { $_.name + ":" + $_.type.Replace('esriFieldType','') }) -join ", "))
    Log "  ROWS: $((Q $u 'where=1%3D1&returnCountOnly=true').count)"
    (Q $u "where=1%3D1&outFields=*&resultRecordCount=2").features | ForEach-Object { Log ("  SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress)) }
  }
} catch { Log "ERROR: $($_.Exception.Message)" }
Log "Done. Send naperville-data-check2.log to Claude."
