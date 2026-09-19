<#
.SYNOPSIS
  Mantem as credenciais dos portais de banco em dois lugares ao mesmo tempo:
  o .env.local (que roda na sua maquina) e o GitHub (que roda no CI).

.DESCRIPTION
  GitHub Secret e via de mao unica: `gh secret set` escreve, e nada le de volta.
  Por isso este script SEMPRE grava nos dois lados na mesma chamada. Voce nunca
  edita so um e descobre a divergencia quando o probe falha.

  Segredo vai para `gh secret` (senha, CPF, nascimento, celular, usuario).
  Parametro de simulacao vai para `gh variable` (placa, valor, prazo, UF), que
  da para ler e editar direto na interface do GitHub.

.EXAMPLE
  .\deploy\ci\secrets.ps1 set MOTOR_BRADESCO_SENHA
  .\deploy\ci\secrets.ps1 push
  .\deploy\ci\secrets.ps1 list
  .\deploy\ci\secrets.ps1 check
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('set', 'push', 'list', 'check', 'help')]
  [string]$Comando = 'help',

  [Parameter(Position = 1)]
  [string]$Nome,

  [string]$Repo = 'gacherubini/CRM',

  # Caminho do .env.local. So precisa passar quando o script roda de um
  # worktree e o arquivo esta na arvore principal (ele fica fora do git).
  [string]$EnvLocal
)

$ErrorActionPreference = 'Stop'

# UTF-8 SEM BOM ao canalizar para executavel nativo. O default do PowerShell 5.1
# prefixa U+FEFF em cada write do pipe, e o `gh` grava isso dentro do valor: uma
# senha de portal chega ao CI com um caractere invisivel na frente e o login
# falha sem dizer por que. Conferido em 19/09/2026 com `gh variable list`.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

if (-not $EnvLocal) {
  $Raiz = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
  $EnvLocal = Join-Path $Raiz 'motor-simulacao\.env.local'
}

# Nao sao segredo: sao os parametros da simulacao de teste. Ficam em
# `gh variable` para voce conseguir ler e ajustar sem adivinhar o valor atual.
$Variaveis = @(
  'MOTOR_BROWSER_HEADLESS',
  'MOTOR_WARM_SESSION',
  'MOTOR_SCREENSHOT_DIR',
  'MOTOR_STORAGE_STATE_DIR',
  'PROBE_PLACA',
  'PROBE_VALOR',
  'PROBE_UF',
  'PROBE_PRAZOS',
  'PROBE_ENTRADA',
  'PROBE_CATEGORIA'
)

function EhVariavel([string]$n) { return $Variaveis -contains $n }

function ConferirGh {
  $gh = Get-Command gh -ErrorAction SilentlyContinue
  if (-not $gh) { throw "gh CLI nao encontrado. Instale: winget install GitHub.cli" }
  gh auth status 2>&1 | Out-Null
  if (-not $?) { throw "gh nao autenticado. Rode: gh auth login" }
}

function LerEnvLocal {
  $mapa = [ordered]@{}
  if (-not (Test-Path $EnvLocal)) { return $mapa }
  foreach ($linha in Get-Content $EnvLocal -Encoding UTF8) {
    if ($linha -match '^\s*#') { continue }
    $i = $linha.IndexOf('=')
    if ($i -lt 1) { continue }
    $k = $linha.Substring(0, $i).Trim()
    $v = $linha.Substring($i + 1)
    if ($k) { $mapa[$k] = $v }
  }
  return $mapa
}

function GravarEnvLocal([string]$n, [string]$valor) {
  $linhas = @()
  if (Test-Path $EnvLocal) { $linhas = @(Get-Content $EnvLocal -Encoding UTF8) }
  $achou = $false
  $saida = foreach ($linha in $linhas) {
    if ($linha -match "^\s*$([regex]::Escape($n))\s*=") {
      $achou = $true
      "$n=$valor"
    }
    else { $linha }
  }
  if (-not $achou) { $saida = @($saida) + "$n=$valor" }
  Set-Content -Path $EnvLocal -Value $saida -Encoding UTF8
}

function EnviarAoGitHub([string]$n, [string]$valor) {
  # Arquivo temporario sem BOM, lido pelo stdin do gh via `cmd`. Os outros dois
  # caminhos obvios nao servem, e os dois foram medidos em 19/09/2026:
  #
  #   `$valor | gh ...`      o pipe do PowerShell 5.1 prefixa U+FEFF no valor,
  #                          mesmo com $OutputEncoding ajustado. Uma senha de
  #                          portal chega ao CI com um caractere invisivel na
  #                          frente e o login falha sem dizer por que.
  #   `gh ... --body $valor` limpo, mas poe a senha na linha de comando, onde
  #                          qualquer processo da maquina consegue ler.
  #
  # O PowerShell 5.1 nao tem redirecionamento `<`, dai o `cmd /c`.
  $tipo = if (EhVariavel $n) { 'variable' } else { 'secret' }
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
  try {
    [System.IO.File]::WriteAllText($tmp, $valor, (New-Object System.Text.UTF8Encoding $false))
    cmd /c "gh $tipo set $n --repo $Repo < ""$tmp"""
    if ($LASTEXITCODE -ne 0) { throw "falhou ao gravar o $tipo $n" }
  }
  finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
  }
  if ($tipo -eq 'variable') {
    Write-Host "  GitHub variable $n  (visivel na UI)" -ForegroundColor DarkGray
  }
  else {
    Write-Host "  GitHub secret   $n  (escrita so)" -ForegroundColor DarkGray
  }
}

