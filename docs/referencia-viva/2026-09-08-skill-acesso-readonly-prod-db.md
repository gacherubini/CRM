# Skill genérica de acesso somente leitura a bancos de produção

Status: aprovado para implementação em 2026-09-08

## Decisão resumida

Criar uma skill reutilizável chamada `prod-readonly-db`, sem conhecimento de
um projeto, produto ou topologia específicos. O mesmo bundle poderá ser usado
em qualquer repositório e aceitará zero, um, dois ou quantos bancos PostgreSQL
forem cadastrados localmente por aliases.

Não haverá lista fixa de bancos no código da skill. Cada alias resolverá uma
configuração independente, fora do Git. Uma consulta sempre abrirá uma conexão
para um único alias. Se o usuário pedir vários bancos, deverá nomear a lista
finita de aliases; a skill executará cada consulta separadamente e de forma
sequencial, sem fan-out silencioso e sem join entre bancos.

A skill será PostgreSQL-first. Ela não armazenará DSNs, senhas, tokens,
cookies, nomes internos de projetos ou credenciais de aplicação. A
configuração virá do ambiente seguro do usuário, preferencialmente por serviços
libpq (`pg_service.conf`) e pelo arquivo de senhas reconhecido pela libpq ou por
um secret manager já existente.

A skill será uma proteção operacional, não a autoridade de segurança. A
garantia principal de somente leitura deverá existir no banco, em uma role
dedicada e sem privilégios de mutação ou administração. A skill adicionará
defesas contra erro: auditoria da role, alvo explícito, sessão read-only,
timeouts, validação de SQL e saída sanitizada.

## Problema que a skill resolve

Projetos podem ter arquiteturas muito diferentes: um único banco, bancos por
produto, bancos por cliente ou vários ambientes independentes. O mecanismo de
acesso não deve codificar essa topologia nem pressupor uma quantidade mínima ou
máxima de conexões.

O objetivo é permitir investigação diagnóstica autorizada em produção com o
menor acesso necessário, sem transformar o agente em operador administrativo,
sem reutilizar credenciais da aplicação e sem tornar uma configuração local
parte da skill compartilhada.

## Escopo

### Incluído

- bundle genérico em `skills/prod-readonly-db/`;
- qualquer quantidade de aliases configurados independentemente;
- uma conexão isolada por alias e suporte a uma lista explícita de aliases;
- conexão PostgreSQL por `psql`, executada por um wrapper seguro;
- preflight de identidade, destino, transporte, privilégios e limites da sessão;
- consultas diagnósticas, inspeção de schema e agregações controladas;
- referência para provisionamento e auditoria manual da role de leitura;
- acesso por TLS autenticado ou por túnel previamente aberto pelo usuário;
- operação equivalente em Windows, macOS e Linux;
- testes automatizados em PostgreSQL descartável, sem usar produção;
- validação da skill antes da instalação global.

### Fora do escopo

- conhecer nomes, domínios, schemas ou quantidade de bancos de um projeto;
- criar ou alterar roles automaticamente em produção;
- buscar, imprimir, copiar ou persistir credenciais;
- enumerar variáveis de ambiente ou secrets para descobrir bancos;
- usar credencial da aplicação como fallback;
- executar migrations, DDL, DML, jobs, rotinas mutáveis ou comandos de
  infraestrutura;
- juntar tabelas de bancos diferentes em uma consulta;
- comparar ou consolidar resultados sem que isso seja pedido explicitamente;
- oferecer suporte inicial a outros motores além de PostgreSQL.

## Arquitetura proposta

### Cadastro de alvos

Um alias é apenas um identificador local, por exemplo `billing-prod` ou
`warehouse-eu`. Ele não contém host, usuário, senha nem significado de domínio
embutido na skill.

Para cada alias, o mecanismo preferido será uma variável não secreta que aponta
para um serviço libpq:

```text
PROD_READONLY_DB_<ALIAS>_SERVICE
```

O `<ALIAS>` será normalizado para maiúsculas e underscores. O serviço conterá
host, porta, banco, usuário, TLS e demais parâmetros não secretos em
`pg_service.conf`; a senha ficará no arquivo reconhecido pela libpq (`.pgpass`
em Unix ou `%APPDATA%\postgresql\pgpass.conf` em Windows) ou em secret manager
compatível. O arquivo e suas permissões serão responsabilidade do usuário ou da
equipe de infraestrutura, fora do repositório da aplicação.

Como modo de compatibilidade, a implementação poderá aceitar:

```text
PROD_READONLY_DB_<ALIAS>_URL
```

