$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
$local = Join-Path $PSScriptRoot "workflow-fly.ready.json"
if (-not (Test-Path $local)) { throw "missing $local - run prepare-workflow.ps1 first" }

Write-Host "Uploading workflow ($((Get-Item $local).Length) bytes) via sftp..."
fly ssh sftp put -a n8n2037 $local /tmp/wf.json
fly ssh console -a n8n2037 -C "wc -c /tmp/wf.json"

# CLI must use HOME=/home/node so data lands on the volume at /home/node/.n8n
# (NOT N8N_USER_FOLDER=/home/node/.n8n — that creates nested .n8n/.n8n)
Write-Host "Importing workflow into production DB (HOME=/home/node)..."
fly ssh console -a n8n2037 -C "sh -c 'export HOME=/home/node; n8n import:workflow --input=/tmp/wf.json'"

Write-Host "Publishing workflow..."
fly ssh console -a n8n2037 -C "sh -c 'export HOME=/home/node; n8n publish:workflow --id=wAiNaoSalvos0001'"

Write-Host "Listing workflows..."
fly ssh console -a n8n2037 -C "sh -c 'export HOME=/home/node; n8n list:workflow'"

Write-Host "Restart n8n so the published webhook registers:"
Write-Host "  fly apps restart n8n2037"
Write-Host "Done import/publish step."
