$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$CloudflaredCandidates = @(
  "C:\Program Files (x86)\cloudflared\cloudflared.exe",
  "C:\Program Files\cloudflared\cloudflared.exe"
)
$Cloudflared = $CloudflaredCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if (-not $Cloudflared) {
  throw "cloudflared not found. Install Cloudflare.cloudflared with winget."
}

$UvicornLog = Join-Path $Root "uvicorn.log"
$UvicornErr = Join-Path $Root "uvicorn.err.log"
$TunnelLog = Join-Path $Root "cloudflared.log"
$TunnelErr = Join-Path $Root "cloudflared.err.log"
$PollingLog = Join-Path $Root "polling.log"
$PollingErr = Join-Path $Root "polling.err.log"

Remove-Item -LiteralPath $UvicornLog,$UvicornErr,$TunnelLog,$TunnelErr,$PollingLog,$PollingErr -ErrorAction SilentlyContinue

$children = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Stop-Children {
  foreach ($child in $children) {
    if ($child -and -not $child.HasExited) {
      Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
    }
  }
}

try {
  $api = Start-Process -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $UvicornLog `
    -RedirectStandardError $UvicornErr `
    -PassThru
  $children.Add($api)

  Start-Sleep -Seconds 4
  Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 10 | Out-Null

  $tunnel = Start-Process -FilePath $Cloudflared `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate") `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $TunnelLog `
    -RedirectStandardError $TunnelErr `
    -PassThru
  $children.Add($tunnel)

  $publicUrl = $null
  for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    $combined = ""
    if (Test-Path -LiteralPath $TunnelLog) { $combined += Get-Content -LiteralPath $TunnelLog -Raw }
    if (Test-Path -LiteralPath $TunnelErr) { $combined += Get-Content -LiteralPath $TunnelErr -Raw }
    $match = [regex]::Match($combined, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    if ($match.Success) {
      $publicUrl = $match.Value
      break
    }
  }

  if (-not $publicUrl) {
    throw "Could not get Cloudflare tunnel URL. See cloudflared.log and cloudflared.err.log."
  }

  Invoke-WebRequest -Uri "$publicUrl/health" -UseBasicParsing -TimeoutSec 20 | Out-Null

  $envPath = Join-Path $Root ".env"
  $envText = [System.IO.File]::ReadAllText($envPath, [System.Text.UTF8Encoding]::new($false))
  $envText = [regex]::Replace($envText, "(?m)^WEBAPP_URL=.*$", "WEBAPP_URL=$publicUrl")
  [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))

  & $Python (Join-Path $Root "scripts\set_menu_button.py")
  & $Python (Join-Path $Root "scripts\set_menu_button.py") 697068570

  $polling = Start-Process -FilePath $Python `
    -ArgumentList @("scripts\polling.py") `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $PollingLog `
    -RedirectStandardError $PollingErr `
    -PassThru
  $children.Add($polling)

  Write-Host ""
  Write-Host "MiniApp is live:" $publicUrl
  Write-Host "Telegram menu button updated. Keep this window open while testing."
  Write-Host "Press Ctrl+C to stop."
  Wait-Process -Id $api.Id
}
finally {
  Stop-Children
}
