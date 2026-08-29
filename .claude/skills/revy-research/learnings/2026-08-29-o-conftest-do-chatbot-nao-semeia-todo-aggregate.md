---
gatilho: escrever teste que exercita projecao do Control (`_apply_envelope`) no chatbot-api
produto: chatbot-api
custo: quatro testes verdes que passariam com metade do codigo apagada
fonte: repo
verificado_em: 2026-08-29
---
# O conftest só semeia três aggregates, então seu teste de projeção nunca vê o update

`_apply_envelope` (`chatbot-api/app/provisioning.py:94`) tem **dois** caminhos que
devolvem `"applied"`: o de *update*, quando a loja já tem linha em
`LojaOperacionalProjecao` para aquele aggregate, e o de *insert*, quando não tem.

As fixtures de loja do `tests/conftest.py:60-80` semeiam projeção apenas de
`loja`, `vendas` e `estoque`. Qualquer aggregate fora desses três — `whatsapp_modo`,
por exemplo — não tem linha nenhuma, então **o primeiro `_apply_envelope` do seu
teste sempre cai no insert**. O caminho de update fica sem exercício, e um efeito
colateral escrito só lá passa despercebido.

Foi o que aconteceu no Card 2 do Embedded Signup: o gancho que ativa o canal Cloud
está nos dois pontos, mas quatro testes passavam com o do update comentado. Só
quebrou depois de um quinto teste que aplica `state="1"` e **depois** `state="2"`
na mesma loja.

## Como escapar

Para cobrir o update, aplique dois envelopes na mesma loja e no mesmo aggregate,
com versão crescente — `version` é monotônico, versão menor volta `"stale"` e o
teste passa sem exercitar nada:

```python
provisioning._apply_envelope(db, loja, {"version": 1, "state": "1", "event_id": "e1"}, "whatsapp_modo")
provisioning._apply_envelope(db, loja, {"version": 2, "state": "2", "event_id": "e2"}, "whatsapp_modo")
```

E, antes de confiar no teste, **apague o código que ele deveria proteger e veja o
teste ficar vermelho**. É o único jeito de saber qual dos dois caminhos ele cobre —
o nome do teste não distingue.
