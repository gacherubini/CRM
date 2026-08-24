---
gatilho: ligar lead a anuncio ou mexer em atribuicao CTWA
produto: chatbot-api / revy-trafego
custo: um diagnostico inteiro retratado
fonte: repo
verificado_em: 2026-08-24
---
# Nunca casar lead com auditoria CTWA por telefone mascarado

`ctwa_auditoria.telefone_mascarado` guarda `***` mais os **4 ultimos digitos**. Com ~500
conversas numa loja a colisao de 4 digitos **acontece** — e aconteceu em 08/08/2026: uma
auditoria com `meta_ad_id` e a conversa correspondente pertenciam a **outro cliente**, com
DDD diferente e 6 ultimos digitos diferentes. So os 4 finais batiam. O bloco de diagnostico
que nasceu dessa colisao esta retratado no proprio plano.

Consequencias que nao devem ser reaprendidas:

- **Nao implementar** fallback auditoria -> lead casando por telefone mascarado. Isso
  atribui o anuncio de um cliente a venda de outro, ou seja, **inventa receita atribuida**.
- Lead sem `meta_ad_id` em registro nenhum e **inatribuivel**: o lugar dele e "Sem
  campanha", nao um palpite.
- Ao filtrar `ctwa_source_type`, compare em `casefold` — os valores chegam com caixa
  diferente (`FB_Ads`, `ctwa_ad`, `ad`), e `click_to_chat_link`, `message_short_link` e
  `global_search_new_chat` sao carimbados `origem=meta_ctwa` **sem serem anuncio**.
- A Meta **nunca** manda `meta_campaign_id` na referral: so vem `meta_ad_id`. Resolver
  ad -> campanha exige o Graph API; nao ha atalho nos dados que chegam.
