# Lições do piloto Santander (Playwright) — guia para os próximos bancos

> **Checkpoint 2026-07-13 (fim da sessão live).**  
> Santander **fim-a-fim real** funcionando: login → passo 1 → simulação → multi-prazo no Portal.  
> Use este doc **antes** de codar Pan / Bradesco / Fontecred / BV em Playwright.  
> Design/API-first: `2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

## Status do piloto

| Item | Estado |
|---|---|
| Driver `santander` live | **OK** (headed + Xvfb no worker Docker) |
| Portal progresso HTMX + resultado multi-prazo | **OK** |
| **Entrada necessária devolvida pelo banco** (`parse_entrada`) | **OK** (não é input; coluna Entrada no Portal) |
| **Fix skeleton dos cards** (`_passo_aguardar_simulacao`) | **OK** (espera texto real `Nx de`) |
| Credenciais via Portal 9A → Motor cifrado | **OK** |
| `POST .../testar-login` | ainda **placeholder** (não valida portal de verdade) |
| Multi-banco paralelo (1 browser por banco) | **não implementado** (arquitetura preparada) |
| Listagem `GET /v1/simulacoes` + histórico por usuário | **OK** (Task 16, 2026-07-13) |

### Arquivos-chave

- `motor-simulacao/app/motor/playwright_base.py` — launch stealth, storage_state, screenshots, `portal_bloqueado`
- `motor-simulacao/app/motor/santander.py` — fluxo real + parsers
- `motor-simulacao/scripts/worker-entrypoint.sh` — Xvfb + limpeza de lock órfão
- `deploy/motor-standalone/docker-compose.yml` — worker `HEADLESS=0`, `shm_size: 1gb`, volume screenshots
- `portal-gestao/.../progresso.html` + rota job + `resultado.html` (códigos de erro legíveis)

### Env do worker (produção Docker)

```text
MOTOR_BROWSER_HEADLESS=0
PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0
DISPLAY=:99
MOTOR_SCREENSHOT_DIR=/srv/data/screenshots
MOTOR_STORAGE_STATE_DIR=/srv/data/storage_state
MOTOR_BROWSER_TIMEOUT_MS=60000
```

URL login padrão: `https://financiamentos.santander.com.br/originacao-auto/login`

---

## Problemas reais que encontramos (e como evitar no próximo banco)

### 1. Akamai / WAF (`portal_bloqueado`)

- **Sintoma:** HTML "Access Denied" / edgesuite; código `portal_bloqueado`.
- **Causa:** Chromium **headless_shell** e fingerprint de bot.
- **Fix:** browser **headed** sob **Xvfb**; `PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0`; stealth init + UA desktop BR em `playwright_base`.
- **Ainda possível:** IP de datacenter/Docker na lista negra — se headed falhar com Access Denied, investigar rede/VPN/IP da loja.

### 2. Xvfb morto após restart (`display_ausente` / `erro_inesperado` ~200 ms)

- **Sintoma:** job falha em &lt;1 s; log Playwright: *Missing X server or $DISPLAY*.
- **Causa:** lock órfão `/tmp/.X99-lock` + socket `/tmp/.X11-unix/X99` sem processo Xvfb.
- **Fix:** `worker-entrypoint.sh` limpa lock/socket se Xvfb não está vivo, sobe Xvfb e só então `exec python -m app.worker`.
- **Checklist próximo banco:** nunca assumir que `docker compose restart` deixou o display saudável; confira `pgrep Xvfb` após restart.

### 3. Angular Material: placeholder HTML vazio

- **Sintoma:** `get_by_placeholder("CPF")` → 0 elementos → timeout ~60 s → `portal_falhou`.
- **Causa:** texto "Digite o seu CPF" é **label flutuante**; `input.placeholder === ""`.
- **Fix:** `get_by_label`, `input[type=tel]`, `get_by_role("textbox")`, `formcontrolname=...`.
- **Regra:** no primeiro probe de um portal novo, rode no worker:
  `page.evaluate(() => [...document.querySelectorAll('input')].map(i => ({type, id, ph: i.placeholder})))`.

### 4. Falso positivo no pós-login

