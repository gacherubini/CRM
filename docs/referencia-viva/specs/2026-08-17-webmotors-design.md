# Webmotors — canal de publicação (design)

Data: 2026-08-17 · Produtos: **Estoque API** (`estoque-api`), **Revy Control** (`revy-trafego`)
e **Revy Loja** (`portal-gestao`)
Estado: **desenhado, não implementado**
Depende de [`2026-08-17-publicacao-por-canal-design.md`](2026-08-17-publicacao-por-canal-design.md).

Calibrado contra o main em `ce36207`. Levantado em 17/08 contra os WSDL de produção, o manual de
integração e a central de ajuda da Webmotors.

---

## 1. Duas surpresas que mudam o desenho

### 1.1 Não é REST. É SOAP.

O portal do desenvolvedor da Webmotors (gateway Sensedia) é REST com OAuth 2.0 e documenta
**leads, catálogo, site e classificados**. O caminho de **publicar estoque** não está lá: é o
serviço SOAP legado em `integracao.webmotors.com.br`, ASP.NET `.asmx`.

A evidência é de três lados: o menu do portal tem "Integração Revendedor" que **aponta para
fora**, para o manual em `integracao.webmotors.com.br/manualintegracao/`; o perfil de usuário que
o lojista cria no Cockpit chama-se exatamente "Integração Revendedor"; e o API Browser da
Sensedia, que enumera todas as REST do gateway, **não tem nenhuma de gestor de estoque**.

> Isto seria a **primeira integração SOAP do monorepo**. Não é impeditivo — é custo de biblioteca
> e de forma, e precisa estar no orçamento da tarefa em vez de aparecer no meio dela.

### 1.2 Moto é serviço separado, e isso é ótimo

Não existe campo `tipoVeiculo`. Carro e moto são **serviços e objetos distintos**:

| | Carro | Moto |
|---|---|---|
| Serviço | `wsEstoqueRevendedorCarros.asmx` | **`wsEstoqueRevendedorMotos.asmx`** |
| Objeto | `AnuncioWM` | **`AnuncioMotoWM`** |
| Catálogo | — | **`wsCodigosWebMotorsMotos.asmx`** |

A pergunta eliminatória ("Webmotors aceita moto?") está respondida: **sim**, com serviço, catálogo
e assinatura comercial próprios. A Revy só usa o lado de moto.

---

## 2. Decisões tomadas

| # | Decisão | Por quê |
|---|---|---|
| W1 | `modo="api"`, transporte **SOAP** | §1.1 |
| W2 | `retry="idempotente"` **só depois** de resolver criar-vs-alterar (§5) | `incluirMoto` não é idempotente |
| W3 | `TipoConsistencia = 0` | §4.3 — é o que torna o canal viável sem inventar seis campos técnicos |
| W4 | `suporta_remocao=True`, `remove_ao_vender=True` | `excluirMoto` existe |
| W5 | Credencial por loja, guardada no Control | §3.2 |
| W6 | **Nunca** mandar `custo` em campo nenhum | §4.2 — `PrecoRevenda` é armadilha |

---

## 3. O que a Webmotors exige de fora

### 3.1 Do lojista

| Passo | Nota |
|---|---|
| Contratar **Assinatura de Motos** | é o nome contratual exato; os outros são Plano Controle e Plano Performance |
| Aceitar o Termo de Adesão no Cockpit | |
| Pedir usuário perfil **"Integração Revendedor"** | só Administrador ou Gerente pode pedir; senha temporária **expira em 24h**; cada loja tem **apenas um** |

> **A credencial é escopada, e isso importa para o invariante de segredo.** O usuário
> "Integração Revendedor" **não tem acesso ao Cockpit** — serve só para autenticar o gestor de
> estoque. Guardar essa credencial não é guardar a senha do lojista; é guardar uma credencial de
> serviço criada para isso. É materialmente diferente do padrão de mercado descrito em §6.2 do
> esqueleto, e é o que torna este canal aceitável.

### 3.2 Da Revy

Registro no portal do desenvolvedor, homologação, e promoção para produção.

> **A janela de 90 dias.** *"Os acessos ao ambiente de testes/homologação serão revogados após 90
> dias corridos ou quando a integração for aprovada e promovida para produção, o que ocorrer
> primeiro"*, contados da liberação das credenciais. E o ambiente de homologação só roda
> **segunda a sexta, 08h–20h** — fora disso, e em feriado nacional, está fora do ar.
>
> Consequência de planejamento: **não se abre o acesso para ir olhando.** Abre quando houver quem
> termine dentro da janela, contando só dias úteis em horário comercial.

