# Skill de acesso somente leitura a bancos de produção

Status: proposta para revisão do owner

## Decisão resumida

Criar uma única skill reutilizável chamada `prod-readonly-db`, distribuída como
um bundle copiável para a pasta global de skills do Codex. A skill terá quatro
alvos configuráveis, mas exigirá que o agente escolha um alvo por consulta.

A skill será PostgreSQL-first, porque os bancos documentados do Revy usam
PostgreSQL. Ela não armazenará DSNs, senhas, tokens, cookies ou nomes de
segredos do Fly. O DSN virá do ambiente seguro do usuário ou de um mecanismo
de secrets já existente.

A skill será uma proteção operacional, não a autoridade de segurança. A
garantia de somente leitura deverá existir no banco, em uma role sem privilégios
de escrita, sem superusuário e sem capacidade de criar roles/bancos. A skill
adicionará uma segunda barreira com transação read-only, timeout, alvo explícito
e bloqueio de comandos evidentemente mutáveis.

## Contexto

O Revy mantém dados separados por serviço e integra produtos por HTTP. No
ambiente local, `deploy/local/init-db.sql` cria os bancos `chatbot`, `estoque`,
`evolution` e `motor`; o ambiente Fly possui uma instância Postgres com bancos
e schemas que evoluíram durante o cutover. Portanto, os quatro alvos da skill
não devem ser codificados como uma tabela fixa do Revy: cada repositório poderá
dar seus próprios aliases.

O objetivo é permitir investigação diagnóstica autorizada em produção sem
transformar o agente em operador de banco, sem ler tabelas de outro domínio por
conveniência e sem depender de configuração específica do monorepo.

## Escopo

### Incluído

- bundle de uma skill genérica em `skills/prod-readonly-db/`;
- quatro ou mais aliases configuráveis por ambiente, com um alias obrigatório
  em cada invocação;
- conexão PostgreSQL via `psql` quando disponível;
- preflight de identidade, banco, modo read-only e limites da sessão;
- consultas de diagnóstico, inspeção de schema e agregações controladas;
- instruções de provisionamento da role de leitura para um DBA/owner;
- suporte a banco privado por túnel previamente aberto pelo usuário;
- validação da skill e cenários de pressão antes da instalação global.

### Fora do escopo

- criar ou alterar roles no banco de produção automaticamente;
- buscar, imprimir, copiar ou persistir credenciais;
- usar o usuário da aplicação como fallback;
- executar migrations, DDL, DML, jobs, funções mutáveis ou comandos Fly que
  alterem infraestrutura;
- juntar tabelas de bancos diferentes em uma consulta;
- substituir os contratos HTTP entre produtos;
- alterar código, migrations, deploy ou bancos do Revy durante a criação da
  skill.

## Arquitetura proposta

### Configuração

Cada alias será resolvido somente quando o usuário o escolher, usando uma
variável com convenção:

```text
PROD_READONLY_DB_<ALIAS>_URL
```

O `<ALIAS>` será normalizado para maiúsculas e underscores. A skill nunca
enumerará o ambiente para descobrir credenciais, nunca exibirá o valor da
variável e nunca fará fallback para `DATABASE_URL`, `DATABASE_CONNECTION_URI`
ou secrets da aplicação.

Para ambientes em que o DSN não deve aparecer nem como argumento temporário de
processo, a documentação também aceitará um serviço PostgreSQL (`pg_service`)
com senha em `.pgpass` ou secret manager. O nome do serviço não é segredo.

### Fluxo de uma consulta

1. Confirmar que o pedido é diagnóstico e que o usuário nomeou exatamente um
   alias de produção.
2. Identificar a raiz/repositório e ler somente as instruções e referências
   necessárias para entender o domínio do alvo.
3. Resolver a configuração do alias sem listar secrets.
4. Executar o preflight de sessão:
   `current_user`, `current_database()`, `current_schema()`,
   `transaction_read_only`, `statement_timeout` e `application_name`.
5. Abrir uma transação explicitamente `READ ONLY`, com `statement_timeout`,
   `lock_timeout` e `idle_in_transaction_session_timeout`.
6. Executar uma única consulta de leitura, com projeção mínima e limite de
   linhas quando o resultado não for agregado.
