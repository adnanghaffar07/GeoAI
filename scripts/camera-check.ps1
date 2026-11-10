# Item 10 check (read-only): can the IDOT Gateway camera list be read for free, and what are its terms?
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "camera-check.log"
"Camera check $(Get-Date -Format s)" | Out-File $out -Encoding utf8
function Log($t) { $t | Out-File $out -Append -Encoding utf8; Write-Host $t }
try {
  $item = Invoke-RestMethod "https://www.arcgis.com/sharing/rest/content/items/8a885da23dfb46caaa1827ad920fb5b1?f=json" -TimeoutSec 60
  Log "OWNER: $($item.owner)"; Log "TITLE: $($item.title)"; Log "TYPE: $($item.type)"; Log "URL: $($item.url)"
  Log "LICENCE: $($item.licenseInfo)"; Log "CREDITS: $($item.accessInformation)"; Log "SUMMARY: $($item.snippet)"
  Log "DESCRIPTION: $($item.description)"
  $layer = $item.url
  if ($layer -notmatch '/\d+$') { $layer = "$layer/0" }
  $box = "-88.25,41.68,-88.08,41.82"   # Naperville
  $q = "$layer/query?where=1%3D1&geometry=$box&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=true&outSR=4326&f=json"
  $count = Invoke-RestMethod "$layer/query?where=1%3D1&returnCountOnly=true&f=json" -TimeoutSec 60
  Log "CAMERAS IN ILLINOIS: $($count.count)"
  $data = Invoke-RestMethod $q -TimeoutSec 60
  Log "CAMERAS IN NAPERVILLE BOX: $($data.features.Count)"
  $data.features | Select-Object -First 25 | ForEach-Object { Log ("  " + ($_.attributes | ConvertTo-Json -Compress)) }
  $first = $data.features | Where-Object { $_.attributes.SnapShot } | Select-Object -First 1
  if ($first) {
    $img = Invoke-WebRequest $first.attributes.SnapShot -TimeoutSec 60 -UseBasicParsing
    Log "SNAPSHOT: $($first.attributes.SnapShot)"
    Log "SNAPSHOT TYPE: $($img.Headers['Content-Type'])  BYTES: $($img.RawContentLength)"
    Log "SNAPSHOT CORS: $($img.Headers['Access-Control-Allow-Origin'])"
  }
} catch { Log "ERROR: $($_.Exception.Message)" }
Log "Done. Send camera-check.log to Claude."