A Webmotors publica a lista de gestores de estoque já homologados — Byus, ALM, RevendaPro, Boom,
BNDV, Revenda Mais, Altimus, Disal, Click Garage, AutoGestor, EasyCar, Localiza, BRDealer,
Batcar, Simples Veículo, DuSeller. A Revy entra nessa lista.

---

## 4. O protocolo

### 4.1 Autenticação — sessão, não token

```
wsLoginSistemaRevendedor.asmx
autenticar(cnpj, email, senha) → { HashAutenticacao, CodigoRetorno }
```

O `HashAutenticacao` é o **primeiro argumento de toda chamada seguinte** — não é header. A sessão
dura **1000 minutos**.

Não há OAuth e não há identidade de integrador neste caminho: o protocolo só conhece a loja. A
credencial (CNPJ, e-mail, senha) vive cifrada no Control, no mesmo molde das outras conexões, e o
hash de sessão é cache em memória com validade menor que os 1000 minutos.

### 4.2 O objeto da moto

Obrigatórios sempre: `CodigoMarca`, `CodigoModelo`, `AnoDoModelo`, `AnoFabricacao`,
`CodigoModalidade`, `CodigoCorPredominante`, `PrecoVenda`, `PrecoRevenda`, `IpvaPago` (S/N),
`Licenciado` (S/N), `TipoAnuncio` (`U` \| `N`), `CodigoSMS`, `TipoConsistencia`.

Condicionais: `Placa` (**só usada**), `UnicoDono`, `Alienado`, `GarantiaDeFabrica`.

**Chassi e RENAVAM não existem neste objeto.** Zero ocorrências no WSDL e no manual. A identidade
do veículo é a placa, e só para moto usada — o oposto do Mercado Livre, que exige os dois.

O que a Revy **não tem** hoje:

| Campo | Situação |
|---|---|
| `AnoFabricacao` | `Veiculo` só tem `ano_modelo`. **Coluna nova**, requisito bloqueante — derivar seria inventar dado |
| `IpvaPago`, `Licenciado` | não existem. Duas colunas booleanas, opcionais no cadastro, requisito deste canal |
| `CodigoModalidade` | vem do pacote contratado pela loja; é configuração da conexão, não do veículo |
| `CodigoSMS` | significado não documentado publicamente — **aberto** (§7) |
| `PrecoRevenda` | **aberto e perigoso** — ver abaixo |

> **`PrecoRevenda` nunca recebe `custo`.** O campo `Veiculo.custo` está marcado *"nunca público"*
> no modelo, e o nome `PrecoRevenda` convida ao erro. Enquanto o significado exato não for
> confirmado em homologação, este canal **não** manda `custo` para lugar nenhum. Se a única saída
> for mandar custo, isso volta como decisão do dono, não como detalhe de implementação.

`TipoAnuncio` deriva de `km == 0` → `N`, senão `U` — mesma regra do `state_of_vehicle` do catálogo
Meta.

### 4.3 `TipoConsistencia = 0` é o que torna isto viável

Nenhum `Codigo*` aceita texto livre: marca, modelo, cor, número de marchas, tipo de refrigeração,
alimentação, motor, partida e freio têm que ser resolvidos antes em `wsCodigosWebMotorsMotos`.

Seis desses são **especificação técnica da moto que a Revy não guarda** e que o vendedor não vai
digitar.

A saída está no próprio protocolo:

> `TipoConsistencia = 0` — *"o sistema não fará a validação dos campos acima citados e fará o
> cadastro dos mesmos com os dados registrados na WebMotors"*.

Ou seja: identificado marca, modelo e ano, a **Webmotors preenche a ficha técnica do catálogo
dela**. Com `1`, ela valida contra o que mandamos — e aí a Revy precisaria de seis campos novos
no cadastro de toda moto.

W3 escolhe `0`. É a decisão que separa "um adaptador" de "um projeto de cadastro técnico".

Resta resolver **marca, modelo e cor**, que a Revy tem como texto livre e a Webmotors quer como
código. Isso é uma tabela de-para por loja-nenhuma (é global), alimentada do catálogo deles e
revisada quando não casar. É o maior item de trabalho da spec.

### 4.4 Retornos

> **`CodigoRetorno = 500` significa SUCESSO.** *"500 | Operação realizada com sucesso"*. Mapear
> para HTTP 500 é o erro que vai acontecer, e por isso está escrito aqui em vez de descoberto lá.

