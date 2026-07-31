# Stack completa local

O arquivo [`local.sh`](../../local.sh) sobe o monorepo inteiro no seu computador
com Docker. Não usa GitHub, Fly.io nem servidor externo. A única comunicação
externa opcional acontece quando você conecta WhatsApp, Gemini ou portais bancários.

## Uso rápido

Na raiz do projeto:

```bash
./local.sh up
```

Na primeira execução, o script:

1. cria `.env.local` com segredos aleatórios e permissão `600`;
2. constrói as imagens Docker;
3. sobe banco, filas, APIs, interfaces e workers;
4. cria a loja local e credenciais internas idempotentes;
5. cria o primeiro usuário do Portal/Control;
6. testa os endpoints e mostra as URLs.

Comandos úteis:

```bash
./local.sh status              # estado dos contêineres
./local.sh doctor              # testa os endereços HTTP
./local.sh logs                # logs de tudo
./local.sh logs portal         # logs de um serviço
./local.sh credentials         # mostra login local e chave da Evolution
./local.sh down                # desliga; preserva bancos e arquivos
./local.sh restart             # reinicia a stack
./local.sh workflow            # importa o template no n8n
```

## O que cada serviço faz

| Endereço | Componente | Função |
|---|---|---|
| `http://localhost:9000` | Revy Loja | CRM, estoque, vendas e atendimento |
| `http://localhost:9010` | Revy Control | lojas, mídia, Pixel/CAPI, Ads e ROI |
| `http://localhost:8200/l/moto-center` | Catálogo | vitrine pública da loja local |
| `http://localhost:8088` | Site | landing page da Revy |
| `http://localhost:5678` | n8n | workflow do atendimento |
| `http://localhost:8080/manager` | Evolution | conexão e QR do WhatsApp |
| `http://localhost:8001/docs` | Chatbot API | conversas, leads, handoff e roteamento |
| `http://localhost:8100/docs` | Estoque API | veículos, publicação e fotos |
| `http://localhost:8000/docs` | Motor | simulações mock e bancárias |

Também sobem, sem porta pública:

- **PostgreSQL:** bancos separados de Chatbot, Estoque, Motor e Evolution;
- **Redis:** cache da Evolution;
- **Estoque Outbox:** entrega eventos de alteração de veículos;
- **Motor Worker:** processa a fila e executa Playwright sob tela virtual.

Os dados sobrevivem a `./local.sh down` porque ficam em volumes Docker. O script
não oferece reset automático para evitar apagar dados por engano.

## Arquivos envolvidos

- `local.sh`: interface de operação;
- `compose.local.yml`: definição dos contêineres, portas, rede e volumes;
- `deploy/local/init-db.sql`: cria os quatro bancos PostgreSQL;
- `deploy/local/bootstrap.py`: cadastra loja, usuário e tokens internos sem duplicar;
- `.env.local`: segredos gerados nesta máquina; ignorado pelo Git e nunca deve ser enviado.

## WhatsApp e IA

Os serviços sobem sem depender de WhatsApp ou Gemini. Para conversar de verdade:

1. execute `./local.sh workflow`;
2. abra o n8n em `http://localhost:5678`;
3. crie/selecione uma credencial Google Gemini no nó do modelo;
4. salve e ative o workflow `WhatsApp IA - Somente Nao Salvos`;
5. abra o Portal, adicione um número em **Ajustes → WhatsApp** e escaneie o QR.

O template é importado inativo porque a chave do Gemini pertence à sua conta e não
deve ser colocada no repositório.

## Observações

- O primeiro build é demorado: baixa imagens e instala Chromium para o Motor.
- Simulação bancária real ainda exige as credenciais de cada portal bancário.
- `./local.sh down` não apaga nada; as políticas `restart: unless-stopped` mantêm
  os serviços ativos enquanto o Docker estiver ligado.
