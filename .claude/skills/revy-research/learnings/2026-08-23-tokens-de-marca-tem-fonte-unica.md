---
gatilho: mudar cor, fonte ou token de marca
produto: shared/brand
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# A fonte unica e `shared/brand/revy-tokens.css`, e as copias sao geradas

Cada produto e um deploy Fly independente, entao a folha de marca e **copiada** para os
quatro front-ends em vez de buscada por HTTP (uma folha remota faria o Control fora do ar
despintar o catalogo). Para mudar qualquer valor: edite `shared/brand/revy-tokens.css` e
rode `python shared/brand/sync_tokens.py` (no Mac, `python3`). Editar uma copia
(`*/static/css/revy-tokens.css`) quebra a suite de proposito.

Testes em `shared/brand/tests`: contraste AA, sincronia das copias, guarda contra o azul
antigo, logo sem `<text>`.

Armadilhas que so aparecem na execucao:

- O Control tem **duas** formas de estado, nao uma: `.status` e a hifenizada
  `.status-pill.status-ativa` (de `app/rotulos.py`), de especificidade maior. Mexer so na
  primeira deixa metade dos estados sem efeito, em silencio.
- O `revy-tokens.css` copiado contem o bloco de tema escuro inteiro. Teste que varra "modo
  escuro em superficie publica" precisa excluir esse nome de arquivo, senao acusa para
  sempre o proprio arquivo gerado.
- O painel preto do login nao pode derivar de `--ink`: no tema escuro `--ink` e quase
  branco e o painel inverte.

O acento e o **verde racing** desde 08/08/2026 (o azul anterior foi substituido, e ha teste
que falha se ele voltar).