- **Sintoma:** "login OK" mas URL ainda `/login` e overlay "Por favor, aguarde...".
- **Causa:** regex `Cliente` casava com **"clientes"** da landing ("Aqui seus clientes compram mais").
- **Fix:** esperar marcadores **específicos** da área logada (`Informações básicas`, `CPF ou CNPJ`, URL sem `/login`) + sumir o overlay de loading.
- **Regra:** nunca usar palavra genérica que existe na landing/marketing.

### 5. Modal "Simulações anteriores"

- **Sintoma:** backdrop `cdk-overlay` intercepta cliques; timeout em nascimento/Continuar.
- **Causa:** CPF do cliente já tem proposta em andamento no portal.
- **Fix:** detectar heading do modal; fechar com **X** / `mat-dialog-close` / Escape — **não** clicar "Continuar essa simulação" se o objetivo é cotação nova.
- **Regra:** todo banco pode ter "rascunho/proposta aberta"; planejar dismiss.

### 6. Loading / backdrop transparente

- **Sintoma:** elemento "visible, enabled, stable" mas clique timeout — *overlay intercepts pointer events*.
- **Causa:** `app-loading-indicator` ("Por favor, aguarde...") ou `cdk-overlay-backdrop` de mat-select aberto.
- **Fix:** `_aguardar_loading`; Escape para fechar select; `click(force=True)` só como último recurso; Tab após CPF/placa para disparar API do portal.

### 7. Fluxo real ≠ fluxos inventados no plano

Fluxo **real** do Portal Auto (2026-07):

1. Login (CPF lojista + senha) → `proposal/step-personal`
2. CPF cliente → Tab → loading → (modal sims anteriores?) → nascimento + CNH
3. Radio **Busca por placa** → campo Placa → FIPE
4. Finalidade Comum/PCD → **Concordar e continuar**
5. `step-offers`: cards multi-prazo (`12x de` / `R$ …` em nós separados)

Não assumir campos "como no mock" sem codegen/probe.

### 8. Parser de parcelas e valor financiado

- **Sintoma A:** `parcelas_nao_encontradas` com tela cheia de ofertas.  
  **Causa:** HTML quebra `48x de` e `R$ 946,28` em tags/linhas.  
  **Fix:** `_texto_plano_portal` (strip tags + colapsa whitespace) + preferir `page.inner_text("body")`.
- **Sintoma B:** coluna **Financiado** = valor da parcela 48x em todas as linhas.  
  **Causa:** `Valor liberado.*?R$` com `.*?` atravessava até o card.  
  **Fix:** match apertado no rótulo; se o valor bate com uma parcela parseada, descartar; fallback `valor_bem - entrada`.

### 9. Hot-patch Docker vs rebuild

- `docker compose build` pode falhar (DNS Docker Hub).
- Hot-copy de `.py` **não recarrega** o worker já em memória — precisa **restart** do `motor-worker`.
- Entrypoint em imagem: copiar `scripts/worker-entrypoint.sh` + restart (ou rebuild quando rede OK).

### 10. Códigos de erro (Portal + Motor)

| Código | Significado |
|---|---|
| `portal_bloqueado` | WAF/Akamai |
| `portal_falhou` | erro genérico no fluxo (selector/timeout/layout) |
| `portal_simulacao_erro` | banner "Ocorreu um erro" no passo de oferta |
| `login_timeout` / `login_rejeitado` | não saiu da tela de login / credencial recusada |
| `display_ausente` | headed sem Xvfb |
| `browser_ausente` | Chromium não instalado na imagem |
| `sem_credencial` / `sem_driver_ou_credencial` | falta Acessos bancos |
| `parcelas_nao_encontradas` | chegou na tela mas parser falhou |
| `erro_inesperado` | exceção não classificada (ver logs + screenshot) |

Screenshots: `/srv/data/screenshots/` no volume do worker (`santander_inesperado.png`, etc.).

### 11. Cards em **skeleton** (falso `parcelas_nao_encontradas`)

- **Sintoma:** job chega na tela de ofertas (~50 s) mas falha com `parcelas_nao_encontradas`; screenshot
  mostra "Escolha a parcela desejada" com os cards ainda como **barras cinzas (skeleton)**, sem o texto
  "48x de R$ …".
- **Causa:** o **título** "Escolha a parcela desejada" aparece **antes** dos cards; estes nascem como
  skeleton (sem texto). Esperar só o título → parser lê cards vazios.
