$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Install project dependencies first. See README.md.'
}
& $projectPython scripts/configure_docker.py
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare .env.docker.' }
docker compose --env-file .env.docker -f docker-compose.yml config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Docker configuration is invalid. Check .env.docker.' }
docker compose --env-file .env.docker -f docker-compose.yml up --build -d --wait --wait-timeout 600
if ($LASTEXITCODE -ne 0) { throw 'Docker services did not become ready. Check docker compose --env-file .env.docker logs --tail=100 web db clamav.' }
$webAddress = docker compose --env-file .env.docker -f docker-compose.yml port web 8000
if ($LASTEXITCODE -eq 0) {
    Write-Host "VOLNA: http://$webAddress"
}
