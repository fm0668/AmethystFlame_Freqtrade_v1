param(
  [string]$TaskName = "FreqtradePipelineDaily",
  [string]$ProjectDir = "d:\AmethystFlame_Freqtrade_v1\v2.4_crosssection_coin_selection_strategy",
  [string]$PythonExe = "d:\AmethystFlame_Freqtrade_v1\.venv\Scripts\python.exe",
  [string]$ConfigPath = "d:\AmethystFlame_Freqtrade_v1\v2.4_crosssection_coin_selection_strategy\pipeline_config.template.json",
  [string]$StatePath = "d:\AmethystFlame_Freqtrade_v1\v2.4_crosssection_coin_selection_strategy\.runtime\pipeline_state.json",
  [string]$StartTime = "22:00"
)

$runner = Join-Path $ProjectDir "pipeline_runner.py"
$arg = "`"$runner`" --config `"$ConfigPath`" --state `"$StatePath`""
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arg
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force
Write-Output "Registered task: $TaskName at $StartTime local time"
