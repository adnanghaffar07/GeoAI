# County expansion (read-only). Looks for pothole / street-repair service requests in two cities:
#  - Aurora IL    (Kane, DuPage, Will and Kendall counties): ArcGIS Hub and ArcGIS Online
#  - Evanston IL  (Cook County): Socrata open data portal
# Nothing is downloaded to the database. Output: county-data-check.log (send it to Claude).
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "county-data-check.log"
"County data check $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
function Ms($v) { if ($v) { [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$v).ToString('yyyy-MM-dd') } }

# ---------- AURORA (Kane / DuPage / Will / Kendall) ----------
Log ""; Log "##### AURORA (counties: Kane, DuPage, Will, Kendall) #####"
$found = @{}
foreach ($q in @('Aurora 311', 'Aurora service requests', 'Aurora pothole', 'myAurora', 'Aurora street')) {
  try {
    $u = 'https://www.arcgis.com/sharing/rest/search?f=json&num=40&q=' + [uri]::EscapeDataString($q + ' AND type:"Feature Service"')
    $r = Invoke-RestMethod $u -TimeoutSec 60
    foreach ($i in $r.results) {
      if (($i.title + ' ' + $i.owner + ' ' + $i.snippet) -match 'Aurora' -and -not $found.ContainsKey($i.url)) {
        $found[$i.url] = $i
        Log ("ARCGIS ITEM: " + $i.title + " | owner " + $i.owner + " | " + $i.url + " | modified " + (Ms $i.modified))
      }
    }
  } catch { Log "SEARCH ERROR ($q): $($_.Exception.Message)" }
}
foreach ($hub in @('https://myaurora-311-cityofaurora.hub.arcgis.com')) {
  try {
    $page = Invoke-RestMethod ($hub + '/api/search/v1/collections/all/items?limit=100') -TimeoutSec 60
    foreach ($f in $page.features) {
      $p = $f.properties
      Log ("HUB ITEM: " + $p.title + " | type " + $p.type + " | " + $p.url)
      if ($p.url -and $p.type -match 'Feature' -and -not $found.ContainsKey($p.url)) { $found[$p.url] = $p }
    }
  } catch { Log "HUB ERROR ($hub): $($_.Exception.Message)" }
}
foreach ($url0 in $found.Keys) {
  $title = $found[$url0].title
  Log ""; Log "=== $title ==="
  try {
    $svc = $url0
    if ($svc -notmatch 'FeatureServer(/\d+)?$') { continue }
    $layers = @()
    if ($svc -match '/\d+$') { $layers = @($svc) }
    else { $meta = Invoke-RestMethod ($svc + '?f=json') -TimeoutSec 60; foreach ($l in $meta.layers) { $layers += ($svc + '/' + $l.id) } }
    foreach ($url in $layers) {
      $info = Invoke-RestMethod ($url + '?f=json') -TimeoutSec 60
      Log ("LAYER: " + $info.name + " | " + $url)
      Log ("FIELDS: " + (($info.fields | ForEach-Object { $_.name + ":" + $_.type.Replace('esriFieldType','') }) -join ", "))
      $c = Invoke-RestMethod ($url + '/query?where=1%3D1&returnCountOnly=true&f=json') -TimeoutSec 60
      Log "ROWS: $($c.count)"
      if ($c.count -gt 0) {
        $s = Invoke-RestMethod ($url + '/query?where=1%3D1&outFields=*&resultRecordCount=3&returnGeometry=true&outSR=4326&f=json') -TimeoutSec 60
        $s.features | ForEach-Object { Log ("  SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress) + " GEOM: " + ($_.geometry | ConvertTo-Json -Compress)) }
        foreach ($fld in $info.fields) {
          if ($fld.type -eq 'esriFieldTypeString' -and $fld.name -match 'type|categ|request|problem|issue|service|desc|subject|topic|status') {
            $st = '[{"statisticType":"count","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"n"}]'
            $g = Invoke-RestMethod ($url + '/query?where=1%3D1&groupByFieldsForStatistics=' + $fld.name + '&outStatistics=' + [uri]::EscapeDataString($st) + '&orderByFields=n%20DESC&resultRecordCount=40&f=json') -TimeoutSec 90
            Log "VALUES OF $($fld.name):"
            $g.features | Select-Object -First 40 | ForEach-Object { Log ("    " + ($_.attributes | ConvertTo-Json -Compress)) }
          }
          if ($fld.type -eq 'esriFieldTypeDate') {
            $st = '[{"statisticType":"min","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"a"},{"statisticType":"max","onStatisticField":"' + $fld.name + '","outStatisticFieldName":"b"}]'
            $d = Invoke-RestMethod ($url + '/query?where=1%3D1&outStatistics=' + [uri]::EscapeDataString($st) + '&f=json') -TimeoutSec 90
            $a = $d.features[0].attributes
            if ($a.a) { Log ("DATES $($fld.name): " + (Ms $a.a) + " to " + (Ms $a.b)) }
          }
        }
      }
    }
  } catch { Log "ERROR: $($_.Exception.Message)" }
}

# ---------- EVANSTON (Cook) ----------
Log ""; Log "##### EVANSTON (county: Cook) #####"
$dom = 'data.cityofevanston.org'
try {
  $cat = Invoke-RestMethod ('https://api.us.socrata.com/api/catalog/v1?domains=' + $dom + '&q=311&limit=20') -TimeoutSec 60
  foreach ($r in $cat.results) {
    $id = $r.resource.id
    Log ("DATASET: " + $r.resource.name + " | id " + $id + " | type " + $r.resource.type + " | updated " + $r.resource.updatedAt + " | licence " + $r.metadata.license)
  }
  foreach ($r in $cat.results) {
    if ($r.resource.type -ne 'dataset') { continue }
    $id = $r.resource.id
    Log ""; Log "=== $($r.resource.name) ($id) ==="
    try {
      $cols = @($r.resource.columns_name); $types = @($r.resource.columns_datatype)
      Log ("COLUMNS: " + (($cols | ForEach-Object -Begin { $i = 0 } -Process { $_ + ":" + $types[$i]; $i++ }) -join ", "))
      $n = Invoke-RestMethod ('https://' + $dom + '/resource/' + $id + '.json?$select=count(*)') -TimeoutSec 60
      Log ("ROWS: " + $n[0].count)
      $s = Invoke-RestMethod ('https://' + $dom + '/resource/' + $id + '.json?$limit=3') -TimeoutSec 60
      $s | ForEach-Object { Log ("  SAMPLE: " + ($_ | ConvertTo-Json -Compress -Depth 4)) }
      $i = 0
      foreach ($col in $r.resource.columns_field_name) {
        $t = $types[$i]; $i++
        if ($t -eq 'text' -and $col -match 'type|categ|request|problem|issue|service|desc|subject|topic|status') {
          $g = Invoke-RestMethod ('https://' + $dom + '/resource/' + $id + '.json?$select=' + $col + ',count(*)%20as%20n&$group=' + $col + '&$order=n%20DESC&$limit=40') -TimeoutSec 90
          Log "VALUES OF ${col}:"
          $g | ForEach-Object { Log ("    " + ($_ | ConvertTo-Json -Compress)) }
        }
        if ($t -match 'calendar_date|floating_timestamp|fixed_timestamp') {
          $d = Invoke-RestMethod ('https://' + $dom + '/resource/' + $id + '.json?$select=min(' + $col + ')%20as%20a,max(' + $col + ')%20as%20b') -TimeoutSec 90
          Log ("DATES ${col}: " + $d[0].a + " to " + $d[0].b)
        }
      }
      $p = Invoke-RestMethod ('https://' + $dom + '/resource/' + $id + '.json?$select=count(*)&$q=pothole') -TimeoutSec 90
      Log ("ROWS MENTIONING 'pothole' (any column): " + $p[0].count)
    } catch { Log "ERROR: $($_.Exception.Message)" }
  }
} catch { Log "CATALOG ERROR: $($_.Exception.Message)" }
Log ""; Log "Done. Send county-data-check.log to Claude."
