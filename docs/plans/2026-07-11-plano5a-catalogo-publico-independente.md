# Plano #5A — Catálogo Público Independente

> Plano válido do Catálogo. #5 legado em `_archive/` (não executar). Sem acesso a banco de outro produto.
>
> **Status 2026-07-12:** 1º incremento vertical **entregue** (vitrine, detalhe, CTA `wa.me`+`CAT-*`,
> outbox, deploy conectado, testes). **Aberto:** E2E env outbox no deploy; tema/SEO/cache/rate limit;
> compose standalone completo; retenção.

**Goal:** Entregar uma vitrine pública por loja, rápida e personalizada, com estoque publicado,
página de veículo e interesse via WhatsApp, vendável sem Portal, Chatbot ou Motor.

**Stack:** FastAPI, templates server-side, assets compilados/localizados, cache, pytest e Docker.

## Formas de venda

- **Catálogo conectado:** aponta para uma Estoque API já existente.
- **Catálogo Standalone:** pacote comercial inclui Estoque API/admin mínimo + Catálogo no mesmo
  compose; para o comprador continua sendo uma instalação autônoma.

Em nenhuma modalidade Portal, Chatbot ou Motor são obrigatórios.

## Critérios de independência

1. Catálogo consome apenas `CatalogDataProvider`, nunca tabelas/views.
2. `HttpInventoryProvider` usa a API pública do Estoque.
3. Compose standalone inclui a fonte de dados necessária e funciona em ambiente vazio.
4. Falha temporária do provider possui página controlada/cache; não expõe erro interno.
5. Eventos de interesse são locais e/ou enviados para webhook opcional.

## Rotas públicas

- `/l/{slug}`: vitrine da loja.
- `/l/{slug}/veiculos/{id-ou-slug}`: detalhe.
- `/l/{slug}?tipo=&marca=&preco_min=&preco_max=`: filtros.
- `/l/{slug}/interesse/{veiculo}`: registra clique e redireciona ao `wa.me` seguro.
- `/sitemap.xml`, `/robots.txt` e metadados sociais por loja/veículo.

Usar slug público, não `loja_id` sequencial como URL comercial.

## Tasks

### Task 1: Scaffold e provider

Criar `catalogo-publico/` com health/version, `CatalogDataProvider`, implementação HTTP e fixtures
para testes. Nenhuma configuração de banco externo é aceita pelo app do catálogo.

### Task 2: Compose conectado e standalone

Criar:

- `deploy/catalogo-conectado/docker-compose.yml`;
- `deploy/catalogo-standalone/docker-compose.yml`;
- `.env.example` e onboarding de ambos.

O standalone inclui Estoque API/admin; o conectado exige somente `ESTOQUE_PUBLIC_API_URL` e token
público quando aplicável.

### Task 3: Tema e configuração por loja

Nome, logotipo, contatos, cores permitidas, texto, domínio e WhatsApp vêm de dados públicos
sanitizados. Definir tema padrão acessível e responsivo.

### Task 4: Vitrine e filtros

Cards com foto, identificação, ano, km e preço; paginação e estado vazio. Filtros são preservados
em URL e enviados somente como parâmetros suportados ao provider.

### Task 5: Detalhe e galeria

Página com galeria, especificações, disponibilidade e CTA. Imagens possuem dimensão/reserva de
espaço, lazy loading e fallback.

### Task 6: Interesse rastreável

Rota interna registra evento com loja, veículo, timestamp, origem/UTM e identificador anônimo,
então redireciona para WhatsApp com mensagem contendo referência do veículo. Validar/normalizar o
número e impedir redirect arbitrário.

### Task 7: Webhook opcional

Enviar `catalog.interest_clicked` para destino configurado com HMAC, outbox e retry. Sem webhook,
guardar/exportar eventos localmente; Catálogo continua funcionando.

### Task 8: SEO, desempenho e cache

HTML server-side, canonical, Open Graph, sitemap, cache condicional e assets locais. Definir metas
de desempenho e testar com catálogo representativo, sem CDN obrigatória de CSS/JS em produção.

### Task 9: Segurança e privacidade

Escape de conteúdo, CSP, headers, rate limit, validação de URLs de imagem/provider, proteção contra
SSRF e política de retenção dos eventos. Não coletar CPF/nascimento.

### Task 10: Operação e teste de revenda

Testar domínio/slug inexistente, provider indisponível, veículo removido, WhatsApp ausente, filtros,
mobile, backup/restore dos eventos e instalação standalone sem produtos externos.

## Integrações opcionais

- Portal pode gerar links e administrar o Estoque pela API privada.
- Chatbot pode receber o evento de interesse por webhook genérico.
- Ferramentas de analytics entram por configuração consentida, sem serem requisito.

## Fora de escopo

- Cadastro direto no banco do Catálogo.
- CRM e atendimento.
- Simulação financeira embutida na primeira versão.
- Automação de campanhas/postagens.

## Resultado

Uma vitrine pública vendável sozinha, com fonte de dados bem definida e interesse mensurável.
