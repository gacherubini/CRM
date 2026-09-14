---
gatilho: testar saída de rede alternativa (residencial, sticky, rotativo) num worker de banco
produto: motor-simulacao
custo: logins escassos queimados num egress que nunca fecharia o EXPECTED_IP
fonte: infra
verificado_em: 2026-09-13
---
# DataImpulse residencial como egresso do worker: sticky-BR passa, rotativo não

Medido em 13/09/2026 contra o worker Bradesco (`motor2037`), plano Residential por GB.

- **Porta 823 = rotativo: reprovado.** IP trocou em 5 s e saiu no Reino Unido.
  Rotativo cai no caso "incompatível" do card multiloja: quebra sessão e o
  `MOTOR_PROXY_EXPECTED_IP` nunca fecha. Nem subir.
- **Porta 10000 + sufixo `__cr.br` + país Brasil + intervalo 120 = sticky: aprovado.**
  Mesmo IP por 6+ min, BR, ASN de consumo (Claro/virtua.com.br no reverso).
  Com ele: `login_confirmado` → 4 ofertas → `concluida` pelo worker.
- **Sticky é ponte, não destino.** Janela de 120 min contada do primeiro uso
  (job no minuto 115 roda no meio); pool compartilhada sem exclusividade, sem
  allowlist, sem manter o número na renovação; tráfego BR com coeficiente x2.
  Quando roda, todo job cai em `saida_de_rede_divergente` (pré-portal, sem gastar
  login) — é o sinal para atualizar o esperado ou desligar.
- **Não replicar para banco que funciona sem proxy.** No mesmo dia, Santander,
  Fontecred, Pan e Omni concluíram no IP direto do Fly; Motrix recusa comercial
  do cliente de teste. Proxy só onde o loop é de rede.
- **Desenho final continua 1 IP dedicado por loja**, nunca um IP para todos os
  workers (ponto único de falha + quebra isolamento por loja, card §7).

Operação: `machine update <id> --env MOTOR_PROXY_URL=... --env
MOTOR_PROXY_EXPECTED_IP=... --skip-start -y` só no worker do banco (mescla,
preserva o resto); rollback esvaziando as duas chaves. `fly deploy` não encosta
nos workers — ver learning do deploy por banco.