Esse modo deverá ser explicitamente habilitado. O wrapper mapeará o valor para
`PGDATABASE` somente no ambiente do processo filho; ele nunca aparecerá em
argumentos de linha de comando, stdout, stderr ou mensagens de erro. Não haverá
fallback para `DATABASE_URL`, `DATABASE_CONNECTION_URI` ou outras credenciais
da aplicação. Por expor o segredo ao ambiente do processo, esse modo é menos
seguro que serviço libpq com arquivo de senhas e não será o padrão.

A skill não descobrirá aliases enumerando o ambiente. O usuário sempre nomeará
um ou mais aliases. Alias inexistente ou não configurado falhará fechado.

### Cardinalidade e seleção

- Não existe quantidade fixa de alvos no bundle.
- Um projeto com um banco configura um alias; com dois bancos, dois aliases; e
  assim por diante.
- Cada execução do wrapper recebe exatamente um alias.
- Um pedido com vários aliases é decomposto pela skill em execuções separadas,
  sequenciais e identificadas no relatório.
- Pedidos como “todos os bancos” exigem que o usuário forneça ou confirme a
  lista explícita; a skill não procura novos alvos.
- Uma falha em um alias não autoriza fallback para outro e não mistura saídas.
- A skill poderá ser selecionada automaticamente pelo Codex, mas só abrirá uma
  conexão quando o pedido do usuário autorizar a consulta e identificar os
  aliases. Se o pedido já for explícito, não haverá confirmação redundante.

### Fluxo de uma consulta

1. Confirmar que o pedido é diagnóstico e identificar o alias ou a lista
   explícita de aliases.
2. Ler apenas as instruções do repositório necessárias para interpretar o
   domínio; a skill não traz contexto de negócio próprio.
3. Resolver a configuração do alias sem listar ou exibir secrets.
4. Verificar transporte autenticado: TLS com `sslmode=verify-full` ou túnel
   local já autorizado e aberto.
5. Auditar destino e role antes da consulta: usuário, banco, role efetiva,
   memberships, atributos administrativos, ownership e privilégios relevantes.
6. Abrir uma transação `READ ONLY`, fixar `search_path`, `application_name` e
   timeouts conservadores.
7. Executar uma única consulta de leitura, com colunas mínimas e limite de
   linhas quando o resultado não for agregado.
8. Encerrar a sessão, sanitizar erros e resumir cada alias separadamente.

### Barreira obrigatória no banco

Para cada alvo, o owner/DBA deverá provisionar uma role dedicada de leitura. A
auditoria deverá considerar privilégios diretos, herdados e concedidos a
`PUBLIC`, não apenas `transaction_read_only`.

A role deverá ter:

- `LOGIN`, sem `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` ou
  `BYPASSRLS`;
- `CONNECT` apenas nos bancos autorizados;
- `USAGE` apenas nos schemas autorizados;
- `SELECT` apenas nas tabelas, views e sequences realmente necessárias;
- nenhum ownership de banco, schema, tabela, sequence ou rotina no escopo;
- nenhum privilégio de `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`,
  `TRIGGER`, `CREATE` ou `MAINTAIN`;
- nenhum `TEMPORARY` no banco;
- nenhum `EXECUTE` em função ou procedure não aprovada como segura;
- nenhum `SET` ou `ALTER SYSTEM` concedido sobre parâmetros de configuração;
- nenhuma membership que reintroduza privilégios proibidos;
- privilégios default revisados para objetos futuros de cada role criadora;
- `default_transaction_read_only=on` e timeouts conservadores como defesa
  adicional.

Schemas presentes no `search_path` não poderão conceder `CREATE` à role nem a
`PUBLIC`. O provisionamento e a revogação de defaults inseguros serão
documentados para execução manual e revisada; a skill não aplicará esse SQL em
produção.

Se a auditoria não conseguir demonstrar as condições necessárias, a conexão
será recusada. `transaction_read_only=on`, isoladamente, não será considerado
prova de que a credencial é somente leitura.

### Barreira na sessão e no executor

O wrapper executará `psql` com `-X` para ignorar arquivos de inicialização,
`--no-password` para nunca abrir prompt interativo e `ON_ERROR_STOP`. SQL e
comandos de sessão serão enviados por stdin; DSN, senha e texto da consulta não
aparecerão nos argumentos do processo.

A sessão usará:

- `application_name=codex-prod-readonly`;
- transação explicitamente `READ ONLY`;
- `statement_timeout`, `lock_timeout` e
  `idle_in_transaction_session_timeout`;
- `search_path` fixo em schemas confiáveis, exigindo qualificação explícita
  quando necessário;
- limite de linhas definido pelo wrapper para resultados não agregados.

A validação aceitará somente uma instrução de leitura e rejeitará, no mínimo:

- múltiplas instruções;
- DDL, DML e CTEs que modificam dados;
- `SELECT ... FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE` ou
  `FOR KEY SHARE`;
