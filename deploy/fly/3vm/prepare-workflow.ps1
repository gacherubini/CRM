param(
  [ValidateSet("production", "test", "cloud", "preview")]
  [string]$Mode = "production"
)

# Prepares n8n workflow JSON with Fly hosts + tokens from .secrets.local
# Does NOT print secret values.
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $root "n8n\workflow-ai-nao-salvos.json"))) {
  $root = (Get-Location).Path
}
# cloud = Modo 2 (Cloud API da Meta). O canonico e GERADO por
# n8n/fork_cloud_workflow.py — nao editar a mao.
# preview = tela de configuracao do agente na Revy Loja. Tambem GERADO
# (n8n/build_preview_workflow.py) e com as ferramentas em modo seco.
$canonicalName = switch ($Mode) {
  "test"    { "workflow-teste-numero-autorizado.json" }
  "cloud"   { "workflow-cloud.json" }
  "preview" { "workflow-preview.json" }
  default   { "workflow-ai-nao-salvos.json" }
}
$outputName = switch ($Mode) {
  "test"    { "workflow-fly-test.ready.json" }
  "cloud"   { "workflow-cloud.ready.json" }
  "preview" { "workflow-preview.ready.json" }
  default   { "workflow-fly.ready.json" }
}
$canonical = Join-Path $root "n8n\$canonicalName"
$secretsFile = Join-Path $PSScriptRoot ".secrets.local"
$outFile = Join-Path $PSScriptRoot $outputName

if (-not (Test-Path $canonical)) { throw "canonical workflow not found: $canonical" }
if (-not (Test-Path $secretsFile)) { throw "missing $secretsFile" }

$secrets = @{}
Get-Content $secretsFile | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $i = $_.IndexOf('=')
  $k = $_.Substring(0, $i).Trim()
  $v = $_.Substring($i + 1).Trim()
  if ($k -and $v) { $secrets[$k] = $v }
}

# Prefer public HTTPS: n8n reaches these reliably.
# flycast needs private IPv6 + nginx listen [::] (see nginx-edge.conf).
$chatbotBase = if ($env:CHATBOT_BASE_URL) { $env:CHATBOT_BASE_URL } else { "https://app2037.fly.dev" }
$evolutionBase = if ($env:EVOLUTION_BASE_URL) { $env:EVOLUTION_BASE_URL } else { "https://evolution2037.fly.dev" }
# multi-WA: instance NÃO é substituída — vem de body.instance em cada evento Evolution.
# Um único workflow atende N números; o Chatbot resolve loja/canal por instância.

$json = Get-Content $canonical -Raw -Encoding UTF8
$json = $json.Replace("http://chatbot-api:8000", $chatbotBase)
$json = $json.Replace("http://evolution:8080", $evolutionBase)
if ($json.Contains("__INSTANCE__")) {
  Write-Warning "canonical still has __INSTANCE__; multi-WA expects dynamic body.instance only"
}
# O Modo 2 autentica com uma credencial de INTEGRACAO (papel=integracao, sem loja):
# um workflow serve N lojas e resolve a loja pela instance de cada chamada (spec 6.2).
# O token do Modo 1 aponta para UMA loja -- reusa-lo aqui ressuscita exatamente o bug
# que a 6.2 fechou, e o sintoma e silencio, nao erro. Por isso fail-fast, nao fallback.
# O preview usa a credencial de INTEGRACAO pela mesma razao do Modo 2: ele serve
# N lojas e diz de qual fala pela instance que o chatbot manda no corpo. Com o
# token de UMA loja, o lojista da loja B testaria contra o estoque da loja A.
$chatbotTokenKey = if ($Mode -eq "cloud" -or $Mode -eq "preview") { "CHATBOT_API_TOKEN_CLOUD" } else { "CHATBOT_API_TOKEN" }
if (-not $secrets.ContainsKey($chatbotTokenKey) -or -not $secrets[$chatbotTokenKey]) {
  throw "missing $chatbotTokenKey in $secretsFile (mode=$Mode). Crie a credencial com: python -m app.cli criar-credencial-integracao"
}
$json = $json.Replace("__CHATBOT_TOKEN__", $secrets[$chatbotTokenKey])
$json = $json.Replace("__CHATBOT_WEBHOOK_TOKEN__", $secrets["CHATBOT_WEBHOOK_TOKEN"])

# Evolution apikey: env > .evolution_key.local > .secrets.local EVOLUTION_API_KEY
$evoKey = $env:EVOLUTION_API_KEY
if (-not $evoKey) {
  $evoKeyFile = Join-Path $PSScriptRoot ".evolution_key.local"
  if (Test-Path $evoKeyFile) {
    $evoKey = (Get-Content $evoKeyFile -Raw).Trim()
  }
}
if (-not $evoKey -and $secrets.ContainsKey("EVOLUTION_API_KEY") -and $secrets["EVOLUTION_API_KEY"]) {
  $evoKey = $secrets["EVOLUTION_API_KEY"]
}
if ($evoKey) {
  $json = $json.Replace("__EVOLUTION_KEY__", $evoKey)
  Write-Host "evolution apikey: len=$($evoKey.Length)"
} elseif ($json.Contains("__EVOLUTION_KEY__")) {
  Write-Warning "EVOLUTION_API_KEY missing - __EVOLUTION_KEY__ left as placeholder (Evolution calls will 401)"
}

# Activate for import
$json = $json.Replace('"active": false', '"active": true')

[System.IO.File]::WriteAllText($outFile, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "wrote $outFile (len=$($json.Length)) mode=$Mode chatbot=$chatbotBase evolution=$evolutionBase instance=dynamic(body.instance)"
Write-Host "tokens: $chatbotTokenKey=$($secrets[$chatbotTokenKey].Length) webhook=$($secrets['CHATBOT_WEBHOOK_TOKEN'].Length)"
