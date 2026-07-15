# Lições Playwright — Pan portal (go!PAN Veículos)

> **Status 2026-07-15:** `PanPortalDriver` LIVE, validado localmente pelo dono fim-a-fim
> (preenche, simula e lê as ofertas). Ler junto com as lições Santander e Fontecred antes do
> próximo banco. Commits: `b3a94b1` (fluxo/âncoras) e `fd1a31a` (leitura de ofertas).

## Escopo entregue

`PanPortalDriver` (`app/motor/pan_portal.py`) automatiza o portal do lojista
`veiculos.bancopan.com.br` (marca **go!PAN**), para lojas que só têm usuário/senha (sem api_key
de developer). Convive com o `PanDriver(ApiBankDriver)` OpenAPI: um **dispatcher** em `drivers.py`
(`_pan_dispatch`) escolhe **API** quando a config OpenAPI está completa e **portal** quando só há
usuario+senha. Para isso, os campos de API em `providers.py` viraram **opcionais** (só
usuario+senha são obrigatórios para o provedor "pan" resolver).

Fluxo: login → (banner LGPD) → CPF do cliente (`/captura/inicio`) → comparador (celular, placa,
UF licenciamento, valor) → Simular → leitura das ofertas (parcela, financiado, entrada).

## O portal é Angular + web components `pan-mahoe` (lição central)

Quase todo problema veio disso. Regras que ficaram:

1. **Campos não têm nome acessível.** O `<input>` mahoe tem `formcontrolname`, `id` e um atributo
   custom `label="..."`, mas **não** um `<label>`/aria que `get_by_role("textbox", name=...)`
   enxergue. Ancorar por `#id` / `input[formcontrolname='...']` / `input[placeholder*='...']`.
   Exemplos reais: usuário `#login`; senha `input[type=password]`; CPF por placeholder
   `000.000.000-00`; celular `Digite o celular...`; placa `Digite a placa...`.
2. **Ancorar sempre no `<input>` interno, nunca no wrapper.** `get_by_placeholder(...)` casa o
   componente `<pan-mahoe-input>` (que também carrega o `placeholder`), e ele **não é preenchível**
   → `fill` quebra com *"Element is not an <input>…"*. Usar `input[placeholder*='...']`.
3. **Máscaras comem caractere em digitação rápida.** Campos com máscara (CPF, celular, placa)
   inserem `( ) - .` sozinhos e perdem dígito no `type` rápido. Solução (`_digitar_mascarado`):
   mandar **só os dígitos**, digitar devagar (`press_sequentially`), **conferir** os dígitos lidos
   e refazer mais devagar (110 → 200 → 300 ms). Limpeza robusta: `Ctrl+A`+`Delete` (o `fill('')`
   às vezes não limpa a máscara).
4. **Moeda: auto-detectar a máscara.** O campo "Venda" não era máscara de centavos; mandar
   `valor*100` gera zero a mais. `_digitar_valor` tenta o inteiro em reais (`21900`) e, se o número
   lido não bater, a forma em centavos (`2190000`), conferindo pelo **número** parseado.

## Ler as ofertas: o que estava oculto (lição decisiva)

Depois de Simular, a oferta vai para o painel **"Comparador de ofertas"** (à direita) e o form da
esquerda **reseta**. O card mostra parcela, financiado, status, entrada e venda — mas o driver não
conseguia ler e estourava 60 s.

Causas e soluções, confirmadas com o HTML real do card:

- **A parcela ("48x R$ 800,00") não entra no `inner_text`.** Ela vive num componente custom
  `<app-custom-select id="installment-select">`, num `<span>` dentro de `[role="option"]`, e o menu
  fica **colapsado/oculto** (`aria-expanded="false"`). `inner_text` só pega texto **visível**;
  `querySelectorAll('select')` não acha (não é `<select>` nativo). **Solução:** extrair por
  **`textContent`** dos `[role="option"]` / `app-custom-select` (textContent ignora visibilidade),
  reforçado por um **locator do Playwright** (`get_by_text(/\d+x.*R\$/)`).
