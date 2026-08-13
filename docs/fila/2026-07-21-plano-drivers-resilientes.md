# Plano #1A — Drivers Playwright resilientes

> **Status 2026-07-21: BACKLOG / NÃO IMPLEMENTADO.**  
> Plano de evolução posterior dos drivers de simulação. Não autoriza alterar o fluxo
> financeiro nem adotar IA/anti-detect em produção sem canário e revisão explícita.  
> Complementa o [plano #1A](2026-07-11-plano1a-motor-simulacao-independente.md), as
> [lições Santander](2026-07-13-playwright-licoes-santander.md), as
> [lições Fontecred](2026-07-15-playwright-licoes-fontecred.md) e o plano de
> [warm session + batch 2](2026-07-17-plano1a-warm-session-batch2.md).

## Objetivo

Reduzir a manutenção e o tempo de diagnóstico dos drivers Santander, Fontecred,
Bradesco e Pan Portal sem tornar a submissão de uma simulação financeira dependente
de decisões não determinísticas.

O resultado esperado é:

1. falhas de portal sempre diagnosticáveis por trace, evento e screenshot;
2. sessão quente validada e persistida com segurança;
3. seletores com alternativas semânticas reutilizáveis;
4. IA, quando habilitada, limitada a sugerir ou reencontrar elementos;
5. experimentos de browser/WAF isolados por provedor e protegidos por flag.

## Baseline existente — não reinventar

- `app/motor/playwright_base.py`: launch Chromium, context vanilla/stealth,
  `storage_state`, detecção de WAF e screenshots.
- `app/sessao_browser.py`: path canônico por `(cliente_id, provedor)` e classificação
  de sessão quente.
- `app/processamento.py`: deadline, retries, eventos e concorrência máxima de dois
  browsers.
- Os quatro drivers têm parsers de fixture e smoke scripts `scripts/probe_*.py`.
- Screenshots de eventos já são persistidos para atravessar Machines Fly.
- O Motor está fixado em `playwright==1.49.*`; qualquer upgrade exige branch/canário
  próprio e rebuild do Chromium correspondente.

## Guardrails obrigatórios

1. A IA nunca confirma nem envia proposta, aceita condição financeira ou escolhe
   prazo/entrada em nome do usuário.
2. CAPTCHA/2FA continua sendo `IntervencaoNecessaria`; não implementar solver.
3. Nunca enviar DOM, trace ou screenshot com CPF, celular, credencial ou dados
   financeiros para terceiro sem avaliação de LGPD, contrato e autorização explícita.
4. Não registrar valor preenchido em log/evento de locator.
5. Não migrar os quatro drivers na mesma entrega.
6. Toda mudança deve ter flag de rollback e smoke live por um provedor antes do rollout.

## Arquitetura alvo

```text
Driver determinístico
       │
       ▼
Ação resiliente (nome lógico)
       ├─ locator semântico principal
       ├─ alternativas conhecidas
       └─ falha
            ├─ trace + screenshot + código sanitizado
            ├─ healer em shadow sugere elemento
            └─ intervenção manual quando necessário
```

## Fase 0 — Baseline e contrato

- [ ] Medir por provedor, em pelo menos 10 execuções de laboratório:
  - sucesso de abertura e login;
  - sessão quente/fria/expirada;
  - `portal_bloqueado`, CAPTCHA, timeout e `campo_nao_encontrado`;
  - duração p50/p95 e etapa da falha.
- [ ] Congelar os códigos de erro atuais e criar mapa de classificação comum.
- [ ] Definir quais ações são apenas navegação/preenchimento e quais são ações
  financeiras proibidas para IA.
- [ ] Registrar uma fixture sanitizada adicional para cada layout live observado.

**Aceite:** baseline consultável e lista de ações críticas aprovada antes de refatorar.

## Fase 1 — Trace e sessão endurecida

### Trace Playwright

- [ ] Adicionar métodos comuns de início/finalização de trace em
  `PlaywrightBankDriver`.
- [ ] Configurações:
  - `MOTOR_TRACE_MODE=off|on-failure` (default inicial `off`, canário `on-failure`);
  - `MOTOR_TRACE_DIR=data/traces`;
  - `MOTOR_TRACE_RETENTION_DAYS=3`.
- [ ] Em sucesso, finalizar sem reter artefato; em falha, salvar
  `{simulacao_id}/{provedor}.zip`.
- [ ] Emitir `trace_capturado` com path interno, nunca com conteúdo do trace no log.
- [ ] Não reutilizar `screenshot_conteudo` para trace: ZIP pode ser grande e conter PII.
- [ ] Antes de disponibilizar trace fora do worker, criar armazenamento privado,
  retenção curta, RBAC e auditoria próprios.

### Sessão

- [ ] Atualizar Playwright em branch isolada e rodar toda a suíte antes do rollout.
- [ ] Remover ou tornar coerentes UA/Client Hints fixos com a versão real do Chromium.
- [ ] Persistir `storage_state` incluindo IndexedDB, após o upgrade suportar a opção.
- [ ] Gravar em arquivo temporário e substituir o state de forma atômica.
- [ ] Serializar gravações concorrentes do mesmo `(cliente_id, provedor)`.
- [ ] Não engolir silenciosamente erro de gravação; emitir evento sanitizado.
- [ ] Salvar após um marcador autenticado confiável e renovar ao final do fluxo estável.
- [ ] Se havia state mas o portal voltou ao login, emitir `sessao_expirada`, fazer login
  frio e sobrescrever o state somente após confirmar autenticação.

**Aceite:** toda falha live do canário gera trace; state inválido não derruba o driver;
duas execuções válidas consecutivas reutilizam login; nenhum segredo aparece em log/API.

## Fase 2 — Ações resilientes determinísticas

Criar `motor-simulacao/app/motor/resilient_actions.py` com um contrato como:

```python
CampoSpec(
    nome="cpf_cliente",
    candidatos=[
        PorRole("textbox", name="CPF"),
        PorLabel("CPF"),
        PorCss("[formcontrolname='cpf']"),
        PorCss("input[name='cpf']"),
    ],
)
```

Operações iniciais:

- [ ] `preencher(campo, valor, candidatos)`;
- [ ] `clicar(acao, candidatos)`;
- [ ] `selecionar(campo, opcao, candidatos)`;
- [ ] `aguardar_estado(etapa, marcadores)`;
- [ ] `fechar_overlay(tipo, candidatos)`.

Regras:

- [ ] Preferir role, label, `formcontrolname`, `name` e id estável.
- [ ] Evitar XPath posicional e classes CSS geradas.
- [ ] Validar `visible`, `enabled` ou `editable` antes da ação.
- [ ] Validar o valor após preencher quando o componente permitir.
- [ ] Depois de clicar, aguardar marcador específico da próxima etapa.
- [ ] Substituir gradualmente `wait_for_timeout` por condições observáveis.
- [ ] Emitir `locator_fallback_usado` somente com provedor, etapa e nome lógico.
- [ ] Se todos falharem, lançar código específico com trace; não usar `force=True`
  automaticamente.

Ordem de adoção:

1. Fontecred — modais e componentes dinâmicos;
2. Bradesco — login/reCAPTCHA, overlays e etapas;
3. Santander;
4. Pan Portal.

**Aceite por banco:** testes de fixture verdes, nenhum resultado financeiro alterado,
ações críticas com pelo menos dois candidatos e smoke live aprovado.

## Fase 3 — Healer de locator opcional

Criar uma interface que não acople os drivers diretamente a Stagehand/Skyvern:

```python
class LocatorHealer:
    def sugerir(self, page, acao, descricao):
        ...
```

- [ ] Configurar `MOTOR_LOCATOR_HEALER=off|stagehand` (default `off`).
- [ ] Configurar `MOTOR_LOCATOR_HEALER_MODE=shadow|assistido` (default `shadow`).
- [ ] Em `shadow`, chamar somente depois de todos os candidatos conhecidos falharem.
- [ ] Persistir sugestão sanitizada como candidata para revisão humana.
- [ ] Não promover seletor automaticamente para produção.
- [ ] Em modo assistido, permitir somente ações explicitamente allowlisted.
- [ ] Bloquear `enviar_simulacao`, `confirmar_proposta`, escolha de prazo/entrada e
  qualquer aceite financeiro.
- [ ] Falha ou indisponibilidade do healer deve cair no diagnóstico normal, não quebrar
  o driver.

Projetos a avaliar no spike:

- [Stagehand Python](https://github.com/browserbase/stagehand-python) — primeira opção
  para recuperação híbrida de ações;
- [Skyvern](https://github.com/Skyvern-AI/skyvern) — alternativa visual mais pesada;
- [Browser Use](https://github.com/browser-use/browser-use) — somente para sessão/login
  assistido, não para o fluxo financeiro determinístico.

**Aceite:** zero submissões feitas por IA, custo/latência medidos e nenhuma chamada ao
healer quando locator conhecido funciona.

## Fase 4 — Canário de browser/WAF

- [ ] Criar seleção de launcher por provedor, mantendo Playwright oficial como default.
- [ ] Fazer spike com [Rebrowser Playwright](https://github.com/rebrowser/rebrowser-playwright)
  em um único portal com bloqueio reproduzível.
- [ ] Avaliar [Camoufox](https://github.com/daijro/camoufox) somente se o primeiro spike
  não resolver e o portal for compatível com Firefox.
- [ ] Comparar abertura, login, CAPTCHA, `portal_bloqueado`, duração e RAM.
- [ ] Revisar termos do portal, segurança e manutenção antes de produção.
- [ ] Nunca combinar o canário com aumento de concorrência no mesmo rollout.

**Aceite:** evidência de melhora mensurável sem regressão funcional; rollback por flag
testado; decisão documentada por provedor.

## Testes obrigatórios

| Tipo | Cobertura |
|---|---|
| Unit | prioridade de locator, fallback, falha total, healer off/shadow |
| Sessão | quente, expirada, state corrompido, IndexedDB, gravação atômica |
| Trace | criado na falha, descartado no sucesso, retenção e path seguro |
| Segurança | senha/CPF/state/DOM não aparecem em evento ou log |
| Driver | contratos comuns + fixtures existentes por provedor |
| Live gated | um canário por vez usando `scripts/probe_*.py` |

Arquivos de teste esperados:

- `tests/test_resilient_actions.py`;
- `tests/test_trace_browser.py`;
- extensão de `tests/test_playwright_base.py`;
- extensão de `tests/test_sessao_browser.py`;
- testes contratuais nos quatro `test_*_driver.py`.

## Métricas e eventos

- `locator_fallback_usado`;
- `locator_healer_sugeriu` / `locator_healer_falhou`;
- `sessao_expirada` / `sessao_gravacao_falhou`;
- `trace_capturado`;
- `waf_detectado`;
- taxa de sucesso e duração por provedor;
- CAPTCHA e WAF por provedor;
- custo e latência do healer, sem labels de alta cardinalidade ou PII.

## Corte recomendado para o primeiro incremento

Implementar somente:

1. trace em falhas;
2. sessão validada, IndexedDB e gravação atômica;
3. `resilient_actions.py`;
4. migração de Fontecred e Bradesco;
5. métricas e eventos.

Stagehand, Rebrowser e Camoufox permanecem em backlog/canário. Esse corte reduz o
tempo de diagnóstico e a fragilidade dos seletores sem colocar IA ou browser
experimental no caminho financeiro principal.

## Rollout e rollback

1. Unit/fixture em CI.
2. Smoke local com credencial de laboratório.
3. Canário de um provedor e uma loja.
4. Observar no mínimo 10 execuções, incluindo sessão fria e quente.
5. Expandir por provedor, nunca todos ao mesmo tempo.

Rollback:

- `MOTOR_TRACE_MODE=off`;
- `MOTOR_LOCATOR_HEALER=off`;
- launcher oficial Playwright por default;
- manter selectors antigos disponíveis durante o canário;
- `MOTOR_BROWSER_CONCURRENCY=1` se houver pressão de WAF/recurso.

## Critérios finais de conclusão

1. Falha live tem diagnóstico suficiente sem reproduzir às cegas.
2. Sessão quente é validada, renovada e salva sem corrupção concorrente.
3. Mudança simples de label/estrutura pode ser absorvida por alternativa conhecida.
4. IA não toma decisão financeira e pode ser desligada sem afetar o driver.
5. Browser alternativo só entra onde houver ganho medido e revisão explícita.
6. Os quatro drivers mantêm resultados e códigos de negócio compatíveis.

