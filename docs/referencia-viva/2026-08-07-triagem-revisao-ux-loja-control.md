# Triagem da revisão de UX — Revy Loja e Revy Control (2026-08-07)

Uma revisão de produto varreu os dois shells procurando o que **retirar**, **melhorar** e
**adicionar**, e produziu 45 achados com código (`L*` Loja, `C*` Control, `I*` incoerências
entre os dois). O dono do produto triou item a item.

Este documento existe por um motivo específico: **registrar o que foi recusado**, para que
os mesmos pontos não voltem como sugestão nova a cada passada no código. O que foi aceito
está no Git (main `729120b..e06d9e5`, LIVE `app2037` v115).

Catálogo interativo usado na triagem:
<https://claude.ai/code/artifact/684b735c-c87d-448f-8434-d56222156cd7>

## Aceito e entregue (32 itens)

### Revy Control — visão geral (`/trafego/app/control/dashboard`)

| Código | O que mudou |
|---|---|
| `C1` | Painel "Destaques" removido — "Ticket médio da rede" repetia o card do topo, do mesmo campo. "Melhor loja" subiu para a faixa de KPIs. |
| `C2` | Faixa "Contagens por status" removida — "Ativas" já está no card 1 e o resto sai da coluna Status da tela Lojas. |
| `C3` `C4` | Tabela "Lojas" (7 colunas) e coluna "Falhas" removidas — replicavam Control › Lojas, que é item de menu próprio. |
| `C9` | Painel "Aquisição Google (7 dias)" removido da visão de negócio da rede. |
| `C10` | `h1` era "Prontidão das lojas" enquanto o menu dizia "Visão geral". |
| `C18` | Prontidão distingue **Bloqueio** (impede ativar) de **Alerta**; antes tudo saía no mesmo chip âmbar. |
| `C20` | Linhas de "Desempenho por loja" abrem a ficha — era a única tabela do Control sem saída. |
| `C21` | Filtro de período (`?inicio=&fim=`), igual ao da Revy Loja. Janela padrão `[1º do mês, hoje]`; o Δ% compara a **janela anterior de mesmo tamanho** (mês inteiro contra mês inteiro fazia o delta do dia 1 despencar todo mês). |
| `C22` | A tela declara o período e que a venda conta por `confirmada_em`. |
| — | "Alterações recentes" (log de auditoria cru) removido. `recent_audit` continua no domínio e na API. |

### Revy Control — navegação, rótulos e ficha da loja

| Código | O que mudou |
|---|---|
| `C11` | `page_title` em Medição, ROI, Cliques do WhatsApp, Conferir Pixel, Campanhas, detalhe/form de campanha e gastos em lote — a topbar escrevia "Control" em ~6 telas. |
| `C12` | `h1` casa com o menu: "Tráfego"→"Medição", "Auditoria CTWA"→"Cliques do WhatsApp", "Auditoria Pixel / CAPI"→"Conferir Pixel". |
| `C13` | `revy-trafego/app/rotulos.py`: mapa único de rótulos, registrado nos **dois** ambientes Jinja (`app.main` e `app.web.control_ui`). Status da loja, papel e estado de acesso deixaram de sair como enum cru. |
| `C15` | "se faltar, eu aviso o que é" — único lugar do produto onde o sistema falava em primeira pessoa. |
| `C16` | Seção "Loja" do menu virou "Loja selecionada" e perdeu "Todas as lojas". |
| `C5` `C6` | Tela `/app` "Escolha a loja" e o campo livre de slug removidos (ver ressalva abaixo). |
| `C7` | Aba "Auditoria" da ficha removida — mostrava `event.action` e `result.value` crus. |
| `C19` | **Painel de Prontidão na ficha da loja**: o dashboard linkava "o que falta" para uma página que não respondia nada disso; `build_readiness_report` só era usado como mensagem de erro na ativação. |
| `I3` | Status da loja usa a mesma pill em toda parte (a tela Lojas usava `.status-pill`, o dashboard usava `.status`). |
| `L3` | **Ajustes › Integrações** criado no Control, espelhando a página que a Loja já tinha — lojista e dono da operação são pessoas diferentes olhando o mesmo status. |

### Revy Loja

