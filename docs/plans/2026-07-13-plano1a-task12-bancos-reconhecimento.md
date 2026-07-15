# Mapa dos bancos — reconhecimento e caminho por banco

> Situação de cada banco para o driver real de simulação (#1A Task 12+).
> Complementa `2026-07-13-plano1a-task12-santander-design.md`. Data: 2026-07-13.
> **Não** é plano de implementação: cada banco ganha o seu quando for atacado (fluxo mapeado via codegen).
>
> **Atualização 2026-07-13:** piloto **Santander LIVE OK**. Antes de codar o próximo Playwright, leia  
> **`2026-07-13-playwright-licoes-santander.md`** (WAF, Xvfb, Material, modais, parsers).  
> Base reutilizável: `PlaywrightBankDriver` + worker headed+Xvfb.

## Princípio (repetido do design)

Integração **API-first**: se o banco tem API/contrato → `ApiBankDriver` (HTTP, sem browser). Só quando
**não há** API → `PlaywrightBankDriver` (robô no portal, com todo o cuidado de fragilidade/ToS). Todos
implementam a mesma interface `Driver`; o resto do Motor não muda.

## Situação por banco

| Banco | URL de acesso | Login | API? (reconhecimento 2026-07-13) | Caminho provável | Fluxo mapeado? |
|---|---|---|---|---|---|
| **Santander** | `financiamentos.santander.com.br/originacao-auto/login` | usuário+senha | **NÃO** (piloto confirmou só portal) | Playwright **LIVE OK** | **Sim** — login + passo 1 + ofertas multi-prazo (2026-07-13) |
| **Pan** | `veiculos.bancopan.com.br/login` | usuário+senha, sem 2FA | **API no código** (`PanDriver` OpenAPI) — credencial developer da loja **a validar live** | **Dual-path:** API se config completa; senão **Playwright portal** (codegen 2026-07-15 parcial) | **Parcial** — login+placa+valor; falta HTML de ofertas multi-prazo. Plano: `2026-07-15-plano1a-task12-pan-playwright-implementacao.md` |
| **BV** (Votorantim) | portal lojista a levantar | a levantar | **PROVÁVEL SIM** — doc "Iniciar Simulação Financiamento Veículo (V4)" no portal dev | **Confirmar API antes** → provável `ApiBankDriver` | Não |
| **Bradesco** | `turbo.bradesco/originacaolojista/login` | usuário+senha, sem 2FA | **provável** API pública, mas loja usa Turbo web hoje | **Playwright Turbo** (codegen 2026-07-15); gate API rápido no plano | **Sim (codegen)** — login → proposta → pessoa → veículo → simulação multi-prazo. Plano: `2026-07-15-plano1a-task12-bradesco-implementacao.md` |
| **Fontecred** | `app.fontecred.com.br/login` | usuário+senha, sem 2FA | **NÃO** (piloto Playwright) | Playwright **LIVE OK** | **Sim** — ver lições 2026-07-15 |

## Achados de reconhecimento (2026-07-13)

Busca pública (não confirma acesso do seu CNPJ nem o endpoint exato — páginas técnicas são gated):

- **Pan** tem Portal do Desenvolvedor com página de *Financiamento de Veículos*:
  `developers.bancopan.com.br/documentacao/financiamento-veiculos` (deu 403 → exige cadastro).
- **BV (Banco Votorantim)** documenta uma API "Iniciar Simulação Financiamento Veículo (V4)" e
  "Incluir Dados Simulação" no portal dev — forte indício de API de simulação.
- **Bradesco** tem portal dev robusto (`api.bradesco`, `developers.bradesco.com.br`, 120+ APIs, teste
  livre p/ não-clientes) — confirmar se há produto de originação/simulação auto para lojista.
- **Santander:** nenhuma API pública de simulação achada; integração aparece via plugins de parceiros
  (ex.: Cockpit) → reforça o caminho Playwright.
- **Fontecred:** fintech de crédito (FonteGIRO), sem documentação de API de desenvolvedor achada.

**Implicação:** possivelmente **2–3 desses (Pan, BV, talvez Bradesco) têm API** — não construir robô
para eles antes de descartar a API. Só Santander (e talvez Fontecred) tende a Playwright.

## Roteiro para o gerente/consultor do banco (copiar e enviar)

> "Somos uma revenda de veículos e queremos **integrar a simulação de financiamento de vocês ao nosso
> sistema** (não usar o portal na mão). Vocês têm uma **API de simulação** para lojista/parceiro? Se sim:
> como consigo **acesso/credencial de sandbox e produção**, qual a **documentação** (endpoints de
> simulação de parcela/taxa por CPF, valor, entrada e prazo), e há **contrato/custo**? Se não houver API,
> confirmam que a única forma é pelo portal web?"

Trazer de volta, por banco: **tem API? (s/n)**, link da doc, como obter credencial, e se cobre a
simulação (parcela/taxa) que precisamos.

> Confirmado com o dono em 2026-07-13: a loja **acessa** Pan, Fontecred e Bradesco por **portal web,
> usuário+senha, sem 2FA**. Isso é como a loja **usa** hoje — **não** confirma ausência de API. A coluna
> "API?" fica **a verificar** para todos até checar com o gerente/consultor de cada banco. Se algum tiver
> API de simulação para lojista, aquele banco passa a `ApiBankDriver` (melhor: sem robô, sem ToS/
> fragilidade). Playwright é o caminho **só se confirmado que não há API**.

## Como verificar se um banco tem API (antes de partir pro robô)

- Perguntar ao **gerente da conta / consultor** do banco se há API de simulação para integração de revenda.
- Procurar **portal do desenvolvedor / "parceiros" / "integração"** do banco.
- Pedir ao time comercial o **kit/manual de integração**, se houver.
- Só depois de confirmar que **não há** API acessível à loja, o banco vai para o caminho Playwright.

## Ordem sugerida

1. ~~**Santander** (piloto)~~ — **feito live 2026-07-13** (base `PlaywrightBankDriver` + worker Xvfb).
2. **Um banco por vez** na ordem de volume da loja:
   - Preferir **confirmar API** (Pan, BV, Bradesco) antes de Playwright.
   - **Fontecred** (e similares sem API) → Playwright reutilizando a base + lições.
3. Cada banco Playwright: ~4 tasks (codegen → driver → registro REAL_DRIVERS → smoke live).

## Template do plano por banco (pós-Santander)

Como a base (`PlaywrightBankDriver`: browser, login, sessão, screenshot, mapeamento de erros, gating por
credencial, multi-prazo) já existe depois do Santander, o plano de **cada** banco novo é uma versão
enxuta das Tasks 8–11 do plano Fase 1 — **sem** reconstruir a base:

1. **Codegen do fluxo** — `playwright codegen <url-do-banco>`; fazer uma simulação à mão; salvar o HTML
   de cada passo em `tests/fixtures/<banco>/passoN.html`.
2. **`<Banco>Driver(PlaywrightBankDriver)`** — implementar `login` (rótulos do portal) e `preencher_e_ler`
   (passos + leitura das parcelas), **ancorando no texto visível**, com testes contra as fixtures.
3. **Registrar em `REAL_DRIVERS["<banco>"]`** + fábrica que injeta a credencial (Task 11) e reporta
   `registrar_sucesso_login`/`registrar_falha_login`.
4. **Smoke live gated** (`MOTOR_<BANCO>_LIVE=1`) + credencial da loja cadastrada + nota no RUNBOOK.

Cada banco: ~4 tasks, sem tocar na base nem no contrato.

## O que ainda precisa de você (por banco, na hora de atacar)

- Rodar o **codegen** no portal do banco e me passar o HTML/fluxo de cada passo (eu não acesso portal
  bancário).
- Cadastrar a **credencial da loja** naquele banco (`PUT /v1/provedores/<banco>/credenciais`).
- Confirmar quais **campos** o portal daquele banco exige (podem diferir do Santander: alguns pedem
  renda, outros não; finalidade/CNH podem não existir).

## Riscos (iguais ao Santander, por banco)

- **ToS:** cada portal tem seus termos; automação/raspagem pode violar e levar a bloqueio da conta.
- **Fragilidade:** mudança de layout quebra o robô daquele banco → manutenção recorrente e isolada
  (quebrar o Pan não afeta o Santander).

## Fora deste reconhecimento

- BV: sem URL/dados ainda — levantar login/API antes de decidir o caminho.
- Agregador multi-banco: só se surgir contrato comercial.
