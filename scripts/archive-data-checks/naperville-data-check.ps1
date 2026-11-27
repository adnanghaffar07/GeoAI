# Naperville focus (read-only): what the City of Naperville's open data portal publishes, and whether its
# "Service Requests" dataset holds pothole reports (that would allow tested levels like Chicago).
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "naperville-data-check.log"
"Naperville data check $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
$hub = "https://open-data-naperville.hub.arcgis.com/api/search/v1/collections/all/items"
$services = @()
try {
  $start = 1
  do {
    $page = Invoke-RestMethod "$hub`?limit=100&startindex=$start" -TimeoutSec 90
    foreach ($f in $page.features) {
      $p = $f.properties
      Log ("DATASET: " + $p.title + " | type " + $p.type + " | " + $p.url + " | licence: " + (($p.licenseInfo -replace '<[^>]+>', '') -replace '\s+', ' '))
      if ($p.title -match 'Service Request|Pothole|Pavement|Street|Resurfac|Road') { $services += $p }
    }
    $start += 100
  } while ($page.features.Count -eq 100 -and $start -lt 600)
} catch { Log "CATALOG ERROR: $($_.Exception.Message)" }
foreach ($p in $services) {
  Log ""
  Log "=== $($p.title) ==="
  $url = $p.url
  if (-not $url) { continue }
  if ($url -notmatch '/\d+$') { $url = "$url/0" }
  try {
    $info = Invoke-RestMethod "$url`?f=json" -TimeoutSec 60
    Log ("FIELDS: " + (($info.fields | ForEach-Object { $_.name + ":" + $_.type.Replace('esriFieldType','') }) -join ", "))
    $count = Invoke-RestMethod "$url/query?where=1%3D1&returnCountOnly=true&f=json" -TimeoutSec 60
    Log "ROWS: $($count.count)"
    $sample = Invoke-RestMethod "$url/query?where=1%3D1&outFields=*&resultRecordCount=3&returnGeometry=true&outSR=4326&f=json" -TimeoutSec 60
    $sample.features | ForEach-Object { Log ("  SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress) + " GEOM: " + ($_.geometry | ConvertTo-Json -Compress)) }
    # most common values of every text field that looks like a request type
    foreach ($fld in $info.fields) {
      if ($fld.type -eq 'esriFieldTypeString' -and $fld.name -match 'type|category|request|problem|issue|service|desc|subject|topic') {
        $stats = '[{"statisticType":"count","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"n"}]'
        $g = Invoke-RestMethod "$url/query?where=1%3D1&groupByFieldsForStatistics=$($fld.name)&outStatistics=$([uri]::EscapeDataString($stats))&orderByFields=n%20DESC&resultRecordCount=60&f=json" -TimeoutSec 90
        Log "VALUES OF $($fld.name):"
        $g.features | Select-Object -First 60 | ForEach-Object { Log ("    " + ($_.attributes | ConvertTo-Json -Compress)) }
      }
      if ($fld.type -eq 'esriFieldTypeDate') {
        $stats = '[{"statisticType":"min","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"first"},{"statisticType":"max","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"last"}]'
        $d = Invoke-RestMethod "$url/query?where=1%3D1&outStatistics=$([uri]::EscapeDataString($stats))&f=json" -TimeoutSec 90
        $a = $d.features[0].attributes
        if ($a.first) { Log ("DATES $($fld.name): " + [DateTimeOffset]::FromUnixTimeMilliseconds($a.first).ToString('yyyy-MM-dd') + " to " + [DateTimeOffset]::FromUnixTimeMilliseconds($a.last).ToString('yyyy-MM-dd')) }
      }
    }
  } catch { Log "ERROR: $($_.Exception.Message)" }
}
Log "Done. Send naperville-data-check.log to Claude."
