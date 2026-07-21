# Fotos de veículos: WhatsApp → Estoque → Catálogo

Fluxo automático implementado para a equipe cadastrar o veículo e suas fotos sem
abrir Portal ou site:

1. um número autorizado envia os dados do carro/moto por texto;
2. a tool `cadastrar_veiculo` cria o veículo já publicado no Estoque;
3. o vendedor envia uma foto com a placa na legenda, por exemplo `ABC1D23`;
4. o n8n encaminha somente instância, telefone, ID da mensagem, legenda e MIME;
5. a Chatbot API valida loja+número antes de baixar a imagem da Evolution;
6. a imagem é enviada em bytes para o Estoque, que valida e grava no volume;
7. a foto entra na galeria e a API pública passa a entregá-la ao Catálogo;
8. o bot confirma no WhatsApp que Estoque e Catálogo foram atualizados.

Para várias fotos, envie cada imagem com a mesma placa na legenda. Reentrega do
mesmo evento não duplica a foto: o ID da mensagem vira chave idempotente.

O cliente comum não pode usar esse caminho. Somente telefones ativos em
`numeros_autorizados` da loja podem anexar fotos; a validação acontece antes do
download da mídia.

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
```

Os `docker-compose.yml` montam o volume `estoque_media` em `/data/media`. Em
produção, o domínio precisa ser acessível pelo navegador do cliente e pela
Evolution. Backup do volume é responsabilidade operacional. Para múltiplas
réplicas, migrar o mesmo contrato de `storage_key` para S3/R2/MinIO é evolução de
escala, sem mudar o Catálogo.

No lab Fly, `estoque-api/fly.toml` já define a URL pública e o mount. Antes do
primeiro deploy, crie uma vez o volume com `fly volumes create estoque_media
--app estoque2037 --region gru --size 1`.

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
- autorização do remetente e tenancy antes de baixar a mídia;
- binário não passa pelo LLM e não fica no n8n ou no banco;
- path público é construído no backend; o modelo nunca escolhe URL ou destino;
- escrita atômica em volume e nome derivado de hash idempotente;
- URLs manuais continuam rejeitando base64, host privado, credenciais, query e fragmento;
- cliente sem controle de exclusão; retenção/remoção continua administrativa.

## Envio da foto ao cliente

Quando um cliente pede uma imagem, a tool `enviar_foto_veiculo` recebe somente o
`veiculo_id`, resolve a capa pela loja autenticada e chama `sendMedia` na
Evolution. Veículo sem foto continua com resposta em texto; nunca é inventada uma
imagem.
