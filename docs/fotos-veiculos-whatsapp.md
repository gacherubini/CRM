# Fotos de veículos: WhatsApp → Estoque → Catálogo

Fluxo automático implementado para a equipe cadastrar o veículo e suas fotos sem
abrir Portal ou site:

1. o dono ou gerente escolhe o grupo em **Grupo do estoque** no Portal;
2. um participante desse grupo envia `menu` e escolhe **Cadastrar veículo**;
3. a tool `cadastrar_veiculo` cria o veículo já publicado no Estoque e abre uma
   sessão de fotos de 10 minutos para aquele grupo+loja+placa;
4. a equipe envia as fotos no mesmo grupo, sem precisar repetir a placa;
5. o n8n encaminha somente instância, grupo, participante, ID da mensagem, legenda e MIME;
6. a Chatbot API valida loja+grupo antes de baixar a imagem da Evolution;
7. a imagem é enviada em bytes para o Estoque, que valida e grava no volume;
8. a foto entra na galeria e a API pública passa a entregá-la ao Catálogo;
9. o bot confirma no grupo que Estoque e Catálogo foram atualizados.

Se o veículo já existia, coloque a placa somente na primeira foto, por exemplo
`ABC1D23`; as seguintes usam a sessão curta. Uma placa explícita troca a sessão
ativa. Reentrega do mesmo evento não duplica a foto: o ID da mensagem vira chave
idempotente.

A janela pode ser ajustada no Chatbot com
`CHATBOT_IMAGE_SESSION_TTL_SECONDS=600`; valor `0` desativa a sessão e volta a
exigir placa em cada foto.

O cadastro textual também possui idempotência persistente no Estoque. A mesma
mensagem+payload retorna o mesmo veículo; reutilizar a chave com dados diferentes
gera conflito. O banco guarda apenas hashes da chave e do payload. No n8n,
telefone e `Idempotency-Key` vêm do webhook real, nunca de campos escolhidos pelo
modelo.

O cliente comum não pode usar esse caminho. A loja possui um único JID em
`grupos_estoque`; imagens privadas e mensagens de qualquer outro grupo são
ignoradas sem resposta. A validação acontece novamente no backend antes do
download da mídia, mesmo que o workflow seja alterado por engano.

## Armazenamento

No MVP, os arquivos ficam fora do banco, em volume persistente do Estoque
(`ESTOQUE_MEDIA_STORAGE_DIR`). O banco guarda somente URL e metadados. A rota
pública usa chave opaca e headers imutáveis:

```text
GET /public/v1/media/{loja_id}/{veiculo_id}/{hash}.{jpg|png|webp}
```

Configure uma URL HTTPS pública que aponte para essa rota:

```env
ESTOQUE_MEDIA_STORAGE_DIR=/data/media
ESTOQUE_MEDIA_PUBLIC_BASE_URL=https://estoque.seudominio.com/public/v1/media
ESTOQUE_MEDIA_ALLOWED_HOSTS=estoque.seudominio.com
ESTOQUE_MEDIA_MAX_FOTOS=20
ESTOQUE_MEDIA_MAX_BYTES=10485760
ESTOQUE_MEDIA_ORPHAN_GRACE_SECONDS=3600
ESTOQUE_MEDIA_CLEANUP_INTERVAL_SECONDS=21600
```

Os `docker-compose.yml` montam o volume `estoque_media` em `/data/media`. Em
produção, o domínio precisa ser acessível pelo navegador do cliente e pela
Evolution. Backup do volume é responsabilidade operacional. Para múltiplas
réplicas, migrar o mesmo contrato de `storage_key` para S3/R2/MinIO é evolução de
escala, sem mudar o Catálogo.

No lab Fly, `estoque-api/fly.toml` já define a URL pública e o mount. O volume
`estoque_media` de 1 GB foi criado, criptografado e anexado em 2026-07-21; não
o recrie em deploys seguintes. Snapshots estão agendados e o runbook de
backup/restore está em `deploy/estoque-standalone/RUNBOOK.md`; falta executar o
primeiro restore drill.

## Contrato privado de upload

```http
POST /v1/veiculos/{id}/fotos/upload?publicar=true
Authorization: Bearer TOKEN_DO_ESTOQUE
Content-Type: image/jpeg
Idempotency-Key: wa-foto:ID_DA_MENSAGEM

<bytes da imagem>
```

Também permanece disponível o contrato de metadados `PUT
/v1/veiculos/{id}/fotos`, aceitando URL HTTPS ou `storage_key` para integrações
externas.

## Regras de segurança

- somente JPEG, PNG e WebP, com conferência de MIME e assinatura do arquivo;
- limite padrão de 10 MiB antes de persistir;
- autorização do grupo e tenancy antes de baixar a mídia;
- binário não passa pelo LLM e não fica no n8n ou no banco;
- path público é construído no backend; o modelo nunca escolhe URL ou destino;
- escrita atômica em volume e nome derivado de hash idempotente;
- sessão de fotos isolada por loja e grupo autorizado, com expiração;
- cadastro textual idempotente e identidade do grupo presa ao webhook;
- URLs manuais continuam rejeitando base64, host privado, credenciais, query e fragmento;
- cliente sem controle de exclusão; retenção/remoção continua administrativa.

## Limpeza administrativa

Ao substituir a galeria, o Estoque remove arquivos locais que deixaram de ser
referenciados, respeitando a carência configurada. Para auditoria e limpeza de
órfãos antigos, o comando inicia em modo somente leitura:

```bash
python -m app.cli limpar-midias-orfas
python -m app.cli limpar-midias-orfas --aplicar
```

A carência padrão de uma hora impede que uma varredura apague um upload ainda
entre a gravação do arquivo e o commit no banco. O comando não aceita path/loja
informado pelo cliente e nunca remove URLs externas. O worker da outbox executa
essa manutenção automaticamente a cada seis horas. Se a base pública não estiver
configurada, a rotina falha fechada e preserva todos os arquivos.

## Envio da foto ao cliente

Quando um cliente pede uma imagem, a tool `enviar_foto_veiculo` recebe somente o
`veiculo_id`, resolve a capa pela loja autenticada e chama `sendMedia` na
Evolution. Veículo sem foto continua com resposta em texto; nunca é inventada uma
imagem.
