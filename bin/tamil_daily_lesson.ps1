$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonBin = if ($env:TAMIL_PYTHON) { $env:TAMIL_PYTHON } else { "python" }

& $PythonBin (Join-Path $ScriptDir "tamil_daily_lesson.py")