Cota esgotada é **resultado normal**, não exceção: `43|32` sem anúncios na modalidade, `43|33`
pacote esgotado, `43|34` sem venda vigente. Tratamento igual ao slot da OLX — erro com instrução
para o lojista, **sem** reagendar.

`excluirMoto` exige `MotivoExclusao` em `1, 2 ou 3`. Excluir de novo devolve `47|79` *"Anúncio já
foi excluído"*, o que torna a remoção seguramente repetível.

---

## 5. Criar não é idempotente

`incluirMoto` não aceita chave externa: a Webmotors atribui o `CodigoAnuncio` e devolve. Reenviar
cria **um segundo anúncio** — e consome cota.

Então o adaptador nunca "publica": ele decide.

```
id_externo vazio      → incluirMoto,  guarda CodigoAnuncio
id_externo preenchido → alterarMoto
```

`obterEstoqueAtualMotos` é a primitiva de reconciliação: lista o que está no ar e permite
reconstruir o mapeamento se ele se perder. É o que salva o caso de resposta perdida.

**Cinco campos são imutáveis depois de criados** — Marca (`47|69`), Modelo (`47|70`), Ano Modelo
(`47|71`), Ano de Fabricação (`47|72`) e Tipo de Anúncio (`47|73`). Corrigir qualquer um exige
excluir e recriar, **queimando cota**. Isso precisa aparecer na tela: corrigir a marca de uma moto
publicada não é edição, é republicação.

---

## 6. Testes

```bash
cd estoque-api   && .venv/bin/python -m pytest -q   # Win: .\.venv\Scripts\python.exe -m pytest -q
cd portal-gestao && .venv/bin/python -m pytest -q
cd revy-trafego  && .venv/bin/python -m pytest -q
```

O adaptador SOAP é testado contra WSDL local e respostas gravadas. Nenhum teste toca a Webmotors.

| Teste | Por quê |
|---|---|
| `CodigoRetorno=500` é tratado como **sucesso** | §4.4; o erro mais provável da implementação inteira |
| `id_externo` vazio chama `incluirMoto`; preenchido chama `alterarMoto` | §5; se inverter, duplica anúncio e queima cota |
| `CodigoAnuncio` é persistido **antes** de qualquer retry | §5 |
| `custo` não aparece em nenhum campo do envelope | W6; vazamento de custo é dano ao lojista |
| `TipoConsistencia` vai `0` | W3; com `1` toda moto passa a exigir seis campos técnicos |
| cota esgotada vira erro **sem** reagendar | §4.4 |
| `MotivoExclusao` ∈ {1,2,3} | §4.4 |
| moto sem `ano_fabricacao` fica bloqueada neste canal | §4.2 |
| `TipoAnuncio` = `N` quando `km == 0` | §4.2 |
| hash de sessão é reusado e renovado antes dos 1000 min | §4.1 |
| senha da loja nunca aparece em log nem em erro | invariante do `AGENTS.md` |

---

## 7. Riscos e o que fica aberto

**Aberto — `PrecoRevenda`.** §4.2. É o item mais sensível e a decisão conservadora já está
tomada: não mandar custo.

**Aberto — `CodigoSMS`.** Obrigatório e sem significado documentado publicamente. Descobre-se em
homologação.

**Aberto — limites de foto.** Quantidade, tamanho e dimensão não estão no manual nem no WSDL. As
fotos vão uma por chamada, em `base64`. Mede-se em homologação.

**Aberto — limite de requisições.** O gateway Sensedia documenta `429` e `413`, mas sem números —
e o caminho SOAP pode nem passar pelo gateway. Pergunta para o chamado que pede a homologação.

**Aberto — `Observacao`.** A tabela de tipos diz máximo 100 caracteres; o código de erro `43|97`
fala em 1500. A fonte primária se contradiz. **Assumir 100** até medir.

**Risco — a de-para de marca e modelo.** §4.3. É o maior item de trabalho e o que mais vai gerar
"por que essa moto não publica". Precisa de tela para ver o que não casou, senão vira suporte.

**Risco — a janela de 90 dias.** §3.2. Só se abre com equipe pronta.

**Fora de escopo — lead.** A Webmotors expõe consulta e inclusão de lead pelas APIs REST do
portal. Dono desse eixo é o Chatbot. **A Webmotors gera lead e hoje ele não entra na Revy.**
