# Downloads public SeeClickFix pothole reports for towns in the project counties into CSV files.
# Keeps only: id, created, acknowledged, closed, updated, status, type, lat, lng. No names, no text, no addresses.
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$out = Join-Path $PSScriptRoot 'seeclickfix-data'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out 'download.log'
function Say($s) { Write-Host $s; Add-Content -Path $log -Value $s }
Set-Content -Path $log -Value "Download $(Get-Date)"

# slug, county, min_lat, min_lng, max_lat, max_lng
$towns = @(
 @('lombard','DuPage',41.84,-88.04,41.90,-87.95),
 @('glen_ellyn','DuPage',41.85,-88.10,41.90,-88.03),
 @('oak_brook','DuPage',41.81,-87.98,41.87,-87.90),
 @('wheaton','DuPage',41.82,-88.14,41.89,-88.07),
 @('elk_grove_village','Cook',41.97,-88.04,42.02,-87.96),
 @('la_grange_park','Cook',41.81,-87.89,41.84,-87.85),
 @('schaumburg','Cook',42.00,-88.13,42.06,-88.03),
 @('evanston','Cook',42.01,-87.72,42.07,-87.66),
 @('geneva','Kane',41.86,-88.34,41.90,-88.28),
 @('joliet','Will',41.48,-88.20,41.58,-88.00),
 @('waukegan','Lake',42.32,-87.92,42.40,-87.80)
)

foreach ($t in $towns) {
  $rows = New-Object System.Collections.ArrayList
  $seen = @{}
  $page = 1
  while ($page -le 80) {
    $u = "https://seeclickfix.com/api/v2/issues?min_lat=$($t[2])&min_lng=$($t[3])&max_lat=$($t[4])&max_lng=$($t[5])&search=pothole&status=open,acknowledged,closed,archived&per_page=100&page=$page&sort=created_at&sort_direction=DESC"
    try { $r = Invoke-RestMethod -Uri $u -TimeoutSec 90 -UserAgent "GeoInfraLens-AI-research (contact: farhan, GeoInfraLens AI project)" } catch { Say "  $($t[0]) page $page failed: $($_.Exception.Message)"; break }
    if (-not $r.issues -or $r.issues.Count -eq 0) { break }
    foreach ($i in $r.issues) {
      if ($seen.ContainsKey([string]$i.id)) { continue }
      $seen[[string]$i.id] = 1
      $type = ''
      if ($i.request_type -and $i.request_type.title) { $type = [string]$i.request_type.title } else { $type = [string]$i.summary }
      # keep only rows that really are pothole-type
      if (($type + ' ' + [string]$i.summary) -notmatch '(?i)pot\s?hole') { continue }
      [void]$rows.Add([pscustomobject]@{
        id = $i.id; town = $t[0]; county = $t[1]
        created_at = $i.created_at; acknowledged_at = $i.acknowledged_at
        closed_at = $i.closed_at; updated_at = $i.updated_at
        status = $i.status; type = $type; lat = $i.lat; lng = $i.lng })
    }
    if (-not $r.metadata.pagination.next_page) { break }
    $page++; Start-Sleep -Milliseconds 3200
  }
  $file = Join-Path $out "$($t[0]).csv"
  $rows | Export-Csv -Path $file -NoTypeInformation -Encoding UTF8
  $closed = ($rows | Where-Object { $_.closed_at }).Count
  $ack = ($rows | Where-Object { $_.acknowledged_at }).Count
  Say ("{0}: {1} rows | with closed date: {2} | with acknowledged date: {3}" -f $t[0], $rows.Count, $closed, $ack)
}
# one combined file
Get-ChildItem $out -Filter *.csv | Where-Object { $_.Name -ne 'all_towns.csv' } | ForEach-Object { Import-Csv $_.FullName } | Export-Csv (Join-Path $out 'all_towns.csv') -NoTypeInformation -Encoding UTF8
Say "Done. Files are in: $out"
