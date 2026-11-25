# Read-only: pages through SeeClickFix pothole reports per town, counts per year. No key needed.
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$log = Join-Path $PSScriptRoot 'county-data-check5.log'
function Say($s) { Write-Host $s; Add-Content -Path $log -Value $s }
Set-Content -Path $log -Value "SeeClickFix pothole check $(Get-Date)"

$towns = @(
 @('Lombard (DuPage)',        41.84,-88.04, 41.90,-87.95),
 @('Glen Ellyn (DuPage)',     41.85,-88.10, 41.90,-88.03),
 @('Oak Brook (DuPage)',      41.81,-87.98, 41.87,-87.90),
 @('Elk Grove Village (Cook)',41.97,-88.04, 42.02,-87.96),
 @('Geneva (Kane)',           41.86,-88.34, 41.90,-88.28),
 @('La Grange Park (Cook)',   41.81,-87.89, 41.84,-87.85),
 @('Wheaton (DuPage)',        41.82,-88.14, 41.89,-88.07),
 @('Bolingbrook (Will)',      41.67,-88.13, 41.72,-88.03),
 @('Joliet (Will)',           41.48,-88.20, 41.58,-88.00),
 @('Elgin (Kane)',            41.99,-88.36, 42.06,-88.22),
 @('Waukegan (Lake)',         42.32,-87.92, 42.40,-87.80),
 @('Schaumburg (Cook)',       42.00,-88.13, 42.06,-88.03),
 @('Oak Park (Cook)',         41.86,-87.82, 41.90,-87.77),
 @('Evanston (Cook)',         42.01,-87.72, 42.07,-87.66)
)

foreach ($t in $towns) {
  Say "=== $($t[0]) ==="
  $years = @{}; $total = 0; $withXY = 0; $types = @{}
  $page = 1; $max = 60
  while ($page -le $max) {
    $u = "https://seeclickfix.com/api/v2/issues?min_lat=$($t[1])&min_lng=$($t[2])&max_lat=$($t[3])&max_lng=$($t[4])&search=pothole&status=open,acknowledged,closed,archived&per_page=100&page=$page&sort=created_at&sort_direction=DESC"
    try { $r = Invoke-RestMethod -Uri $u -TimeoutSec 90 } catch { Say "  page $page failed: $($_.Exception.Message)"; break }
    if (-not $r.issues -or $r.issues.Count -eq 0) { break }
    foreach ($i in $r.issues) {
      $y = ([string]$i.created_at).Substring(0,4)
      $years[$y] = 1 + [int]$years[$y]; $total++
      if ($i.lat -and $i.lng) { $withXY++ }
      $types[[string]$i.summary] = 1 + [int]$types[[string]$i.summary]
    }
    if (-not $r.metadata.pagination.next_page) { break }
    $page++; Start-Sleep -Milliseconds 300
  }
  Say "  TOTAL: $total   with location: $withXY   pages read: $page"
  foreach ($k in ($years.Keys | Sort-Object)) { Say ("  {0}: {1}" -f $k, $years[$k]) }
  Say ("  types: " + (($types.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 5 | ForEach-Object { "$($_.Key) $($_.Value)" }) -join '; '))
}
Say "Done."
