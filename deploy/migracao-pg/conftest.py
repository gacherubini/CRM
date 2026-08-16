"""Existe só para pôr esta pasta no `sys.path` do pytest.

Os testes daqui fazem `from tipos import converter`, `from copiar import copiar`
e afins. O pytest, no modo de import default, insere no `sys.path` o diretório
do arquivo de teste — `tests/` — e não o pai. Sem este arquivo, nenhum dos
quatro módulos da ferramenta é importável e a suíte inteira morre no collect.

Ele fica vazio de propósito: não há fixture compartilhada aqui. As ferramentas
NÃO importam `app` de nenhum produto (o Portal e o Control têm ambos um pacote
chamado `app` e nenhum processo pode importar os dois), então não há nada de
ambiente para montar — elas refletem o schema do banco que o alembic criou.
"""
