# Run Locust load testing for EcoScholar API and generate results
# Usage: .\run_locust_test.ps1

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "EcoScholar API Load Testing with Locust" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Flask is already running
$existingFlask = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*app.py*" }
if ($existingFlask) {
    Write-Host "Stopping existing Flask instances..." -ForegroundColor Yellow
    $existingFlask | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Write-Host "Starting Flask server in background..." -ForegroundColor Green
$pythonPath = (Get-Command python).Source
$appPath = Join-Path (Split-Path $MyInvocation.MyCommand.Path) "..\app.py"

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $pythonPath
$processInfo.Arguments = $appPath
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true

$appProcess = [System.Diagnostics.Process]::Start($processInfo)
Start-Sleep -Seconds 3

Write-Host "Flask server started (PID: $($appProcess.Id))" -ForegroundColor Green
Write-Host ""
Write-Host "Running Locust test..." -ForegroundColor Green
Write-Host "Test configuration:" -ForegroundColor Yellow
Write-Host "  - Users: 10" -ForegroundColor Yellow
Write-Host "  - Spawn rate: 2 users/sec" -ForegroundColor Yellow
Write-Host "  - Duration: 60 seconds" -ForegroundColor Yellow
Write-Host ""

# Ensure output directory exists
$scriptDir = Split-Path $MyInvocation.MyCommand.Path
$resultsFile = Join-Path $scriptDir "locust_results"

# Run Locust
& locust -f $appPath.Replace("app.py", "scripts\locustfile.py") `
    --host=http://localhost:5000 `
    --users=10 `
    --spawn-rate=2 `
    --run-time=60s `
    --headless `
    --csv=$resultsFile

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Test Complete!" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Results saved to:" -ForegroundColor Green
Write-Host "  - $resultsFile`_stats.csv (statistics)" -ForegroundColor Green
Write-Host "  - $resultsFile`_stats_history.csv (timeline)" -ForegroundColor Green
Write-Host "  - $resultsFile`_failures.csv (failures, if any)" -ForegroundColor Green
Write-Host ""

Write-Host "Shutting down Flask server..." -ForegroundColor Yellow
$appProcess | Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "Done!" -ForegroundColor Green
