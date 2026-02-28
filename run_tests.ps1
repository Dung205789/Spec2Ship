# Spec2Ship Test Runner for Windows PowerShell
# Usage:
#   .\run_tests.ps1 smoke
#   .\run_tests.ps1 rules
#   .\run_tests.ps1 ollama
#   .\run_tests.ps1 all

param(
    [Parameter(Position=0)]
    [string]$Mode = "smoke"
)

$API_URL = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }

Write-Host ""
Write-Host "================================================"
Write-Host "  Spec2Ship Test Runner"
Write-Host "================================================"
Write-Host "  Mode   : $Mode"
Write-Host "  API    : $API_URL"
Write-Host "  Web UI : http://localhost:3000"
Write-Host "================================================"
Write-Host ""

# Check pytest is installed
try {
    $null = Get-Command pytest -ErrorAction Stop
} catch {
    Write-Host "[ERROR] pytest not found. Run: pip install pytest requests"
    exit 1
}

# Check API is reachable
Write-Host "  Checking API at $API_URL/healthz ..."
try {
    $response = Invoke-WebRequest -Uri "$API_URL/healthz" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($response.StatusCode -ne 200) {
        Write-Host "[ERROR] API returned $($response.StatusCode)"
        Write-Host "        Run: docker compose up -d --build"
        exit 1
    }
    Write-Host "  [OK] API is up"
} catch {
    Write-Host ""
    Write-Host "[ERROR] Cannot reach $API_URL/healthz"
    Write-Host ""
    Write-Host "  Steps to fix:"
    Write-Host "    1. cd to spec2ship_v3 directory"
    Write-Host "    2. docker compose up -d --build"
    Write-Host "    3. Wait 15 seconds"
    Write-Host "    4. docker compose ps   (all should be healthy)"
    Write-Host "    5. Run tests again"
    Write-Host ""
    exit 1
}

Write-Host ""

$env:API_URL = $API_URL

switch ($Mode) {
    "smoke" {
        Write-Host "  Running smoke tests (~10 seconds)..."
        Write-Host ""
        pytest test_spec2ship.py -m smoke -v -s
    }
    "rules" {
        $env:PATCHER_MODE = "rules"
        Write-Host "  Running rules patcher tests (~2-3 min)..."
        Write-Host "  NOTE: Reset sample workspace on http://localhost:3000 first"
        Write-Host ""
        pytest test_spec2ship.py -m rules -v -s
    }
    "ollama" {
        $env:PATCHER_MODE = "ollama"
        if (-not $env:POLL_TIMEOUT) { $env:POLL_TIMEOUT = "600" }
        Write-Host "  Running Ollama tests (~5-10 min)..."
        Write-Host "  NOTE: Requires docker compose with docker-compose.llm.yml"
        Write-Host ""
        pytest test_spec2ship.py -m ollama -v -s
    }
    "all" {
        $env:PATCHER_MODE = "rules"
        Write-Host "  Running all tests..."
        Write-Host ""
        pytest test_spec2ship.py -v -s
    }
    default {
        Write-Host "[ERROR] Unknown mode: $Mode"
        Write-Host "  Valid modes: smoke, rules, ollama, all"
        exit 1
    }
}

Write-Host ""
Write-Host "  Web UI  : http://localhost:3000"
Write-Host "  API docs: $API_URL/docs"