switch ($Comando) {

  'set' {
    if (-not $Nome) { throw "uso: .\deploy\ci\secrets.ps1 set NOME_DA_VARIAVEL" }
    ConferirGh
    $Nome = $Nome.ToUpperInvariant()

    if (EhVariavel $Nome) {
      $valor = Read-Host "novo valor para $Nome"
    }
    else {
      $seguro = Read-Host "novo valor para $Nome (nao aparece na tela)" -AsSecureString
      $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
      try { $valor = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
      finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    if ([string]::IsNullOrWhiteSpace($valor)) { throw "valor vazio, nada foi gravado" }

    GravarEnvLocal $Nome $valor
    Write-Host "  .env.local      $Nome" -ForegroundColor DarkGray
    EnviarAoGitHub $Nome $valor
    Write-Host "$Nome atualizado nos dois lugares." -ForegroundColor Green
  }

  'push' {
    ConferirGh
    $mapa = LerEnvLocal
    if ($mapa.Count -eq 0) { throw "nao achei nada em $EnvLocal" }
    $n = 0
    foreach ($k in $mapa.Keys) {
      if ($k -notmatch '^(MOTOR|PROBE|MOTRIX)_') { continue }
      if ([string]::IsNullOrWhiteSpace($mapa[$k])) { continue }
      EnviarAoGitHub $k $mapa[$k]
      $n++
    }
    Write-Host "$n variaveis enviadas ao GitHub." -ForegroundColor Green
  }

  'list' {
    ConferirGh
    Write-Host "`nSECRETS (valor nao pode ser lido; a coluna de data responde 'de quando e essa senha')" -ForegroundColor Cyan
    gh secret list --repo $Repo
    Write-Host "`nVARIABLES (valor visivel)" -ForegroundColor Cyan
    gh variable list --repo $Repo
  }

  'check' {
    ConferirGh
    $local = LerEnvLocal
    $locais = @($local.Keys | Where-Object { $_ -match '^(MOTOR|PROBE|MOTRIX)_' })

    $remotos = @()
    $remotos += (gh secret list --repo $Repo --json name --jq '.[].name')
    $remotos += (gh variable list --repo $Repo --json name --jq '.[].name')
    $remotos = @($remotos | Where-Object { $_ -match '^(MOTOR|PROBE|MOTRIX)_' })

    $soLocal = @($locais | Where-Object { $remotos -notcontains $_ })
    $soRemoto = @($remotos | Where-Object { $locais -notcontains $_ })

    Write-Host "local:  $($locais.Count) variaveis"
    Write-Host "GitHub: $($remotos.Count) variaveis"
    if ($soLocal.Count) {
      Write-Host "`nSo no .env.local (o CI nao tem):" -ForegroundColor Yellow
      $soLocal | ForEach-Object { Write-Host "  $_" }
      Write-Host "  corrija com: .\deploy\ci\secrets.ps1 push"
    }
    if ($soRemoto.Count) {
      Write-Host "`nSo no GitHub (sua maquina nao tem):" -ForegroundColor Yellow
      $soRemoto | ForEach-Object { Write-Host "  $_" }
      Write-Host "  o valor nao da para baixar; regrave com: secrets.ps1 set <NOME>"
    }
    if (-not $soLocal.Count -and -not $soRemoto.Count) {
      Write-Host "`nOs dois lados tem os mesmos nomes." -ForegroundColor Green
    }
  }

  default {
    Write-Host @"
secrets.ps1 - credenciais dos portais de banco, nos dois lados de uma vez

  set <NOME>   pede o valor (senha nao aparece na tela) e grava no .env.local
               E no GitHub, na mesma chamada
  push         manda tudo que ja esta no .env.local para o GitHub (bootstrap)
  list         lista o que existe no GitHub e QUANDO cada um mudou
  check        compara os nomes dos dois lados e mostra o que falta onde

Rotacao de senha expirada:
  .\deploy\ci\secrets.ps1 set MOTOR_BRADESCO_SENHA

Secret (escrita so) x variable (visivel na UI). Sao variables:
  $($Variaveis -join ', ')
Todo o resto com prefixo MOTOR_ / PROBE_ / MOTRIX_ vira secret.
"@
  }
}
