# Fotos de veículos no WhatsApp

Fluxo implementado para enviar a foto no próprio WhatsApp, sem exigir que o
cliente abra o catálogo/site:

1. a foto é hospedada em object storage/CDN público;
2. o Estoque recebe URL estável ou `storage_key`, valida e grava só metadados;
3. consultas do Chatbot recebem a projeção `tem_foto`/`midia_principal`;
4. a tool `enviar_foto_veiculo` recebe somente `veiculo_id`;
5. o Chatbot resolve a capa pela loja autenticada;
6. o n8n chama `POST /message/sendMedia/{instance}` na Evolution.

O modelo nunca escolhe a URL enviada para a Evolution. A URL vem da rota
tenant-scoped `GET /v1/estoque/veiculos/{id}/midia-principal`, que consulta apenas
veículo disponível e publicado na vitrine daquela loja.

## Cadastro no Estoque

```http
PUT /v1/veiculos/{id}/fotos
Authorization: Bearer TOKEN_DO_ESTOQUE
Content-Type: application/json
```

```json
{
  "fotos": [
    {
      "storage_key": "moto-center/veiculo-123/frente.webp",
      "content_type": "image/webp",
      "tamanho_bytes": 245000,
      "ordem": 0,
      "capa": true
    },
    {
      "url": "https://media.example/veiculos/veiculo-123/lateral.jpg",
      "content_type": "image/jpeg",
      "tamanho_bytes": 310000,
      "ordem": 1,
      "capa": false
    }
  ]
}
```

`storage_key` exige `ESTOQUE_MEDIA_PUBLIC_BASE_URL`. Tipos permitidos: JPEG,
PNG e WebP. O limite padrão é 20 fotos e 10 MiB por arquivo. Ordem não pode se
repetir e deve existir exatamente uma capa. Enviar `{"fotos": []}` remove todas.

A forma anterior `{"urls": ["https://..."]}` continua aceita. Ela deve ser
usada somente durante a migração, pois não traz tamanho declarado.

## Regras de segurança

- nunca persistir binário ou base64 no banco;
- aceitar apenas URL HTTPS pública e estável;
- rejeitar host local/privado, credenciais, query e fragmento;
- não devolver path de filesystem ou `storage_key` na API;
- projetar por allowlist antes de expor o veículo ao Chatbot;
- resolver mídia por loja + `veiculo_id`, nunca por URL enviada pelo modelo;
- veículo sem foto continua respondendo normalmente em texto.

## Configuração

```env
ESTOQUE_MEDIA_PUBLIC_BASE_URL=https://media.seudominio.com/veiculos
ESTOQUE_MEDIA_MAX_FOTOS=20
ESTOQUE_MEDIA_MAX_BYTES=10485760
ESTOQUE_MEDIA_URL_MAX_CHARS=2048
ESTOQUE_MEDIA_ALLOWED_HOSTS=media.seudominio.com
```

O bucket/origem deve permitir leitura pela Evolution. Escrita no storage,
política de lifecycle, antivírus e remoção de objetos órfãos pertencem à operação
do provedor escolhido; não devem ser implementadas salvando arquivos no container.
