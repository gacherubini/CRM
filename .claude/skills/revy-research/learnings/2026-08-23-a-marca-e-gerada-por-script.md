---
gatilho: mexer no logo ou na assinatura da marca
produto: shared/brand
custo: 14 testes vermelhos por semanas
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# A assinatura nao se desenha a mao: gera e distribui

`shared/brand/build_marca.py` **gera** e `shared/brand/sync_marca.py` **distribui**.
Origem canonica: `shared/brand/assets/`. Destinos em `DESTINOS_MARCA`
(`shared/brand/tokens.py`): `templates/marca/` dos tres paineis, `static/marca/` (favicon
e icone de app) e `site/assets/`.

Nos templates a marca entra **inline** via `{% include %}` — e o unico jeito do
`currentColor` funcionar. Dentro de um `<img>` ela vira preta e some no tema escuro.

A geometria da assinatura (barras + Chivo 900) foi medida pixel a pixel e esta na spec de
20/08/2026; nao chute proporcao nova.

Armadilhas ja pagas:

- O Google Fonts devolve os `@font-face` em ordem **crescente** de peso. Zipar contra uma
  lista decrescente troca 900 por 500 **em silencio** — case peso com URL pelo
  `font-weight:` do proprio bloco.
- `test_app_css.py::test_template_nao_carrega_cor_propria` e o hook do impeccable varrem o
  arquivo inteiro, **comentario incluido**: citar um hex ou escrever `<img>` dentro de um
  comentario Jinja quebra o teste. Reescreva o comentario, nao afrouxe a regra.
- Os assets moram ao lado de quem os gera. Quando eles foram parar em `docs/`, uma
  reorganizacao os apagou e `test_marca.py` ficou com 14 falhas por semanas.
- Seis telas de auth carregam o simbolo inline e **nao aparecem** em grep por template de
  sidebar. Cada uma tem seu proprio `?v=`.
