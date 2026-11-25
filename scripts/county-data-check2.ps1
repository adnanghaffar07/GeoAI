# County expansion part 2 (read-only).
#  - Aurora IL (Kane/DuPage/Will/Kendall): pothole requests per year and month, and how many have a location.
#  - Evanston IL (Cook): finds the 311 service on ArcGIS (the city moved off Socrata) and logs the same facts.
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "county-data-check2.log"
"County data check 2 $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
function Ms($v) { if ($v) { [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$v).ToString('yyyy-MM-dd') } }

function Scan($url, $label) {
  Log ""; Log "=== $label ==="; Log "SERVICE: $url"
  $layers = @()
  if ($url -match '/\d+$') { $layers = @($url) }
  else { $m = Invoke-RestMethod ($url + '?f=json') -TimeoutSec 60; foreach ($l in $m.layers) { $layers += ($url + '/' + $l.id) } }
  foreach ($u in $layers) {
    $info = Invoke-RestMethod ($u + '?f=json') -TimeoutSec 60
    $c = Invoke-RestMethod ($u + '/query?where=1%3D1&returnCountOnly=true&f=json') -TimeoutSec 60
    Log ("LAYER: " + $info.name + " | " + $u + " | ROWS: " + $c.count)
    Log ("FIELDS: " + (($info.fields | ForEach-Object { $_.name + ":" + $_.type.Replace('esriFieldType','') }) -join ", "))
    if ($c.count -lt 1) { continue }
    $dateF = ($info.fields | Where-Object { $_.type -eq 'esriFieldTypeDate' -and $_.name -match 'creat|open|submit|report|request|date' } | Select-Object -First 1).name
    if (-not $dateF) { $dateF = ($info.fields | Where-Object { $_.type -eq 'esriFieldTypeDate' } | Select-Object -First 1).name }
    foreach ($fld in ($info.fields | Where-Object { $_.type -eq 'esriFieldTypeString' -and $_.name -match 'type|categ|request|problem|issue|service|desc|subject|topic' })) {
      $where = "UPPER(" + $fld.name + ") LIKE '%POTHOLE%' OR UPPER(" + $fld.name + ") LIKE '%POT HOLE%'"
      try {
        $n = Invoke-RestMethod ($u + '/query?returnCountOnly=true&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 90
        Log ("POTHOLE ROWS by field " + $fld.name + ": " + $n.count)
        if ($n.count -gt 0) {
          $rows = Invoke-RestMethod ($u + '/query?outFields=' + $dateF + '&returnGeometry=true&outSR=4326&resultRecordCount=2000&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 120
          $withGeom = 0; $byYear = @{}; $byMonth = @{}
          foreach ($f in $rows.features) {
            if ($f.geometry -and ($f.geometry.x -or $f.geometry.paths)) { $withGeom++ }
            $d = $f.attributes.$dateF
            if ($d) { $dt = [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$d); $byYear[$dt.Year] = 1 + [int]$byYear[$dt.Year]; $mk = $dt.ToString('MM'); $byMonth[$mk] = 1 + [int]$byMonth[$mk] }
          }
          Log ("  fetched " + $rows.features.Count + " | with location: " + $withGeom + " | date field: " + $dateF)
          Log ("  PER YEAR: " + (($byYear.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ", "))
          Log ("  PER CALENDAR MONTH (all years): " + (($byMonth.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ", "))
          $one = Invoke-RestMethod ($u + '/query?outFields=*&returnGeometry=true&outSR=4326&resultRecordCount=2&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 60
          $one.features | ForEach-Object { Log ("  SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress) + " GEOM: " + ($_.geometry | ConvertTo-Json -Compress)) }
        }
      } catch { Log "  ERROR on $($fld.name): $($_.Exception.Message)" }
    }
    if ($dateF) {
      $st = '[{"statisticType":"min","onStatisticField":"' + $dateF + '","outStatisticFieldName":"a"},{"statisticType":"max","onStatisticField":"' + $dateF + '","outStatisticFieldName":"b"}]'
      $d = Invoke-RestMethod ($u + '/query?where=1%3D1&outStatistics=' + [uri]::EscapeDataString($st) + '&f=json') -TimeoutSec 90
      $a = $d.features[0].attributes; Log ("DATES ${dateF}: " + (Ms $a.a) + " to " + (Ms $a.b))
    }
  }
}

Log "##### AURORA IL (Kane, DuPage, Will, Kendall) #####"
try { Scan 'https://services1.arcgis.com/79UxTxnBeBW8JHY4/arcgis/rest/services/OneView_ServiceRequests_Points_Mapped_view/FeatureServer/0' 'Aurora IL 311 Service Requests' } catch { Log "ERROR: $($_.Exception.Message)" }

Log ""; Log "##### EVANSTON IL (Cook) #####"
$urls = @{}
try {
  $it = Invoke-RestMethod 'https://www.arcgis.com/sharing/rest/content/items/46a3790e057a413e83103abf0e50a816?f=json' -TimeoutSec 60
  Log ("ITEM: " + $it.title + " | owner " + $it.owner + " | type " + $it.type + " | url " + $it.url + " | modified " + (Ms $it.modified) + " | licence: " + (($it.licenseInfo -replace '<[^>]+>', '') -replace '\s+', ' '))
  if ($it.url) { $urls[$it.url] = $it.title }
} catch { Log "ITEM ERROR: $($_.Exception.Message)" }
foreach ($q in @('Evanston 311', 'Evanston service requests', 'Evanston pothole', 'Evanston street')) {
  try {
    $r = Invoke-RestMethod ('https://www.arcgis.com/sharing/rest/search?f=json&num=30&q=' + [uri]::EscapeDataString($q + ' AND type:"Feature Service"')) -TimeoutSec 60
    foreach ($i in $r.results) {
      if (($i.title + ' ' + $i.owner + ' ' + $i.snippet + ' ' + $i.description) -match 'Evanston' -and ($i.title + $i.snippet) -match '311|request|pothole|street|pavement|resurfac|road') {
        if (-not $urls.ContainsKey($i.url)) { $urls[$i.url] = $i.title; Log ("FOUND: " + $i.title + " | owner " + $i.owner + " | " + $i.url + " | modified " + (Ms $i.modified)) }
      }
    }
  } catch { Log "SEARCH ERROR ($q): $($_.Exception.Message)" }
}
foreach ($k in $urls.Keys) { try { Scan $k $urls[$k] } catch { Log "ERROR ($($urls[$k])): $($_.Exception.Message)" } }
Log ""; Log "Done. Send county-data-check2.log to Claude."
