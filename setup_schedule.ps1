# setup_schedule.ps1 - registers the Windows task that runs the summarizer.
# run_daily.bat calls this for you, so you normally never run it yourself.
#
# The task starts run.py in --scheduled mode:
#   - a couple of minutes after you log in (Wi-Fi needs a moment to connect)
#   - a minute after you unlock the laptop (e.g. after opening it from sleep)
#   - every hour while the laptop stays on
# run.py only sends a summary if the last one went out 20+ hours ago,
# so all these triggers still mean at most one email per 20 hours.
#
# Running this again is safe: it just updates the existing task.

$TaskName   = "Gmail AI Summarizer"
$ProjectDir = $PSScriptRoot
$User       = "$env:USERDOMAIN\$env:USERNAME"

# pythonw.exe is the windowless version of Python, so nothing pops up on screen.
$action = New-ScheduledTaskAction `
    -Execute (Join-Path $ProjectDir "venv\Scripts\pythonw.exe") `
    -Argument "`"$(Join-Path $ProjectDir 'run.py')`" --scheduled" `
    -WorkingDirectory $ProjectDir

# Trigger 1: when you log in.
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $User
$atLogon.Delay = "PT2M"

# Trigger 2: when you unlock the laptop.
$stateChangeClass = Get-CimClass -Namespace ROOT\Microsoft\Windows\TaskScheduler `
    -ClassName MSFT_TaskSessionStateChangeTrigger
$atUnlock = New-CimInstance -CimClass $stateChangeClass -ClientOnly
$atUnlock.StateChange = 8  # 8 means "session unlocked"
$atUnlock.UserId = $User
$atUnlock.Delay = "PT1M"

# Trigger 3: every hour, as a safety net while the laptop stays on.
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# Run as you, only while you're logged in, with normal (non-admin) rights.
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $atLogon, $atUnlock, $hourly `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' is set up."
