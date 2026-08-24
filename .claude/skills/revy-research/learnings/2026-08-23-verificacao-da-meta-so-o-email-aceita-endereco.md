---
gatilho: submeter a verificacao de empresa (CNPJ) no portfolio da Meta
produto: chatbot-api
fonte: externo
verificado_em: 2026-08-23
---
# Na verificação da Meta, só o método Email aceita endereço no lugar do telefone

A tela de upload de documentos tem **duas** seções — *Verificar a razão social* e
*Verificar telefone* — e o **CCMEI não aparece na lista da segunda**, porque não imprime
telefone. O único documento do MEI que imprime é o cartão CNPJ, e ele traz `(19) 9846-9808`,
truncado em 8 dígitos por cadastro antigo da Receita: uma string diferente do que se declara
no formulário, que exige o nono dígito para receber SMS.

O que dissolve isso é a **tela seguinte**, de confirmar conexão com a empresa, onde a
exigência documental **muda conforme o método**:

| Método | O documento precisa ter |
|---|---|
| **Email** | razão social **e o endereço _ou_ o telefone** |
| Ligação / SMS / WhatsApp | razão social **e o telefone** |

Escolher **Email** é o que faz o CCMEI bastar sozinho — ele tem razão social + endereço — e
tira o cartão CNPJ da jogada. Não é por ser o "Recomendado". Nunca alinhar o telefone
declarado à versão de 8 dígitos para casar com o cartão: número truncado não recebe SMS e
trava a confirmação por código.

Três detalhes que custam uma tentativa cada:

- **Voltar consome o método.** Depois de um *Voltar* na tela do código, *Email* e
  *Verificação de domínio* sumiram da lista, sobrando só as três que pedem telefone.
  Reabrir o fluxo pelo *Ver detalhes* devolve as opções.
- O e-mail tem que ser **`contato@revyapp.com.br`**: o catch-all do domínio está desligado
  de propósito, então qualquer outro endereço não existe e o código se perde sem erro
  nenhum. O código cai na aba **Social** do Gmail, não na Primary, e vale 60 minutos.
- O fluxo **lê os *Detalhes da empresa* do portfólio**, que estavam desatualizados (razão
  social `Revy`, site `app2037.fly.dev/site/`, sem telefone, endereço só `Brasil`).
  Corrigir antes é pré-requisito — é esse bloco que o revisor compara com o documento.

O caminho na interface **não é** *Autorizações e verificações*, que só trata autorização de
anúncio: é **Central de Segurança**, rolando até *Verificação da empresa*, com o caso de uso
*"O app exige acesso a permissões no Meta for Developers"*.

Contexto e o que a verificação compra (nome de exibição, 3º número — não volume) em
[`docs/referencia-viva/design/2026-08-16-onboarding-meta-dominio-asbuilt.md`], junto do
placar dos quatro portões. Ver também o teto de 250, que conta só outbound.