- `COPY`, `DO`, `CALL`, `VACUUM`, `ANALYZE` e `EXPLAIN ANALYZE`;
- `SET ROLE`, alterações de sessão não geradas pelo wrapper e controle de
  transação fornecido pelo usuário;
- metacomandos do `psql`, inclusive linhas iniciadas por barra invertida.

Essa validação é defesa contra erro de operação, não um sandbox SQL perfeito.
A role restrita no banco continua sendo a barreira principal, inclusive contra
consultas que chamem rotinas com efeitos colaterais.

## Tratamento de dados e falhas

- Dados pessoais, financeiros ou secretos serão consultados somente quando
  necessários ao diagnóstico, com colunas explícitas e quantidade mínima.
- Resultado grande, consulta sem limite ou pedido ambíguo deve ser refinado em
  vez de produzir um dump.
- Alias ausente, destino incorreto, TLS não autenticado, role excessiva ou
  privilégio inesperado interrompem o fluxo imediatamente.
- Falha de rede em banco privado será reportada como necessidade de túnel; a
  skill não buscará credenciais nem executará comandos de deploy.
- Erros e logs serão sanitizados para não conter DSN, senha, token, cookie,
  query sensível ou nome de variável secreta com seu valor.
- Saídas brutas temporárias não serão versionadas e serão descartadas ao fim.

## Artefatos previstos

```text
skills/prod-readonly-db/
├── SKILL.md
├── agents/openai.yaml
├── references/postgresql.md
├── scripts/readonly_psql.py
└── tests/test_readonly_psql.py
```

`SKILL.md` conterá gatilhos, seleção de aliases, fluxo e invariantes comuns. A
configuração e o provisionamento PostgreSQL ficarão em
`references/postgresql.md`. O script será responsável por resolver um alias,
auditar o preflight e executar uma consulta. `agents/openai.yaml` será mantido
somente se os metadados de interface gerados forem úteis.

O bundle poderá ser versionado em qualquer repositório ou mantido em um
repositório próprio. A instalação global em
`$CODEX_HOME/skills/prod-readonly-db` ou, quando `CODEX_HOME` não existir,
`~/.codex/skills/prod-readonly-db`, será uma etapa separada. Copiar ou atualizar
essa instalação exige autorização para escrever fora do workspace atual.

Configurações de aliases e credenciais nunca serão parte do bundle. Cada
máquina, usuário ou ambiente poderá apontar os mesmos aliases para serviços
locais diferentes sem alterar a skill.

## Verificação

Antes de instalar ou conectar em produção:

1. Rodar o validador da skill e conferir frontmatter, nome, links e ausência de
   placeholders.
2. Executar os testes em um PostgreSQL descartável, sem credenciais ou rede de
   produção.
3. Cobrir configuração vazia, um alias, dois aliases e uma quantidade maior de
   aliases, demonstrando que não há limite codificado.
4. Demonstrar que vários aliases são processados separadamente e em sequência,
   sem fallback ou mistura de resultados.
5. Recusar alias inexistente, `psql` ausente, transporte inseguro, banco
   inesperado e role com atributo, ownership, membership ou privilégio proibido,
   inclusive `SET` ou `ALTER SYSTEM` sobre parâmetros.
6. Recusar `SELECT FOR UPDATE`, CTE mutável, múltiplas instruções,
   `EXPLAIN ANALYZE`, metacomandos do `psql` e os demais comandos proibidos.
7. Demonstrar uma consulta limitada bem-sucedida com uma role realmente
   restrita no banco descartável.
8. Verificar que DSN, senha e SQL sensível não aparecem em argumentos de
   processo, stdout, stderr ou exceções.
9. Executar o wrapper e sua suíte nas formas suportadas de Windows, macOS e
   Linux, sem depender do shell de um sistema específico.
10. Executar cenários de pressão com pedido urgente, credencial ampla e pedido
   genérico de “todos os bancos”; a skill deverá falhar fechado ou pedir a lista
   explícita.
11. Somente depois, configurar uma role real e fazer um preflight em um alvo de
    produção explicitamente autorizado.

O sucesso inicial é uma skill validada que funciona sem conhecer o projeto,
aceita qualquer número de aliases e executa uma consulta limitada em banco de
teste. Conectar a bancos reais é uma etapa operacional posterior e separada,
não um efeito colateral da criação ou instalação do bundle.

## Decisões adiadas para a configuração local

Não pertencem ao spec nem ao Git:

- quantidade e nomes reais dos aliases;
- hosts, portas, bancos e usuários;
- senhas, certificados privados e tokens;
- schemas liberados em cada alvo;
- mecanismo de túnel ou secret manager;
- quais bancos de produção serão autorizados primeiro.

Essas decisões poderão variar por projeto sem exigir fork ou edição da skill.
