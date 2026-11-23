<#
.SYNOPSIS
  Start the Jarvis Telegram bot automatically when you log in (Windows Task Scheduler).

.DESCRIPTION
  Registers a per-user scheduled task named "JarvisTelegram". It runs `uv run jarvis --telegram`
  hidden, restarts the bot if it crashes, and keeps running on battery.
  It does not touch power settings. See "Keeping the laptop awake" in the README for that.

.EXAMPLE
  .\scripts\install-autostart.ps1            # install
  .\scripts\install-autostart.ps1 -Status    # show the task
  .\scripts\install-autostart.ps1 -Remove    # uninstall
#>
param(
    [switch]$Remove,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$TaskName = "JarvisTelegram"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ($Status) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) { Write-Host "Task not installed." }
    return
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed $TaskName."
    return
}

# The bot cannot run without its secrets, so fail early with a clear message.
$envFile = Join-Path $HOME ".jarvis\.env"
if (-not (Test-Path $envFile) -or -not (Select-String -Path $envFile -Pattern "^JARVIS_TELEGRAM_TOKEN=.+" -Quiet) `
        -or -not (Select-String -Path $envFile -Pattern "^JARVIS_TELEGRAM_USER_ID=\d+" -Quiet)) {
    throw "Set JARVIS_TELEGRAM_TOKEN and JARVIS_TELEGRAM_USER_ID in $envFile first (see README, Telegram)."
}

$uv = (Get-Command uv -ErrorAction Stop).Source
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$uv' run jarvis --telegram`"" `
    -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Jarvis Telegram bot (starts at logon, restarts on failure)" -Force | Out-Null
Write-Host "Installed $TaskName. It starts at your next login; start it now with: Start-ScheduledTask $TaskName"