- **Entrada e Venda são `<input mask=currency>`** (`id=requestedEntry` / `id=saleValue`): o valor
  não está no `inner_text` (é `.value`). Capturar o **value cru** de cada input + um **rótulo
  curto** ao lado (`<label>`, atributo `label`, ou irmão com texto ≤ 24 chars) — nunca o texto do
  card inteiro (isso fazia o regex de entrada grudar num número errado, ex.: `204.139,00`).
- **`get_by_text` não serve para o gatilho de "pronto"** quando o alvo está oculto. A espera das
  ofertas (`_passo_aguardar_ofertas`) é **por condição**: para quando as parcelas parseadas
  (via `textContent`) **estabilizam** entre duas leituras **e** há sinal de conclusão visível
  (`Aprovado`/`Financiado`). Retorna no instante em que fica pronto — o timeout é só o teto.

`financiado` é lido do texto exibido (`Financiado: R$ 15.116,8`, aceitando 1–2 casas), com fallback
`valor − entrada`.

## Login e navegação

- **`networkidle` nunca estabiliza** (chat/analytics mantêm conexões) → usar `domcontentloaded` e
  esperar o próprio campo de login aparecer. (Mesma lição do Fontecred.)
- **Decidir login pela PRESENÇA do campo, não pela URL.** Heurística de "URL fora de /login = logado"
  pulava o login inteiro quando a rota não continha "/login". Se o `#login` existe, loga; se não
  existe, assume sessão autenticada.
- **Banner LGPD "Permitir todos os cookies"** intercepta cliques. Fechar antes de logar e antes de
  preencher (`_fechar_got_it` cobre "Permitir todos os cookies", "Rejeitar cookies", "Got it!", etc.).
- **Botões ficam `disabled`** até o form validar — esperar habilitar (`Entrar`, `Simular`).

## Diagnóstico que fechou o incidente

`MOTOR_PAN_PORTAL_DEBUG=1` grava em `data/screenshots/pan_ofertas_debug.txt` **o texto exato que o
parser enxerga** na tela de ofertas. Foi o que revelou que a parcela não estava em lugar nenhum do
texto (só no componente oculto) e que cards antigos de rodadas com bug (`×100`) poluíam o comparador.
Correlacionar sempre com a timeline (`browser_pronto → login_confirmado → dados_preenchidos →
simulacao_enviada → ofertas_recebidas → parcelas_lidas`), não só com o screenshot.

## Códigos de erro estáveis

`celular_obrigatorio` / `placa_obrigatoria` / `valor_obrigatorio` (pré-browser), `credencial_invalida`
(login), `pan_sem_oferta` (sem parcela legível), `portal_bloqueado` / `portal_falhou`,
`portal_simulacao_erro`.

## UF licenciamento

Dropdown "UF licenciamento" no comparador (mostra a sigla atual, ex.: SP). O driver só troca quando a
solicitação informa `veiculo.uf_licenciamento`; senão mantém o default do portal. Âncora por texto
"UF licenciamento" (case-insensitive) + o elemento de seleção seguinte; escolhe pela sigla ou nome
por extenso. Testado ao vivo com RJ.

## Checklist para o próximo banco (delta go!PAN)

1. Se o portal usar web components (mahoe/mat/etc.), esquecer nome acessível: `id`/`formcontrolname`/
   `placeholder`, e sempre o `<input>` interno.
2. Máscara → dígitos + digitação lenta + **conferir e refazer**; moeda → auto-detectar reais×centavos.
3. Resultado pode estar em componente **colapsado/oculto** ou em `<input>`: usar **`textContent`** e
   **value de input**, não só `inner_text`.
4. Espera final **por condição** (estabiliza + sinal de conclusão), nunca sleep longo.
5. Ligar um **dump de debug** do texto lido cedo — economiza horas de adivinhação.
6. `networkidle` é armadilha em portais com chat/analytics.