7. Encerrar a sessão, resumir o resultado e descartar o DSN e a saída bruta
   que não forem necessários.

Um pedido envolvendo mais de um banco será decomposto em consultas
independentes, uma por alias. A skill não fará fan-out silencioso e não fará
join entre bancos.

### Barreira no banco

Para cada banco, o owner/DBA deverá provisionar uma role específica de leitura
com, no mínimo:

- `LOGIN`, sem `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` ou
  `BYPASSRLS`;
- `CONNECT` apenas no banco autorizado;
- `USAGE` apenas nos schemas autorizados;
- `SELECT` apenas nas tabelas/views autorizadas;
- nenhum privilégio de `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `TRUNCATE`, DDL,
  ownership ou alteração de role;
- privilégios default configurados para novas tabelas, quando aplicável;
- `default_transaction_read_only=on` e timeouts conservadores como defesa
  adicional.

O provisionamento será uma referência para execução manual e revisada. A skill
não executará esse SQL, pois isso já seria uma mutação administrativa em
produção.

### Barreira na sessão

O executor usará `application_name=codex-prod-readonly`, `ON_ERROR_STOP`,
transação `READ ONLY` e timeouts. A validação de SQL rejeitará comandos
evidentemente mutáveis ou de elevação de privilégio, incluindo DML, DDL,
`COPY`, `DO`, `CALL`, `VACUUM`, `ANALYZE`, `EXPLAIN ANALYZE`, `SET ROLE` e
controle de transação fornecido pelo usuário.

Essa validação é defesa contra erro de operação, não um parser de segurança.
O privilégio irrevogável da role no banco continua sendo a barreira principal.

## Tratamento de dados e falhas

- Dados pessoais e credenciais bancárias serão consultados somente quando
  necessários ao diagnóstico, com colunas explícitas e quantidade mínima.
- Resultado grande, query sem limite ou consulta ambígua deve virar uma
  pergunta de refinamento, não um dump.
- Alias ausente, role sem read-only, banco incorreto ou privilégio inesperado
  interrompem o fluxo imediatamente.
- Falha de rede em banco privado deve ser reportada como necessidade de túnel;
  a skill não tentará recuperar credenciais nem executar comandos de deploy.
- Erros exibidos ao usuário serão sanitizados para não conter DSN, senha,
  token, cookie ou variável secreta.

## Artefatos previstos

```text
skills/prod-readonly-db/
├── SKILL.md
├── agents/openai.yaml
├── references/postgresql.md
└── scripts/readonly_psql.py
```

`SKILL.md` conterá somente gatilhos, fluxo e invariantes comuns. O
provisionamento PostgreSQL ficará em `references/postgresql.md`. O script será
responsável pela resolução segura do alias, preflight e execução de uma
consulta de leitura; ele falhará de forma explícita se `psql` não estiver
instalado ou se a variável do alvo não existir.

O bundle ficará versionado no repositório para revisão. A instalação global em
`%CODEX_HOME%/skills/prod-readonly-db` ou `~/.codex/skills/prod-readonly-db`
será uma etapa separada, dependente de autorização para escrever fora do
workspace.

## Verificação

Antes de instalar ou conectar em produção:

1. Rodar o validador oficial da skill e conferir frontmatter, nome, links e
   ausência de placeholders.
2. Executar cenários RED sem a skill, sob pressão de urgência, credencial
   ampla e pedido de consulta em todos os bancos; registrar as decisões reais
   do agente.
3. Criar a skill mínima para os desvios observados.
4. Reexecutar os mesmos cenários com a skill e fechar as brechas encontradas.
5. Testar o script sem credencial, com alias inexistente, com `psql` ausente,
   com query mutável e com uma consulta segura em um banco de teste.
6. Só então configurar roles read-only reais e fazer um preflight em um alvo de
   produção explicitamente autorizado.

O sucesso inicial é uma skill validada que recusa caminhos inseguros e executa
uma consulta limitada em um banco de teste. Acesso aos quatro bancos de
produção é uma etapa operacional posterior, não um efeito colateral da criação
do bundle.

## Decisões ainda não necessárias para o spec

Os nomes reais dos quatro aliases, os hosts/portas e o mecanismo de túnel não
precisam entrar neste documento nem no Git. Eles serão fornecidos na etapa de
configuração local, fora da skill e fora do histórico.