- **Fix:** `_passo_aguardar_simulacao` espera o **texto real do card** (`\d+\s*x\s*de`) com **2 leituras
  seguidas > 0** (estabilidade) + settle; seleciona a aba **Padrão** antes. Não basta o heading.
- **Regra p/ próximo banco:** nunca considerar a tela pronta pelo título/heading — aguardar o **dado**
  que você vai parsear (texto do card, valor), não o container/skeleton.

### 12. Entrada é **devolvida**, não enviada (Santander)

- O Santander **calcula a entrada necessária** e a exibe na tela ("Entrada R$ …", "Valor mínimo",
  "Entrada recomendada"). Não a enviamos como input: `_ajustar_entrada` foi **removido**.
- `parse_entrada` lê o rótulo `\bEntrada\b\s+R\$` (o `\b` evita casar "Valor liberado"/"Valor do veículo";
  descarta se casar o R$ de um card). Vai no campo `entrada` do resultado (por prazo) → coluna Entrada no
  Portal. Fallback financiado = `valor_bem − entrada(retornada)`.
- **Regra p/ próximo banco:** confira se o portal **pede** entrada ou **calcula**. Se calcula, leia; não
  invente input. Campos diferem por banco.

---

## Checklist para o próximo banco Playwright

1. **Confirmar ausência de API** (ver reconhecimento). Se tiver API → `ApiBankDriver`, não robô.
2. Credencial da loja em Portal → Acessos bancos (mesmo fluxo 9A).
3. Subir worker com headed+Xvfb; `pgrep Xvfb` + probe `page.goto(login)`.
4. Probe de inputs: types, placeholders, labels, `formcontrolname`, iframes.
5. Codegen / gravação manual de cada passo; salvar fixtures em `tests/fixtures/<banco>/`.
6. Implementar `<Banco>Driver(PlaywrightBankDriver)`:
   - login estável (sem falso positivo de landing)
   - dismiss de modais/loading
   - **esperar o dado real** (texto do card), não o título/skeleton (lição 11)
   - parse de ofertas com texto plano (não confiar em HTML cru)
   - **entrada**: ler se o banco calcula (lição 12); só enviar como input se o portal pedir
7. Registrar em `REAL_DRIVERS`; nomes canônicos **minúsculos** alinhados à credencial.
8. Mapear erros específicos → códigos estáveis (como acima).
9. Testes: parse com HTML real quebrado; fixture offline; smoke live gated por env.
10. Atualizar este doc + handoff com o que for específico daquele portal.

### O que reutilizar

- `PlaywrightBankDriver._launch_browser` / `_new_context` / stealth / screenshots  
- `worker-entrypoint.sh` e compose do worker  
- Padrão de `_aguardar_loading` / fechar overlay  
- `processamento._executar_driver` (retry, códigos, não deixar job em `processando` eterno)  
- UI Portal progresso + tabela de códigos

### O que **não** copiar cegamente do Santander

- Seletores de label/placeholder  
- Assumir "Busca por placa" ou "Concordar e continuar"  
- Regex de parcela sem normalizar HTML  
- `testar-login` como prova de credencial (ainda placeholder)

---

## Ordem sugerida pós-Santander

1. ~~**Histórico de simulações por usuário no Portal** (#3A.1 Task 16)~~ — **FEITO (2026-07-13)**:
   `GET /v1/simulacoes` + `solicitado_por` + tela `/app/simulacoes/historico`.
2. **Corrigir 2 falhas pré-existentes** do Motor (mock `Santander` sombreado pelo driver real homônimo).
3. **Pan / BV / Bradesco** — primeiro **confirmar API** com gerente; se API, implementar HTTP.  
4. **Fontecred** — candidato Playwright se confirmar sem API.  
5. Multi-banco paralelo no mesmo job (1 browser por provedor).  
6. `testar-login` real (Playwright short) no Motor.  
7. Task 10 revenda; go-live WhatsApp em paralelo de produto.

## Verificação rápida (operador)

```powershell
cd deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb; ls /srv/data/screenshots | tail"
# No Portal: Acessos bancos com Santander habilitado + MOTOR_TOKEN no portal
# Simular → progresso → tabela com status concluida e financiado coerente (≠ parcela)
```
