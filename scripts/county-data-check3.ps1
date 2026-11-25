# Evanston (Cook County) 311 data 2013-2022: how many pothole requests, per year, and how many have a location.
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "county-data-check3.log"
"County data check 3 $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
$u = 'https://services3.arcgis.com/RVAJnWJd9M0xRdYG/arcgis/rest/services/311_Service_Requests_(2013_to_2022)/FeatureServer/0/query'
$where = "UPPER(Title) LIKE '%POTHOLE%'"
try {
  $n = Invoke-RestMethod ($u + '?returnCountOnly=true&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 90
  Log "POTHOLE ROWS (Title): $($n.count)"
  $st = '[{"statisticType":"count","onStatisticField":"Title","outStatisticFieldName":"n"}]'
  $g = Invoke-RestMethod ($u + '?f=json&groupByFieldsForStatistics=Title&outStatistics=' + [uri]::EscapeDataString($st) + '&orderByFields=n%20DESC&where=' + [uri]::EscapeDataString("UPPER(Title) LIKE '%POTHOLE%' OR UPPER(Title) LIKE '%STREET%' OR UPPER(Title) LIKE '%PAVEMENT%' OR UPPER(Title) LIKE '%ROAD%' OR UPPER(Title) LIKE '%FLOOD%'")) -TimeoutSec 90
  Log "ROAD-RELATED TITLES:"; $g.features | ForEach-Object { Log ("    " + ($_.attributes | ConvertTo-Json -Compress)) }
  $rows = Invoke-RestMethod ($u + '?outFields=Date_Created,Latitude,Longitude,Status&returnGeometry=false&resultRecordCount=2000&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 120
  $byYear = @{}; $loc = 0
  foreach ($f in $rows.features) {
    $a = $f.attributes
    if ($a.Latitude -and $a.Longitude -and $a.Latitude -ne 0) { $loc++ }
    if ($a.Date_Created) { $y = [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$a.Date_Created).Year; $byYear[$y] = 1 + [int]$byYear[$y] }
  }
  Log ("fetched " + $rows.features.Count + " | with latitude/longitude: " + $loc)
  Log ("PER YEAR: " + (($byYear.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ", "))
  $s = Invoke-RestMethod ($u + '?outFields=*&returnGeometry=false&resultRecordCount=2&f=json&where=' + [uri]::EscapeDataString($where)) -TimeoutSec 60
  $s.features | ForEach-Object { Log ("SAMPLE: " + ($_.attributes | ConvertTo-Json -Compress)) }
} catch { Log "ERROR: $($_.Exception.Message)" }
Log "Done. Send county-data-check3.log to Claude."