| Código | O que mudou |
|---|---|
| `L1` | Rodapé "Atalhos" removido — apontava para `/app/vendas`, `/app/leads`, `/app/funil`, `/app/financeiro` e "Painel clássico", as telas legadas que o shell substitui. |
| `L4` | Painel "Reservas e vendas recentes" removido — quatro colunas, nada clicável, sem link para o veículo. |
| — | Painel "Cadastro › Pendências" da visão do estoque removido (pedido direto do dono). |
| `L7` | Bloco "Pendências" de Vendas só aparece quando há pendência; o estado vazio anunciava roadmap interno. |
| `L9` | `page_title` nas páginas do shell que faltavam — Resultado, Situação do estoque, Agente, Números de WhatsApp e Equipe escreviam "Ajustes" na topbar. |
| `L10` | Badge de canal saiu de um `<style>` inline com `rgba(255,255,255,…)` escrito para o tema escuro; desde a paleta clara default ele era branco sobre branco. |
| `L11` `L18` | Coluna **"Aguardando há"** na fila: a tela mostrava a última mensagem mas nenhuma data/hora — não dava para saber se o cliente esperou 5 minutos ou 5 dias. Helper `tempo_relativo()` em `portal-gestao/app/main.py`. |
| `L12` | Dois "Visão geral" no menu viraram "Resultado" (Vendas) e "Situação do estoque" (Estoque). |
| `L13` | "Catálogo e vitrine" (CTA do WhatsApp + link do catálogo) mudou de Ajustes › Números de WhatsApp para **Estoque › Vitrine**; a configuração da vitrine estava partida entre duas seções. "Ordem na vitrine" virou "Vitrine". |
| `L15` `L16` | Jargão removido: "API de estoque", "migração completa do shell", "status confirmada no período", "Workspace por telefone do cliente", "chatbot" (o menu diz "agente"). |
| `L19` | "Leads no período", "Atendidos" e "Vendas vinculadas" abrem a fila filtrada — o funil parava no número. |
| — | Redesign da página do Agente (barra dividida agente × handoff, série diária preenchida do dia 1 até hoje) e ícone do Agente no menu. |
| — | Conversa do lead no Control com bolhas e separador de dia, reusando a thread da Revy Loja. |

## Recusado pelo dono — não propor de novo (13 itens)

São decisões de produto, não pendências técnicas. Ao mexer nessas telas, deixe como está.

| Código | O que foi recusado |
|---|---|
| `L2` | Remover o card "Google Ads — Indisponível" fixo na visão de Vendas. |
| `L5` | Remover o aside "Veículos" que duplica dois botões na visão do Estoque. |
| `L6` | Remover de vez o "Simulações — em construção" (aceito apenas demover para o rodapé). |
| `L8` | Remover a rota órfã `/app/loja/catalogo`. |
| `L14` | Trocar o placeholder `app2037.fly.dev` no link do catálogo. |
| `L20` | Filtro "só pendências" na lista de veículos. |
| `C8` | Tirar Acessos de item de menu de primeiro nível no Control. |
| `C14` | Unificar as duas formas de ativar a loja (botão "Ativar loja" + select de estado). |
| `C17` | "Conversão" mistura janelas (vendas do mês ÷ leads acumulados). |
| `I1` | Seletor de loja mostra slug na Loja e nome no Control. |
| `I2` | "Acessos bancários" (Loja) vs "Acessos dos bancos" (legado). |
| `I4` | O bot tem quatro nomes: "Agente", "Agente de atendimento", "chatbot", "o bot". |
| `I5` | Cabeçalho fora do padrão em Integrações (`section.page-head` em vez de `div.page-heading`). |

## Ressalvas do que foi entregue

- **`C5` não é remoção total.** `/app` encaminha para Visão geral (ou Lojas, sem a flag de
  dashboard), mas `exigir_loja` devolve todo mundo para `/app` quando não há loja escolhida —
  redirecionar dali para uma página que exige loja fecharia um laço. Com o Control desligado
  e sem loja selecionada, `home.html` ainda renderiza, agora como **estado vazio** apontando
  para o seletor da sidebar, não mais como formulário.
- **`C6` tirou o único bootstrap do modo legado.** O campo livre de slug era a forma de
  abrir uma loja que ainda não tem dados quando `REVY_CONTROL_RBAC_ENABLED=0`. Se esse
  caminho voltar a ser necessário, ele precisa reaparecer atrás de uma tela de admin.
- **`C7` mudou o teste, não a garantia.** Os testes que liam código de auditoria no HTML
  passaram a ler a trilha (`AuditoriaEvento`), que é onde ela mora. O escopo por gestor
  continua coberto em `revy-trafego/tests/test_control_dashboard.py`.

## Aberto

- ~~**Os KPIs de venda da Visão Geral contam 0 em produção**~~ — corrigido em 07/08
  (`projetar_venda` resolve o `loja_id` + migration `0017` religa as órfãs). `C21`/`C22`/`C20`
  só ficam visíveis em produção depois do deploy com `alembic upgrade head`.
- **Espaçamento ("gaps")**: o dono viu problemas de espaçamento nas prévias e ainda não
  localizou onde. Fila separada.
