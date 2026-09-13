---
gatilho: rodar comando com aspas, parenteses, pipe ou redirect via fly ssh console no Windows
produto: motor-simulacao
custo: uma sessao presa em quoting sem registrar o slot do worker novo
fonte: infra
verificado_em: 2026-09-12
---
# `fly ssh console -C` no Windows quebra com comando complexo; use stdin

O valor do `-C` passa por PowerShell → CreateProcess → parser Go → SSH, e cada
camada re-mastiga aspas. Em 12/09, todos estes formatos falharam:

- `-C 'export A=1; ... | base64 -d | python3'` → `unknown shorthand flag: 'd' in -d`
- `-C '... python3 -c "import base64,sys;exec(...)" BLOB'` → `malformed resolve command`
  (o `;` vira separador e o resto vira "host")
- `echo "L1" > /tmp/x.py` dentro do `-C` → `unknown shorthand flag: '>' in ->`
- `python3 -c "print(123)"` → `sh: Syntax error: "(" unexpected` (aspas duplas
  internas somem no caminho e o parêntese chega nu no dash)

O que passa ileso: espaços, aspas simples, `&&`, `$VAR` — ex.:
`fly ssh console -a app2037 -C "sh -lc 'cd /srv/motor && ... python3 --version'"`.

Receita para comando complexo (12/09, slot `motrix` registrado assim): grave o
script remoto com bytes exatos e envie por stdin, com `-C` de um token só:

    Get-Content -Raw remote.sh | fly ssh console -a app2037 -C 'sh -s'

O `remote.sh` pode ter heredoc, `export DATABASE_URL=$MOTOR_DATABASE_URL`,
`PYTHONPATH=/srv/motor` e `python3 - <<'PY'` sem restrição nenhuma — stdin não é
re-parseado por ninguém. Detalhe: arquivo escrito no Windows chega com CRLF e o
dash reclama no fim (`sh: N: : not found`, exit 127) **depois** do trabalho já
ter rodado — inofensivo, mas converta para LF se o exit code importar.
