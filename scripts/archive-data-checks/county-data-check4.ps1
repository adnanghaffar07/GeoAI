# Read-only check: SeeClickFix public pothole reports for towns in the 8 counties.
# Counts per town and per year. Needs no key. Writes nothing except the log.
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# name, min_lat, min_lng, max_lat, max_lng  (rough boxes around each town)
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

function Count-Issues($t, $after, $before) {
  $u = "https://seeclickfix.com/api/v2/issues?min_lat=$($t[1])&min_lng=$($t[2])&max_lat=$($t[3])&max_lng=$($t[4])" +
       "&search=pothole&status=open,acknowledged,closed,archived&per_page=1&after=$after&before=$before"
  try {
    $r = Invoke-RestMethod -Uri $u -TimeoutSec 60
    return [int]$r.metadata.pagination.entries
  } catch { return -1 }
}

foreach ($t in $towns) {
  Write-Host "=== $($t[0]) ==="
  $total = 0
  foreach ($y in 2016..2026) {
    $n = Count-Issues $t "$y-01-01T00:00:00Z" "$($y+1)-01-01T00:00:00Z"
    if ($n -ge 0) { $total += $n }
    Write-Host ("  {0}: {1}" -f $y, $n)
    Start-Sleep -Milliseconds 400
  }
  Write-Host "  TOTAL: $total"
  # sample of the newest 3 so we can see what the rows look like
  try {
    $u = "https://seeclickfix.com/api/v2/issues?min_lat=$($t[1])&min_lng=$($t[2])&max_lat=$($t[3])&max_lng=$($t[4])&search=pothole&status=open,acknowledged,closed,archived&per_page=3&sort=created_at&sort_direction=DESC"
    $r = Invoke-RestMethod -Uri $u -TimeoutSec 60
    foreach ($i in $r.issues) { Write-Host ("  sample: {0} | {1} | {2} | {3},{4}" -f $i.created_at, $i.status, $i.summary, $i.lat, $i.lng) }
  } catch { Write-Host "  sample failed" }
}
Write-Host "Done."
