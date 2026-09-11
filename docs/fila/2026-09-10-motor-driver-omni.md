# Driver Omni (Omni+ motocicletas) — card de implementação

Status: em implementação (10/09/2026). Reconhecimento feito ao vivo com credencial
da loja (proposta 70099127). Sem captcha/WAF no login.

## Task

Buildar `app/motor/omni.py` (Playwright) + registro + `probe_omni.py`, provar com
`probe_todos` e `pytest`.

## Fluxo mapeado (fonte: `motor-simulacao/data/probes/omni-sim*/`, fora do git)

1. `GET /login` — Usuário + Senha + Continuar. Sessão quente reaproveitável.
2. `/app/rodas/visao-geral` → modal Nova Simulação: Financiamento + PF +
   card Motocicletas + select de vendedor (`.select_dropdown_item`) → Continuar.
3. `/simulacao/documento` — `app-huge-input` com máscara `000.000.000-00`
   (preencher formatado). Dialog "proposta em andamento" → "Continuar com a proposta".
4. `/simulacao/geral/telefone` — `input[testid='telephone-input']` máscara
   `(00) 00000-00`. **Efeito colateral: o cliente recebe WhatsApp (Open Finance).**
5. `/simulacao/geral/dados-veiculo` — radios plate/zeroKm/manual;
   `[testid='vehicle-plate']` resolve modelo (Fazer 250 2021, cotação R$ 19.200).
6. `/simulacao/geral/valor-veiculo` — `[testid='vehicle-value-input']` só aceita
   digitação real (teclado, não `fill`) + Tab.
7. `/simulacao/resultado-simulacao` — esperar skeletons sumirem; ofertas
   `48x de R$ 710,71 … 12x de R$ 1.754,30`; Entrada min R$ 0 / max R$ 17.200.
   **Parar aqui: nunca clicar o Continuar final (avança p/ contratação).**

## Constraints

- Contrato `/v1/simulacoes` não muda; segredo só no Motor; sem CPF/senha em log.
- Entrada: portal escolhe default (30%); preencher `down-payment-input` só se
  `entrada > 0`, e devolver a entrada do portal no resultado.
- Valor: o portal pode trocar pelo cotação — ler `Valor:/Financiado:/Entrada:`
  da tela, não assumir o pedido.
- Vendedor: `MOTOR_OMNI_VENDEDOR` (parcial basta); vazio = primeiro da lista.
- Login é escasso: reutilizar `storage_state`; senha recusada = parar.
