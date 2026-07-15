# Lições Playwright — Fontecred

> **Status em 2026-07-15:** driver Fontecred LIVE, validado localmente e no worker Fly/Xvfb.
> Produção `motor2037` versão 12, health passing; suíte do Motor com **147 testes verdes**.
> Ler junto com `2026-07-13-playwright-licoes-santander.md` antes de implementar outro banco.

## Escopo entregue

O segundo driver Playwright real do Motor automatiza o portal do lojista Fontecred:

1. login por e-mail e senha, ou reaproveitamento de `storage_state` válido;
2. confirmação do Dashboard autenticado;
3. fechamento do modal **COMUNICADOS**;
4. abertura de `clientes/criarComProposta`;
5. CPF, nascimento e celular;
6. resolução do veículo pela placa;
7. valor, entrada, prazo e autorização SCR;
8. envio da simulação, modal PEP e oferta de proteção;
9. leitura das parcelas e da entrada mínima devolvida pelo portal.

O Fontecred exige celular e placa. Ausência desses dados deve ser rejeitada antes de abrir o browser,
com códigos estáveis como `celular_obrigatorio` e `placa_obrigatoria`.

## Incidente e causa-raiz

### Sintoma visual enganoso

Os screenshots de falha mostravam o Dashboard com o modal COMUNICADOS aberto. A primeira hipótese foi
que o clique no `X` havia falhado. Isso ocorreu em um fluxo antigo, mas não explicava todos os jobs.

A timeline foi a evidência decisiva:

```text
browser_iniciando
browser_pronto
falha_inesperada
```

Como `login_confirmado` não aparecia, a exceção acontecia **antes** de `_fechar_comunicados`. Portanto,
o modal visível no screenshot era o estado final da página, não necessariamente a etapa que falhou.

### Diferença entre sessão fria e sessão quente

- No teste local, o `storage_state` estava expirado: o portal mostrou o formulário e o login normal
  passou.
- No worker, o `storage_state` continuava válido: navegar para `/login` redirecionava diretamente ao
  Dashboard com COMUNICADOS.
- O portal mantém conexões abertas. `goto(..., wait_until="networkidle")` podia expirar mesmo com o
  Dashboard pronto.
- Após o timeout, o driver tentava navegar novamente e procurar e-mail/senha numa tela já autenticada;
  essa procura expirava e virava `portal_falhou`.

**Regra permanente:** todo banco com sessão persistida deve testar separadamente:

1. login frio, com formulário;
2. login quente, com redirect automático;
3. `networkidle` expirado, mas marcador autenticado já visível.

Nunca trate timeout de navegação como prova de que a página não carregou.

## Correções aplicadas

### Reconhecimento pós-login

O driver considera a área autenticada quando encontra um destes sinais:

- URL fora de `/login`;
- título `COMUNICADOS` visível;
- título `Dashboard` visível.

Se `networkidle` expirar, ele verifica esses marcadores antes de navegar novamente. Quando a sessão já
está válida, pula os campos de credencial, espera o DOM e segue para o modal.

### Modal COMUNICADOS

O fechamento não é considerado concluído só porque `click()` ou `Escape` não levantou exceção.

Fluxo obrigatório:

1. esperar o título COMUNICADOS ficar visível;
2. tentar botão com nome `Fechar`;
3. tentar seletores Bootstrap 5 (`.btn-close`, `[data-bs-dismiss="modal"]`) e legados;
4. usar `Escape` como último fallback;
5. esperar o título ficar `hidden`;
6. verificar novamente `is_visible()`;
7. se persistir, retornar `comunicados_nao_fechou`.

### Navegação e ritmo

- A URL de Nova Proposta usa `wait_until="commit"` para não perder uma navegação que já começou.
- Depois do commit, o driver espera `domcontentloaded`, `document.readyState` e o campo CPF ficar
  visível e acionável.
- `click(trial=True)` confirma actionability sem alterar a tela.
- Nascimento, celular, placa, seleção do veículo e botão Simular têm esperas explícitas.
- Depois de Simular, o driver espera PEP, proteção, erro ou cards de parcela. A espera final continua
  responsável por estabilizar os cards.

Prefira marcador real da próxima etapa a sleeps longos. Uma pausa curta continua válida apenas para
animação visual ou debounce conhecido.

## Observabilidade obrigatória

O Fontecred registra etapas sanitizadas e prints protegidos por job:

```text
browser_iniciando
browser_pronto
login_confirmado
comunicados_fechados
proposta_aberta
dados_preenchidos
simulacao_enviada
ofertas_recebidas
parcelas_lidas
```

Falhas conhecidas usam `falha_portal`; exceções imprevistas usam `falha_inesperada` com somente o tipo
da exceção, nunca HTML, CPF, placa, e-mail ou senha. Screenshots ficam no diretório do job, passam por
RBAC/tenancy no Portal e seguem a retenção configurada.

Diagnóstico por sequência:

| Última etapa | Investigar primeiro |
|---|---|
| `browser_pronto` | navegação/login, sessão persistida, captcha, timeout de locator |
| `login_confirmado` | modal COMUNICADOS e overlay |
| `comunicados_fechados` | URL/menu da proposta e campo CPF |
| `proposta_aberta` | carregamento de CPF/nascimento/celular/placa |
| `dados_preenchidos` | botão Simular, PEP, SCR e proteção |
| `simulacao_enviada` | erro bancário, cards e parser |

Não diagnosticar apenas pelo screenshot: correlacionar sempre com a última etapa persistida.

## Validação que encerrou o incidente

O smoke foi executado dentro do próprio worker Fly, usando Chromium headed + Xvfb e o `storage_state`
persistido, sem preencher cliente e sem enviar proposta:

```text
PORTAL_AUTENTICADO=True
SESSAO_REUTILIZADA=ok
MODAL_ANTES=True
MODAL_DEPOIS=False
SMOKE_WORKER=ok
```

Depois disso, uma simulação real iniciada pelo usuário concluiu com sucesso.

Commits do endurecimento:

- `ce75e60` — fechamento do modal, navegação resiliente e timeline por etapa;
- `8ac4b92` — esperas por DOM/actionability e ritmo conservador;
- `1165690` — reconhecimento e reaproveitamento da sessão autenticada.

## Checklist para o próximo banco

1. Confirmar API antes de escolher RPA.
2. Mapear sessão fria, quente, expirada, captcha e credencial rejeitada.
3. Não usar `networkidle` como único sinal de sucesso.
4. Definir marcadores autenticados específicos do banco.
5. Registrar evento antes/depois de cada fronteira importante.
6. Para cada modal, validar `visible → ação → hidden`.
7. Esperar o próximo campo ficar visível e acionável antes de preencher.
8. Testar local headed e no mesmo Chromium/Xvfb da produção.
9. Fazer smoke sem proposta quando o objetivo for apenas login/modal.
10. Manter mensagens, logs e nomes de arquivos sem PII.
11. Validar retry: duas tentativas não podem esconder a etapa original da falha.
12. Só publicar após teste focado, suíte completa e health check do worker.

## Limitações ainda abertas

- Seletores do portal podem mudar sem aviso; timeline e screenshots são parte do contrato operacional.
- `testar-login` administrativo ainda é placeholder; o smoke e a simulação real continuam sendo a
  validação prática.
- API e worker ainda compartilham uma Machine de 2 GB.
- Fan-out por banco e workers sob demanda continuam planejados, não implementados.
- `storage_state` ainda depende do volume da Machine; object storage privado é necessário antes de
  escalar para múltiplos workers.
