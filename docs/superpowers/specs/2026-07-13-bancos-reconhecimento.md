# Mapa dos bancos — reconhecimento e caminho por banco

> Situação de cada banco para o driver real de simulação (#1A Task 12+).
> Complementa `2026-07-13-driver-real-santander-design.md`. Data: 2026-07-13.
> **Não** é plano de implementação: cada banco ganha o seu quando for atacado (fluxo mapeado via codegen).

## Princípio (repetido do design)

Integração **API-first**: se o banco tem API/contrato → `ApiBankDriver` (HTTP, sem browser). Só quando
**não há** API → `PlaywrightBankDriver` (robô no portal, com todo o cuidado de fragilidade/ToS). Todos
implementam a mesma interface `Driver`; o resto do Motor não muda.

## Situação por banco

| Banco | URL de acesso | Login | API? | Caminho | Fluxo mapeado? |
|---|---|---|---|---|---|
| **Santander** | `financiamentos.santander.com.br/originacao-auto/login` | usuário+senha | **a verificar** | Playwright (piloto) | **Piloto** — Passo 1 conhecido; 2–5 via codegen (ver plano Fase 1) |
| **Pan** | `veiculos.bancopan.com.br/login` | usuário+senha, sem 2FA | **a verificar** | Playwright *(se não houver API)* | Não — mapear via codegen |
| **Fontecred** | `app.fontecred.com.br/login` | usuário+senha, sem 2FA | **a verificar** | Playwright *(se não houver API)* | Não — mapear via codegen |
| **Bradesco** | `turbo.bradesco/originacaolojista/login` | usuário+senha, sem 2FA | **a verificar** | Playwright *(se não houver API)* | Não — mapear via codegen |
| BV | — | a levantar | a verificar | a definir | Não |

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

1. **Santander** (piloto) — constrói a base `PlaywrightBankDriver` e prova o fim-a-fim.
2. Depois, **um banco por vez** (Pan / Fontecred / Bradesco), na ordem de volume da loja. Cada um é um
   incremento barato porque a base já existe.

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
