param(
    [string]$BaseUrl = "https://bot-federation-production.up.railway.app",
    [Parameter(Mandatory = $true)]
    [string]$Token,
    [string]$OutputDir = ".\synced",
    [string]$TaskName = "BBF Railway Data Sync",
    [int]$IntervalMinutes = 60
)

$ErrorActionPreference = "Stop"

$syncScript = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "sync_railway_data.ps1")
$resolvedOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$($syncScript.Path)`"",
    "-BaseUrl", "`"$BaseUrl`"",
    "-Token", "`"$Token`"",
    "-OutputDir", "`"$resolvedOutputDir`""
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Sync BBF Railway Excel and backup zip to this PC." -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName"
Write-Host "Interval: every $IntervalMinutes minutes"
Write-Host "Output: $resolvedOutputDir"
