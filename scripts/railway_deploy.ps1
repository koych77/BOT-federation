$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Railway = "C:\Users\koych\AppData\Roaming\npm\railway.cmd"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$EnvPath = Join-Path $Root ".env"
$ProjectName = "BOT-federation"
$ServiceName = "bfb-membership-bot"
$DatabaseServiceName = "Postgres"
$AdminTelegramId = "697068570"

if (-not (Test-Path -LiteralPath $Railway)) {
  throw "Railway CLI not found at $Railway"
}
if (-not (Test-Path -LiteralPath $EnvPath)) {
  throw ".env not found. Create it before deploy."
}
if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python venv not found at $Python"
}

Push-Location $Root
try {
  function Invoke-Railway {
    & $Railway @args
    if ($LASTEXITCODE -ne 0) {
      throw "Railway command failed: railway $($args -join ' ')"
    }
  }

  Invoke-Railway whoami | Out-Host

  Write-Host "Creating Railway project/service..."
  Invoke-Railway init --name $ProjectName | Out-Host
  Invoke-Railway add --service $ServiceName | Out-Host
  Invoke-Railway add --database postgres | Out-Host

  Write-Host "Generating Railway domain..."
  $domainOutput = Invoke-Railway domain --service $ServiceName --port 8000
  $domainOutput | Out-Host
  $domainMatch = [regex]::Match(($domainOutput -join "`n"), "https://[a-zA-Z0-9.-]+")
  if (-not $domainMatch.Success) {
    $domainMatch = [regex]::Match(($domainOutput -join "`n"), "[a-zA-Z0-9-]+\.up\.railway\.app")
  }
  if (-not $domainMatch.Success) {
    throw "Could not parse Railway domain from command output."
  }
  $publicUrl = $domainMatch.Value
  if (-not $publicUrl.StartsWith("https://")) {
    $publicUrl = "https://$publicUrl"
  }

  Write-Host "Railway URL: $publicUrl"

  $envText = [System.IO.File]::ReadAllText($EnvPath, [System.Text.UTF8Encoding]::new($false))
  $envLines = @{}
  foreach ($line in $envText -split "`r?`n") {
    if ($line.Trim() -eq "" -or $line.Trim().StartsWith("#") -or -not $line.Contains("=")) { continue }
    $parts = $line.Split("=", 2)
    $envLines[$parts[0]] = $parts[1]
  }

  $webhookSecret = $envLines["TELEGRAM_WEBHOOK_SECRET"]
  if (-not $webhookSecret) {
    $webhookSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
  }
  $exportToken = $envLines["ADMIN_EXPORT_TOKEN"]
  if (-not $exportToken) {
    $exportToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
  }
  $botToken = $envLines["BOT_TOKEN"]
  if (-not $botToken) {
    throw "BOT_TOKEN is missing in .env"
  }

  Write-Host "Setting Railway variables..."
  Invoke-Railway variable set --service $ServiceName --skip-deploys `
    "WEBAPP_URL=$publicUrl" `
    "PUBLIC_BASE_URL=$publicUrl" `
    'DATABASE_URL=${{Postgres.DATABASE_URL}}' `
    "ADMIN_TELEGRAM_IDS=$AdminTelegramId" `
    "MEMBERSHIP_YEAR=2026" `
    "ENTRY_FEE=45" `
    "MEMBERSHIP_FEE=90" `
    "CURRENCY=BYN" `
    "REQUIRE_TELEGRAM_AUTH=false" `
    "UPLOAD_DIR=./data/uploads" `
    "MAX_UPLOAD_MB=10" `
    "STORAGE_BACKEND=local" | Out-Host

  $botToken | & $Railway variable set --service $ServiceName --skip-deploys --stdin BOT_TOKEN | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Failed to set BOT_TOKEN" }
  $webhookSecret | & $Railway variable set --service $ServiceName --skip-deploys --stdin TELEGRAM_WEBHOOK_SECRET | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Failed to set TELEGRAM_WEBHOOK_SECRET" }
  $exportToken | & $Railway variable set --service $ServiceName --skip-deploys --stdin ADMIN_EXPORT_TOKEN | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Failed to set ADMIN_EXPORT_TOKEN" }

  Write-Host "Deploying..."
  Invoke-Railway up --service $ServiceName --detach | Out-Host

  Write-Host "Updating local .env and Telegram MiniApp button..."
  $envText = [regex]::Replace($envText, "(?m)^WEBAPP_URL=.*$", "WEBAPP_URL=$publicUrl")
  $envText = [regex]::Replace($envText, "(?m)^PUBLIC_BASE_URL=.*$", "PUBLIC_BASE_URL=$publicUrl")
  $envText = [regex]::Replace($envText, "(?m)^ADMIN_TELEGRAM_IDS=.*$", "ADMIN_TELEGRAM_IDS=$AdminTelegramId")
  [System.IO.File]::WriteAllText($EnvPath, $envText, [System.Text.UTF8Encoding]::new($false))

  & $Python (Join-Path $Root "scripts\set_menu_button.py") | Out-Host
  & $Python (Join-Path $Root "scripts\set_menu_button.py") $AdminTelegramId | Out-Host

  Write-Host ""
  Write-Host "DONE"
  Write-Host "MiniApp URL: $publicUrl"
  Write-Host "Health URL: $publicUrl/health"
  Write-Host "Excel export: $publicUrl/admin/export.xlsx?token=<ADMIN_EXPORT_TOKEN>"
}
finally {
  Pop-Location
}
