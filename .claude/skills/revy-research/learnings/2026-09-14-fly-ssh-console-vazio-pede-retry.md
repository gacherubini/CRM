---
gatilho: fly ssh console volta vazio sem erro, ou parse de saida remota falha do nada
produto: motor-simulacao
custo: meia hora culpando codigo e mapa quando era flake de transporte
fonte: infra
verificado_em: 2026-09-14
---
# `fly ssh console` vazio não é resposta: é flake, tenta de novo

Em 14/09, o mesmo comando remoto alternou entre saída cheia e zero linhas,
sem erro e com exit normal — inclusive `echo ... | base64 -d > /tmp/x.py`
que tinha funcionado minutos antes. Saída vazia (`@($r).Count -eq 0`) não
prova nada; só vale parsear quando há linhas.

Padrão que funcionou: até 4-5 tentativas com `Start-Sleep` de 5-8 s,
parseando marcador (`^TOK:`, `^CID:`, `CODE:`) e só então desistindo. Erro
REAL se distingue porque vem com traceback/texto — vazio puro é sempre
transporte. E o inverso também vale: `echo simples` que volta não prova que
o comando complexo seguinte passou; cada passo precisa do seu marcador.
