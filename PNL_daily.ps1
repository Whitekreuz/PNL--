$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptPath

# Run daily data fetch and report generation
.\run_daily_job.bat
