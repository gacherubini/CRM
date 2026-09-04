---
gatilho: rodar os drivers de banco ao vivo na maquina local
produto: motor-simulacao
custo: quatro probes soltos com nomes de env e saida diferentes
fonte: repo
verificado_em: 2026-09-04
---
# `scripts/probe_todos.py` roda os quatro bancos e diz quais quebraram

Nao ha worker fora do Fly (o card do PC local segue so desenhado). Para ver os drivers
reais rodando na maquina do dono existe **um** caminho:

    cd motor-simulacao
    .\.venv\Scripts\python.exe scripts\probe_todos.py            # Windows
    .venv/bin/python scripts/probe_todos.py                      # macOS
    ... --bancos fontecred,pan                                   # subconjunto

Headed, um banco por vez (o teto de 2 browsers e decisao B+D de IP). Log por etapa com
flush, screenshot na falha e tabela final em `data/probes/<carimbo>/` — tudo fora do git.

Credenciais e dados do cliente vem de `motor-simulacao/.env.local` (gitignored). Erro fatal
ja cometido: preencher o `.env.local.exemplo`, que e so o modelo. O runner detecta e diz o
comando de renomear. **Os dois** estao no `.gitignore` desde 04/09; antes o `.exemplo` era
untracked-e-nao-ignorado, e um `git add -A` teria commitado seis senhas de portal.

Rodada de referencia (04/09/2026, IP residencial, placa FUV7G58 / R$ 21.900):

| Banco | Tempo | Prazos | Entrada exigida |
|---|---|---|---|
| Fontecred | 53s | 24/36/48 | R$ 5.278,36 |
| Pan | 41s | **so 48** | R$ 6.324,00 |
| Bradesco | 56s | 24/36/48 | nenhuma |
| Santander | 137s | 24/36/48 | R$ 1.386,00 |

Dois numeros que valem como marco:

- **O Bradesco fez a analise SCR em 8 segundos.** No Fly a mesma etapa passa de 4 minutos.
  E o gate que o `README.md:90` define para a hipotese de IP residencial (opcao I). Uma
  corrida nao fecha o assunto, mas o sinal e forte.
- **O Pan devolve so o prazo 48**, mesmo pedindo 24/36/48. Os outros tres devolvem os tres.
  Nao investigado: pode ser o portal, pode ser o parser.

Antes de mexer em seletor de portal, rode um `scripts/_diag*.py` (fora do git) que despeja
o DOM. Em 04/09 supor em vez de olhar custou dois diagnosticos errados; o diag resolveu
cada um em uma rodada. Ver [[2026-09-04-is-visible-mente-com-modal-recortado]].
