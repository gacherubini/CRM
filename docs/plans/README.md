# Índice dos planos

## Ordem válida de implementação

| Ordem | Plano | Produto | Pode ser vendido sozinho? |
|---:|---|---|---|
| 0 | [Plano #0](2026-07-11-plano0-fundacao-core-dominio-seguranca.md) | Contratos e segurança | Fundação comum, não produto |
| 1 | [Plano #1A](2026-07-11-plano1a-motor-simulacao-independente.md) | Motor de Simulação | Sim |
| 2 | [Plano #4A](2026-07-11-plano4a-estoque-api-independente.md) | Estoque API/admin e modo Lite | Sim |
| 3 | [Plano #2A](2026-07-11-plano2a-chatbot-standalone-revendivel.md) | Chatbot + Estoque Lite | Sim |
| 4 | [Plano #5A](2026-07-11-plano5a-catalogo-publico-independente.md) | Catálogo Público | Sim, conectado ou bundle com Estoque |
| 5 | [Plano #3A](2026-07-11-plano3a-portal-vendedor-independente.md) | Portal/CRM do vendedor | Sim |
| 5.1 | [Plano #3A.1](2026-07-11-plano3a1-frontend-dashboard-mvp.md) | Frontend/BFF do Dashboard MVP | Workstream executável do #3A |
| 6 | [Plano #3B](2026-07-11-plano3b-dashboard-dono-vendas-metas.md) | Vendas, metas e dashboard | Extensão do Portal #3A |
| futuro | [Plano #6](2026-07-11-plano6-evolucoes-roadmap.md) | Add-ons por produto | Conforme item |

Planos #1A e #4A podem avançar em paralelo depois do Plano #0. O #2A depende da fatia Lite do #4A.
A numeração representa o histórico do projeto, não uma obrigação de construir Portal antes de
Estoque/Catálogo.

## Pacotes comerciais

- **Chatbot Atendimento:** Plano #2A + Estoque Lite; sem Motor obrigatório.
- **Chatbot Financiamento:** Plano #2A + provider do Plano #1A.
- **Motor:** Plano #1A sozinho.
- **Estoque:** Plano #4A sozinho.
- **Catálogo conectado:** Plano #5A apontando ao Estoque existente.
- **Catálogo Standalone:** Plano #5A empacotado com a operação mínima do Plano #4A.
- **Portal do Vendedor:** Plano #3A empacotado com Estoque API; Bot/Motor opcionais.
- **Gestão completa:** Planos #3A + #3B + Estoque API, podendo integrar Bot/Motor/Catálogo.

## Documentos legados

Os arquivos originais #1–#5 permanecem para preservar pesquisa, exemplos e histórico. Seus títulos
estão marcados como `LEGADO — NÃO EXECUTAR`; eles não definem mais arquitetura, propriedade de dados
ou ordem de implementação.
