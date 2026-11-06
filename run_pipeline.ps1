# Scheduled entry point: run the pipeline from this folder and pass its exit code to Task Scheduler.
Set-Location $PSScriptRoot
python -m flightpipe run
exit $LASTEXITCODE
