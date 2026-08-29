---
gatilho: escrever teste no chatbot-api que grava canal, ou qualquer linha com coluna UNIQUE global
produto: chatbot-api
custo: seis testes vermelhos com erro que nada tinha a ver com o defeito procurado
fonte: repo
verificado_em: 2026-08-29
---
# O banco de teste do chatbot é UM só, e ele não é limpo entre testes

`tests/conftest.py:23-26` cria um SQLite em memória com `StaticPool` e roda
`create_all` uma vez. **Toda a sessão de pytest usa esse mesmo banco, e nada
apaga linha entre um teste e outro.**

O que confunde é que meia proteção existe: `loja_a`, `loja_b` e
`loja_sem_projecao` criam uma **loja nova a cada teste**, com `uuid` no slug. Por
isso quase tudo que é filtrado por `loja_id` funciona como se o banco fosse
limpo — e você conclui, errado, que ele é.

**A conta não fecha em coluna `UNIQUE` global.** `WhatsAppCanal.evolution_instance`
é única no banco inteiro, não por loja (é de propósito: um número pertence a uma
loja só). Então dois testes que usem o mesmo `phone_number_id` colidem, mesmo
sendo de lojas diferentes — e o segundo falha com o erro da colisão, não com o
que ele estava testando.

Foi assim no Card 3 do Embedded Signup: um helper com `phone_number_id` fixo
derrubou seis dos oito testes com "este número já está conectado a outra loja".
A guarda estava certa; o teste é que não era hermético.

## Como escapar

**Um valor único por teste** em qualquer coluna `UNIQUE` global. Nos testes de
canal do chatbot a convenção que se formou é uma faixa de `phone_number_id`
sequenciais, um por teste, com os módulos não se sobrepondo — de
`1227059273831581` em diante. Antes de escolher o seu, `rg 12270592738 tests/`.

Vale para qualquer coisa com `UniqueConstraint` no `models_db.py`, não só canal.
