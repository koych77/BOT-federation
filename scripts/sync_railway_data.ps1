param(
    [string]$BaseUrl = $env:BBF_BASE_URL,
    [string]$Token = $env:ADMIN_EXPORT_TOKEN,
    [string]$OutputDir = ".\synced"
)

$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
    $BaseUrl = "https://bot-federation-production.up.railway.app"
}

if (-not $Token) {
    throw "Set ADMIN_EXPORT_TOKEN in this terminal or pass -Token."
}

$BaseUrl = $BaseUrl.TrimEnd("/")
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targetDir = Join-Path $OutputDir $timestamp
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$excelPath = Join-Path $targetDir "bfb_members.xlsx"
$backupPath = Join-Path $targetDir "bfb_backup.zip"

Invoke-WebRequest -Uri "$BaseUrl/admin/export.xlsx?token=$Token" -OutFile $excelPath -UseBasicParsing
Invoke-WebRequest -Uri "$BaseUrl/admin/backup.zip?token=$Token" -OutFile $backupPath -UseBasicParsing

Write-Host "Synced BBF data to $targetDir"
Write-Host "Excel:  $excelPath"
Write-Host "Backup: $backupPath"
