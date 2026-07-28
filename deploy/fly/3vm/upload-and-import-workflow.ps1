param(
  [ValidateSet("production", "test")]
  [string]$Mode = "production"
)

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
$localName = if ($Mode -eq "test") {
  "workflow-fly-test.ready.json"
} else {
  "workflow-fly.ready.json"
}
$stamp = Get-Date -Format "yyyyMMddHHmmssfff"
$remote = if ($Mode -eq "test") { "/tmp/wf-test-$stamp.json" } else { "/tmp/wf-$stamp.json" }
$local = Join-Path $PSScriptRoot $localName
if (-not (Test-Path $local)) { throw "missing $local - run prepare-workflow.ps1 first" }
$workflow = Get-Content $local -Raw -Encoding UTF8 | ConvertFrom-Json
$workflowId = [string]$workflow.id
if (-not $workflowId) { throw "workflow sem id: $local" }
$machines = fly machine list -a n8n2037 --json | ConvertFrom-Json
$machine = $machines | Where-Object state -eq "started" | Select-Object -First 1
if (-not $machine) { throw "n8n2037 sem machine iniciada" }
$machineId = [string]$machine.id

Write-Host "Uploading workflow ($((Get-Item $local).Length) bytes) via sftp..."
fly ssh sftp put -a n8n2037 $local $remote
fly machine exec $machineId "wc -c $remote" -a n8n2037 --timeout 60

# CLI must use HOME=/home/node so data lands on the volume at /home/node/.n8n
# (NOT N8N_USER_FOLDER=/home/node/.n8n — that creates nested .n8n/.n8n)
Write-Host "Importing workflow into production DB (HOME=/home/node)..."
fly machine exec $machineId "env HOME=/home/node n8n import:workflow --input=$remote" -a n8n2037 --timeout 120

Write-Host "Publishing workflow..."
fly machine exec $machineId "env HOME=/home/node n8n publish:workflow --id=$workflowId" -a n8n2037 --timeout 120

Write-Host "Listing workflows..."
fly machine exec $machineId "env HOME=/home/node n8n list:workflow" -a n8n2037 --timeout 60

Write-Host "Restart n8n so the published webhook registers:"
Write-Host "  fly apps restart n8n2037"
Write-Host "Done import/publish step (mode=$Mode id=$workflowId)."
