# Learnings — indice

Leia **so** os de gatilho compativel com a sua tarefa. Normalmente 0, 1 ou 2.

Cada arquivo declara no cabecalho **onde mora a verdade dele** e **quando alguem
reconferiu pela ultima vez**:

- `fonte: repo` — da para confirmar lendo codigo. Se desconfiar, confirme: e barato.
- `fonte: infra` — so com acesso ao Fly ou ao painel do n8n. **Apodrece sem sinal
  nenhum no git**, porque o mundo muda sem commit.
- `fonte: externo` — politica de terceiro (Meta, WhatsApp). Muda sem aviso.

`verificado_em: nunca reconferido...` quer dizer o que esta escrito: o texto veio
das memorias de sessao e ninguem bateu contra o repo depois. Nao e motivo para
ignorar o learning — e motivo para conferir antes de decidir em cima dele.
Conferiu? Carimbe a data. **Carimbo sem conferencia e o defeito que este campo
existe para consertar**: o learning dos bancos afirmou "Portal e Control sao
SQLite" por uma semana depois de os dois virarem Postgres, e quase fez um agente
escrever migration com `batch_alter_table`.

| Gatilho | Arquivo |
|---|---|
| propor ou planejar feature que voce ainda nao viu no codigo | `2026-08-23-confira-se-a-feature-ja-existe-antes-de-propor.md` |
| deployar no Fly | `2026-08-23-fly-deploy-usa-arvore-local.md` |
| rodar alembic ou conferir migration de producao | `2026-08-23-alembic-mente-sem-database-url.md` |
| mergear branch longa que tem migration | `2026-08-23-merge-limpo-esconde-duas-cabecas-do-alembic.md` |
| descobrir se uma flag de rollout esta ligada em producao | `2026-08-23-flags-de-rollout-sao-secrets.md` |
| ligar ou desligar as maquinas do Fly pelos scripts do repo | `2026-08-23-scripts-do-fly-usam-python3.md` |
| investigar custo, volume ou RAM dos apps do Fly | `2026-08-23-volume-do-fly-forka-sozinho.md` |
| portal e motor caindo juntos com conexao recusada no banco | `2026-08-23-suite-pg-oom-derruba-portal-e-motor.md` |
| procurar o banco de um produto, escolher dialeto de migration ou cruzar dados | `2026-08-23-engine-do-produto-se-confere-no-db-py.md` |
| o bot do WhatsApp parou de responder sem ninguem ter mexido no codigo | `2026-08-23-n8n-cheio-deixa-o-bot-mudo.md` |
| reiniciar o n8n2037 ou trocar um secret dele | `2026-08-23-reiniciar-o-n8n-derruba-o-webhook.md` |
| subir workflow novo no n8n do Fly | `2026-08-23-import-do-n8n-desativa-o-workflow.md` |
| mudar o prompt do bot, o tom da IA ou o que ela pode responder | `2026-08-23-o-prompt-do-bot-mora-no-n8n.md` |
| mexer no workflow do n8n do Modo 2 (cloud) | `2026-08-23-workflow-cloud-e-gerado.md` |
| parear numero novo no Evolution ou QR que nao conecta | `2026-08-23-qr-do-evolution-nao-fecha-por-passkey.md` |
| responder se uma feature ja foi implementada | `2026-08-23-teste-verde-nao-prova-que-a-feature-existe.md` |
| mexer no JS de uma tela do portal | `2026-08-23-copiloto-so-se-verifica-no-navegador.md` |
| mexer em app.css do portal ou do control | `2026-08-23-bump-do-v-no-base-html.md` |
| acrescentar metrica numa tela da Loja ou do Control | `2026-08-23-metric-grid-trava-em-quatro.md` |
| mudar cor, fonte ou token de marca | `2026-08-23-tokens-de-marca-tem-fonte-unica.md` |
| mexer no logo ou na assinatura da marca | `2026-08-23-a-marca-e-gerada-por-script.md` |
| reexportar ou editar o site de marketing | `2026-08-23-site-e-export-estatico.md` |
| escrever teste do outbox de provisionamento do Control | `2026-08-23-teste-de-outbox-usa-destino-sintetico.md` |
| testar projecao de venda no Control | `2026-08-23-nao-construir-venda-projetada-a-mao.md` |
| investigar numero zerado numa tela da Loja | `2026-08-23-zero-na-tela-pode-ser-projecao-vazia.md` |
| ligar lead a anuncio ou mexer em atribuicao CTWA | `2026-08-23-telefone-mascarado-de-4-digitos-colide.md` |
| testar envio de convite ou de e-mail | `2026-08-23-backend-de-email-console-responde-200.md` |
| simulacao de banco volta "sem oferta" e voce vai procurar bug no driver | `2026-09-06-motrix-recusa-sem-motivo-e-200-com-lista-vazia.md` |
| driver de banco reprova um passo olhando o estado da janela em vez do campo | `2026-09-07-modal-aberto-nao-quer-dizer-passo-falhou.md` |
| depurar driver Playwright de banco que termina em timeout | `2026-08-23-driver-playwright-engole-o-clique-que-falha.md` |
| clique do Playwright estoura timeout num elemento que existe e parece visivel | `2026-09-04-is-visible-mente-com-modal-recortado.md` |
| rodar os drivers de banco ao vivo na maquina local | `2026-09-04-probe-todos-roda-os-bancos-de-uma-vez.md` |
| logar num portal bancario por script, ou repetir um login que acabou de funcionar | `2026-09-04-portal-do-banco-desativa-login-repetido.md` |
| achar API JSON atras do portal de um banco e querer trocar Playwright por HTTP | `2026-09-04-spa-com-api-nao-e-driver-de-api.md` |
| propor canal de entrada de lead que nao seja anuncio CTWA | `2026-08-23-mensagem-de-servico-volta-a-ser-paga.md` |
| dimensionar limite da Cloud API ou tratar verificacao de CNPJ como bloqueio | `2026-08-23-teto-de-250-conta-so-outbound.md` |
| submeter a verificacao de empresa (CNPJ) no portfolio da Meta | `2026-08-23-verificacao-da-meta-so-o-email-aceita-endereco.md` |
| ligar o Modo 2 numa loja ou cadastrar o canal Cloud dela | `2026-08-23-canal-cloud-nao-se-cadastra-pela-api.md` |
| por uma loja cliente no Modo 2, ou seguir o onboarding assistido do §16.6 | `2026-08-29-onboarding-assistido-do-16-6-nao-roda.md` |
| mandar mensagem do lado do servidor numa loja Modo 2 (worker, rota, envio humano) | `2026-08-24-outbound-por-loja-quer-loja-id.md` |
| mexer em multi-loja, no seletor de lojas ou em quem pode trocar de loja | `2026-08-24-seletor-e-rota-leem-fontes-diferentes.md` |
| por uma rota do chatbot na credencial de integracao, ou achar que `instance` resolve multi-loja | `2026-08-24-instance-nao-conserta-toda-rota.md` |
| trabalhar no repo com outra sessao de agente aberta | `2026-08-24-outra-sessao-move-o-chao-no-meio-da-tarefa.md` |
| bot do Modo 2 fica mudo com audio, imagem ou qualquer midia | `2026-08-25-corpo-assinado-pela-meta-nao-sobrevive-ao-n8n.md` |
| por um formulario do portal para gravar em rota do chatbot | `2026-08-25-o-422-do-chatbot-chega-como-indisponivel.md` |
| rodar as ferramentas do agente fora de uma conversa real (preview, lab, carga) | `2026-08-25-consultar-estoque-cria-conversa.md` |
| mexer no prompt do bot, no systemMessage ou na config do agente por loja | `2026-08-25-o-prompt-e-metade-template-metade-dado.md` |
| escrever ou revisar script de operacao que aponta para uma loja por slug | `2026-08-25-o-slug-do-piloto-nao-e-o-nome-do-piloto.md` |
| escrever teste que exercita projecao do Control (`_apply_envelope`) no chatbot-api | `2026-08-29-o-conftest-do-chatbot-nao-semeia-todo-aggregate.md` |
| escrever teste no chatbot-api que grava canal, ou qualquer linha com coluna UNIQUE global | `2026-08-29-o-banco-de-teste-do-chatbot-e-um-so.md` |
| escrever teste de read-model do portal que le dicionario vindo de outro produto | `2026-08-29-dicionario-sintetico-no-teste-esconde-contrato.md` |
