#Requires -Version 5.1
<#
.SYNOPSIS
  Recria o acesso read-only de produção (skill prod-readonly-db) nesta máquina.

.DESCRIPTION
  Fonte de verdade é o Fly (org crm-419). Nada de segredo fica no git: a senha
  das roles *_reader é lida do secret PROD_READONLY_DB_PASSWORD no app2037, e a
  partir dela o script grava o pg_service.conf e o pgpass.conf no path do SO e
  exporta as variáveis PROD_READONLY_DB_* dos aliases.

  O banco (suite-pg) é privado. O acesso é por túnel: rode `-Tunnel` (ou
  `fly proxy 15432:5432 -a suite-pg` em outro terminal) antes de consultar.

  As roles são read-only de verdade (SELECT, sem ownership, sem CONNECT fora do
  próprio banco). O superusuário não é usado aqui em regime normal.
#>
[CmdletBinding()]
param(
    [switch]$Tunnel,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$FlyApp    = 'app2037'
$PgApp     = 'suite-pg'
$LocalPort = 15432
$RemotePort = 5432

$aliases = [ordered]@{
    'revy-chatbot'   = @{ db = 'chatbot';   role = 'chatbot_reader';   schemas = 'public' }
    'revy-estoque'   = @{ db = 'estoque';   role = 'estoque_reader';   schemas = 'public' }
    'revy-motor'     = @{ db = 'motor';     role = 'motor_reader';     schemas = 'public' }
    'revy-revy'      = @{ db = 'revy';      role = 'revy_reader';      schemas = 'portal,control,public' }
    'revy-evolution' = @{ db = 'evolution'; role = 'evolution_reader'; schemas = 'public' }
}

function Write-Step($msg) { if (-not $Quiet) { Write-Host $msg } }

# fly escreve progresso em stderr; com ErrorActionPreference=Stop isso viraria
# erro terminante. Captura só o stdout com o EAP rebaixado na chamada.
function Invoke-Fly {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$FlyArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return (& fly @FlyArgs 2>$null) } finally { $ErrorActionPreference = $prev }
}

Write-Step 'conferindo login do Fly...'
$who = Invoke-Fly auth whoami
if (-not $who) {
    throw 'Fly não está autenticado. Rode `fly auth login` e tente de novo.'
}

Write-Step "lendo senha do reader de $FlyApp..."
$raw = Invoke-Fly ssh console -a $FlyApp -C "sh -lc 'printenv PROD_READONLY_DB_PASSWORD'"
$pw = ($raw | Where-Object { $_ -and ($_ -notmatch 'Connecting to') } | Select-Object -Last 1)
if ($pw) { $pw = $pw.Trim() }
if (-not $pw) {
    throw "não achei PROD_READONLY_DB_PASSWORD nos secrets de $FlyApp"
}

if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $svcDir = Join-Path $env:APPDATA 'postgresql'
    New-Item -ItemType Directory -Force -Path $svcDir | Out-Null
    $svcFile = Join-Path $svcDir '.pg_service.conf'
    $passFile = Join-Path $svcDir 'pgpass.conf'
} else {
    $svcDir = $HOME
    $svcFile = Join-Path $HOME '.pg_service.conf'
    $passFile = Join-Path $HOME '.pgpass'
}

$svcLines = @()
$passLines = @()
foreach ($alias in $aliases.Keys) {
    $a = $aliases[$alias]
    $svcLines += "[$alias]"
    $svcLines += 'host=127.0.0.1'
    $svcLines += "port=$LocalPort"
    $svcLines += "dbname=$($a.db)"
    $svcLines += "user=$($a.role)"
    $svcLines += 'sslmode=disable'
    $svcLines += ''
    $passLines += "127.0.0.1:${LocalPort}:$($a.db):$($a.role):$pw"
}

[IO.File]::WriteAllText($svcFile, ($svcLines -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
[IO.File]::WriteAllText($passFile, ($passLines -join "`n"), (New-Object System.Text.UTF8Encoding($false)))

if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    icacls $passFile /inheritance:r /grant:r "$($env:USERNAME):(F)" | Out-Null
} else {
    chmod 600 $passFile
    chmod 600 $svcFile
}
Write-Step "escrito: $svcFile"
Write-Step "escrito: $passFile"

# Variáveis dos aliases (não são segredo).
foreach ($alias in $aliases.Keys) {
    $a = $aliases[$alias]
    $key = $alias.ToUpper().Replace('-', '_')
    $vars = [ordered]@{
        "PROD_READONLY_DB_${key}_SERVICE"           = $alias
        "PROD_READONLY_DB_${key}_EXPECTED_DATABASE" = $a.db
        "PROD_READONLY_DB_${key}_EXPECTED_ROLE"     = $a.role
        "PROD_READONLY_DB_${key}_ALLOWED_SCHEMAS"   = $a.schemas
        "PROD_READONLY_DB_${key}_TRANSPORT"         = 'tunnel'
    }
    foreach ($name in $vars.Keys) {
        if ($IsWindows -or $env:OS -eq 'Windows_NT') {
            [Environment]::SetEnvironmentVariable($name, $vars[$name], 'User')
        }
        Set-Item "env:$name" $vars[$name]
    }
}
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    [Environment]::SetEnvironmentVariable('PGSERVICEFILE', $svcFile, 'User')
} else {
    $profileLine = "export PGSERVICEFILE=`"$svcFile`""
    foreach ($rc in @("$HOME/.bashrc", "$HOME/.zshrc")) {
        if ((Test-Path $rc) -and -not (Select-String -Path $rc -SimpleMatch $profileLine -Quiet)) {
            Add-Content -Path $rc -Value $profileLine
        }
    }
}
Set-Item 'env:PGSERVICEFILE' $svcFile
Write-Step 'aliases exportados (variáveis de usuário).'

Write-Step ''
Write-Step "pronto. $($aliases.Keys.Count) aliases: $($aliases.Keys -join ', ')"

if ($Tunnel) {
    Write-Step "abrindo túnel local $LocalPort -> ${PgApp}:$RemotePort ..."
    Start-Process -FilePath 'fly' -ArgumentList @('proxy', "${LocalPort}:${RemotePort}", '-a', $PgApp) -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 6
    Write-Step "túnel ativo em 127.0.0.1:$LocalPort (feche o processo fly proxy para encerrar)."
} else {
    Write-Step "abra o túnel em outro terminal: fly proxy ${LocalPort}:${RemotePort} -a $PgApp"
}

Write-Step ''
Write-Step 'teste:'
Write-Step "  `"SELECT current_database(), current_user`" | python skills/prod-readonly-db/scripts/readonly_psql.py --alias revy-motor"
