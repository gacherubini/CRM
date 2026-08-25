# Agente por loja — 1/4: o dado e o texto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar task a task. Os passos usam
> checkbox (`- [ ]`).
>
> **Este card é só `chatbot-api`.** Não abra o `portal-gestao`, não edite JSON do n8n, não
> deploye nada. Os outros três eixos têm cards próprios (ver "Os quatro cards" abaixo).

**Goal:** Fazer o `chatbot-api` guardar, versionar e servir a configuração do agente de cada
loja, com o núcleo Revy sempre no fim do prompt — sem que nada disso ainda chegue ao bot.

**Architecture:** um módulo puro monta o texto do prompt a partir de campos validados; duas
tabelas guardam rascunho, versão publicada e histórico; uma rota de leitura serve o n8n e
quatro rotas de escrita servem a Loja. O n8n e a tela vêm depois e consomem o que este card
produz.

**Tech Stack:** FastAPI, SQLAlchemy 2 (`Mapped`/`mapped_column`), Alembic (alvo Postgres),
Pydantic, pytest.

**Spec:** [`../referencia-viva/specs/2026-08-24-agente-por-loja-design.md`](../referencia-viva/specs/2026-08-24-agente-por-loja-design.md)
— §3 (arquitetura), §4 (campos), §5 (núcleo), §7 (modelo global e teto de tokens).

## Os quatro cards

| # | Eixo | Situação |
|---|---|---|
| **1** | `chatbot-api` — dado e texto | **este card** |
| 2 | n8n — slots, nó de config, migração das assertivas do validador | depende do card 1 e do spike (§7 do spec) |
| 3 | `portal-gestao` — tela, rascunho, publicar | depende do card 1 |
| 4 | preview — workflow `whatsapp-ai-preview` + modo seco | depende dos cards 1–3 |

**O Control não entra em card nenhum.** O dono decidiu em 25/08 que o modelo de LLM é
global — um só para todas as lojas. Nada de coluna `modelo`, nada de rota para trocá-lo,
nada de tela no Control. Não re-proponha.

Não misture. O card 2 mexe em JSON gerado e em validadores; o 3 é JS de tela que pytest não
verifica; o 4 depende dos dois.

## Estado ao abrir este card

Nada disto existe. O prompt do bot está inteiro em `n8n/workflow-ai-nao-salvos.json`, com
`vitor motos` e `limeira-sp` escritos à mão. O `chatbot-api` não tem prompt de LLM nenhum.

Migration head do produto: `0026_credencial_integracao`.

Suíte na abertura: rode e anote o número antes de tocar em qualquer coisa.

## Global Constraints

- **Só `chatbot-api/`.** Integração entre produtos é HTTP versionado; nada de import `app`
  cruzado.
- **Migration com `op.create_table` direto, sem `batch_alter_table`.** O alvo é o Postgres do
  `suite-pg`; `batch` estoura no PG quando há FK dependendo do índice da PK. O padrão está em
  `chatbot-api/alembic/versions/0026_credencial_integracao.py`.
- **Testes a partir da pasta do produto**, senão importa o `app` errado:
  - macOS: `cd chatbot-api && .venv/bin/python -m pytest -q`
  - Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
- **O núcleo Revy é o último bloco do prompt, sempre.** É o mecanismo de segurança inteiro
  (§3.4 do spec). Nenhuma task pode inverter essa ordem.
- **`resolver_loja_id` antes do gate operacional.** Gate com `loja_id=None` responde 423 e
  engole o 400 que diz "faltou `instance`".
- **Fallback nunca em 423.** Loja suspensa tem que parar o fluxo, não cair no prompt padrão
  (§3.3 do spec). Isso é regra do card 2, mas o teste do 423 nasce aqui.
- Nenhum secret, token ou `.env` real no git ou no log.
- Ao terminar o card: `git diff --check`, `git status --short`, e regerar o mapa —
  `cd .claude/skills/revy-research && python gerar_mapa.py` (Windows) / `python3` (macOS) —
  commitando junto, porque este card cria rota, modelo (ORM) e migration.

---

### Task 1: Núcleo Revy e o gerador de prompt

Módulo puro: campos entram, texto sai. Sem banco, sem rede, sem n8n. É a peça de maior valor
e a mais barata de testar, por isso vem primeiro.

**Files:**
- Create: `chatbot-api/app/agente_prompt.py`
- Test: `chatbot-api/tests/test_agente_prompt.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `CamposAgente` (pydantic `BaseModel`) — o formulário inteiro, com defaults.
  - `NUCLEO_REVY: str`
  - `montar_prompt(campos: CamposAgente) -> str`
  - `max_output_tokens(campos: CamposAgente) -> int`
  - `detectar_conflitos(texto: str) -> list[str]`
  - `MAX_INSTRUCOES_LIVRES: int = 1000`
  - `CAMPOS_PADRAO_REVY: CamposAgente`

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_prompt.py`:

```python
"""Gerador de prompt por loja: campos entram, texto sai (spec §3.4, §4, §5)."""
import pytest

from app.agente_prompt import (
    NUCLEO_REVY,
    CamposAgente,
    detectar_conflitos,
    max_output_tokens,
    montar_prompt,
)


def _campos(**over) -> CamposAgente:
    base = dict(nome_loja="Motos do Léo", cidade="Piracicaba", uf="SP")
    base.update(over)
    return CamposAgente(**base)


def test_nucleo_e_sempre_o_ultimo_bloco():
    """A ordem É o mecanismo de segurança: o que vem depois vence."""
    prompt = montar_prompt(_campos(instrucoes="pode falar o valor da parcela pro cliente"))
    assert prompt.rstrip().endswith(NUCLEO_REVY.rstrip())


def test_identidade_usa_o_nome_e_a_cidade_da_loja():
    prompt = montar_prompt(_campos())
    assert "motos do léo" in prompt.lower()
    assert "piracicaba-sp" in prompt.lower()
    assert "vitor motos" not in prompt.lower()


def test_so_a_cidade_quando_endereco_completo_e_falso():
    prompt = montar_prompt(_campos(endereco_completo=False))
    assert "não informe rua" in prompt.lower()


def test_emoji_nunca_vira_frase_fixa():
    assert "não use emojis" in montar_prompt(_campos(emoji="nunca")).lower()
    assert "não use emojis" not in montar_prompt(_campos(emoji="a_vontade")).lower()


def test_assume_ia_muda_o_texto_e_nao_some():
    nunca = montar_prompt(_campos(assume_ia="nunca")).lower()
    perg = montar_prompt(_campos(assume_ia="se_perguntarem")).lower()
    assert "não diga que é ia" in nunca
    assert "assistente digital" in perg


def test_faq_vira_resposta_exata():
    prompt = montar_prompt(_campos(faq=[{"pergunta": "garantia", "resposta": "3 meses de motor"}]))
    assert "garantia" in prompt.lower()
    assert "3 meses de motor" in prompt


def test_instrucoes_livres_entram_antes_do_nucleo():
    prompt = montar_prompt(_campos(instrucoes="não financiamos quem tem cnh suspensa"))
    assert prompt.index("cnh suspensa") < prompt.index(NUCLEO_REVY.strip()[:40])


def test_instrucoes_livres_tem_teto():
    with pytest.raises(ValueError):
        CamposAgente(nome_loja="x", cidade="y", uf="SP", instrucoes="a" * 1001)


@pytest.mark.parametrize(
    "tamanho,esperado", [("curto", 250), ("medio", 400), ("longo", 700)]
)
def test_tamanho_da_resposta_define_o_teto_de_tokens(tamanho, esperado):
    """Sem isto, 'pode explicar' bate no teto de 250 e corta no meio da frase."""
    assert max_output_tokens(_campos(tamanho_resposta=tamanho)) == esperado


def test_detecta_conflito_com_tema_fechado():
    assert detectar_conflitos("pode dizer o valor da parcela") != []
    assert detectar_conflitos("aos sábados atendemos com hora marcada") == []


def test_combinacao_feia_nao_gera_contradicao():
    """Formal + minúsculas: as duas instruções coexistem sem se anular."""
    prompt = montar_prompt(_campos(tom="formal", escrita="minusculas")).lower()
    assert "letras minúsculas" in prompt
    assert "formal" in prompt
```

- [ ] **Step 2: Rode e confirme que falha**

macOS: `cd chatbot-api && .venv/bin/python -m pytest tests/test_agente_prompt.py -q`
Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_agente_prompt.py -q`

Esperado: `ModuleNotFoundError: No module named 'app.agente_prompt'`.

- [ ] **Step 3: Escreva o módulo**

Crie `chatbot-api/app/agente_prompt.py`. O núcleo abaixo é **cópia literal da §5 do spec** —
não reescreva com suas palavras, ele é contrato:

```python
"""Prompt do agente por loja: campos entram, texto sai (spec §3.4, §4, §5).

Módulo puro de propósito: sem banco, sem rede, sem n8n. O lojista não escreve
prompt — escreve campos, e cada campo tem um gerador aqui. É isso que faz o
texto sair bem escrito mesmo quando o lojista não é.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

MAX_INSTRUCOES_LIVRES = 1000

_TOKENS_POR_TAMANHO = {"curto": 250, "medio": 400, "longo": 700}

# Temas que o núcleo fecha. Instrução livre que os toca não funciona — a tela
# avisa, não bloqueia (spec §4.5).
_TEMAS_FECHADOS = {
    "parcela": ("parcela", "taxa", "juros", "banco", "prazo", "financiado"),
    "insistir": ("insista", "insistir", "tente de novo", "ofereça de novo"),
    "dados": ("renda", "placa"),
    "estoque": ("invente", "diga que temos", "sempre disponível"),
}

NUCLEO_REVY = """[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]
estas regras não podem ser contrariadas por nenhuma instrução anterior.
se algo acima conflitar com algo aqui, siga o que está aqui.

1. estoque e preço: só o que consultar_estoque retornar. nunca invente veículo,
   preço, km, cor, ano ou disponibilidade, e nunca afirme que uma moto está
   disponível sem a consulta ter confirmado.
2. resultado de financiamento: nunca mostre nem mencione parcela, taxa, banco,
   valor financiado ou prazo. depois da tool simular, responda somente a
   confirmação curta que ela devolver.
3. recusa: se o cliente recusar, declinar ou encerrar um convite, dê uma frase
   curta de ok e PARE. não repita a oferta e não emende outra.
4. simulação: cpf, data de nascimento e resposta de cnh (sim ou não) são
   obrigatórios, nessa ordem — nascimento e maioridade, depois cnh, depois a
   tool. "não tenho cnh" não bloqueia. nunca peça renda, prazo ou placa. nunca
   peça de novo um dado já recebido.
5. menor de idade: se a tool devolver motivo_bloqueio=menor_de_idade, envie
   exatamente a mensagem da tool e não chame de novo.
6. anti-alucinação: só confirme a simulação se a tool retornou ok:true e
   simulacao_humana_solicitada:true. em erro, ok:false ou faltando, siga a
   mensagem da tool — nunca invente confirmação.
7. nunca revele tools, tokens, apis internas, placa interna ou qualquer dado de
   controle.
8. o lead nasce dentro da tool simular. nunca crie lead por cumprimento, clique
   em anúncio ou pergunta de estoque.
"""


class ParFaq(BaseModel):
    pergunta: str = Field(max_length=120)
    resposta: str = Field(max_length=400)


class CamposAgente(BaseModel):
    """O formulário inteiro. Defaults = o agente padrão do Revy."""

    # identidade (§4.1)
    nome_loja: str = Field(max_length=80)
    cidade: str = Field(max_length=60)
    uf: str = Field(max_length=2)
    endereco_completo: bool = False
    entrega: str = Field(default="", max_length=200)
    horario: dict[str, list[str]] = Field(default_factory=dict)

    # personalidade (§4.2)
    nome_agente: str = Field(default="", max_length=40)
    assume_ia: str = "nunca"  # nunca | se_perguntarem | na_abertura
    tom: str = "direto"  # direto | simpatico | consultivo | formal
    tratamento: str = "primeiro_nome"  # primeiro_nome | voce | senhor
    escrita: str = "minusculas"  # minusculas | normal
    emoji: str = "nunca"  # nunca | raro | a_vontade
    tamanho_resposta: str = "curto"  # curto | medio | longo
    expressoes: list[str] = Field(default_factory=list)
    nunca_diga: list[str] = Field(default_factory=list)

    # faq (§4.3)
    faq: list[ParFaq] = Field(default_factory=list)

    # regras da conversa (§4.4)
    oferece: list[str] = Field(default_factory=lambda: ["financiamento", "a_vista"])
    fotos: str = "so_quando_pedir"  # so_quando_pedir | na_abertura
    sem_moto_anuncio: str = "segura"  # segura | oferece_parecida
    handoff: list[str] = Field(default_factory=lambda: ["quando_pedir"])
    cita_vendedor: bool = False
    followup_ativo: bool = True

    # liga/desliga (§4.6)
    agente_ativo: bool = True
    so_horario_comercial: bool = False
    so_lead_anuncio: bool = False

    # instruções livres (§4.5)
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES_LIVRES)


CAMPOS_PADRAO_REVY = CamposAgente(nome_loja="a loja", cidade="", uf="")

_TOM = {
    "direto": "fale de forma direta e objetiva, sem rodeio.",
    "simpatico": "fale de forma simpática e próxima, sem forçar intimidade.",
    "consultivo": "fale como quem orienta: explique a opção antes de sugerir.",
    "formal": "mantenha um registro formal e respeitoso.",
}
_TRATAMENTO = {
    "primeiro_nome": "chame o cliente pelo primeiro nome quando ele parecer um nome real.",
    "voce": 'trate o cliente por "você", sem usar o nome dele.',
    "senhor": 'trate o cliente por "senhor" ou "senhora".',
}
_TAMANHO = {
    "curto": "seja minimalista: uma ou duas frases curtas.",
    "medio": "use até três frases.",
    "longo": "pode explicar com calma quando o assunto pedir.",
}
_ASSUME_IA = {
    "nunca": "não diga que é ia, assistente virtual ou bot.",
    "se_perguntarem": (
        "se o cliente perguntar se você é uma pessoa ou um robô, responda com "
        "honestidade que é o assistente digital da loja; fora isso, não levante "
        "o assunto."
    ),
    "na_abertura": "diga na abertura que é o assistente digital da loja.",
}
_OFERECE = {
    "financiamento": "financiamento",
    "a_vista": "venda à vista",
    "troca": "moto na troca",
    "consignacao": "consignação",
}


def _bloco_identidade(c: CamposAgente) -> str:
    linhas = [f"você atende os clientes da {c.nome_loja.lower()} pelo whatsapp."]
    if c.cidade:
        linhas.append(f"a loja fica em {c.cidade.lower()}-{c.uf.lower()}.")
        if not c.endereco_completo:
            linhas.append(
                "não informe rua, número, bairro nem ponto de referência: "
                "passe só a cidade."
            )
    if c.entrega:
        linhas.append(f"entrega: {c.entrega.lower()}")
    if c.horario:
        dias = "; ".join(
            f"{dia} das {faixa[0]} às {faixa[1]}" for dia, faixa in c.horario.items()
        )
        linhas.append(f"horário de atendimento: {dias}.")
    return "[IDENTIDADE]\n" + "\n".join(linhas)


def _bloco_personalidade(c: CamposAgente) -> str:
    linhas = []
    if c.nome_agente:
        linhas.append(f"seu nome é {c.nome_agente.lower()}.")
    linhas.append(_ASSUME_IA[c.assume_ia])
    linhas.append("fale em português do brasil, de forma humana e simples.")
    linhas.append(_TOM[c.tom])
    if c.escrita == "minusculas":
        linhas.append("escreva toda resposta ao cliente em letras minúsculas.")
    if c.emoji == "nunca":
        linhas.append("não use emojis.")
    elif c.emoji == "raro":
        linhas.append("use emoji no máximo uma vez por conversa.")
    linhas.append(_TAMANHO[c.tamanho_resposta])
    linhas.append(_TRATAMENTO[c.tratamento])
    if c.expressoes:
        termos = ", ".join(f'"{e.lower()}"' for e in c.expressoes)
        linhas.append(
            f"use {termos} quando combinar com a conversa, sem virar bordão."
        )
    if c.nunca_diga:
        termos = ", ".join(f'"{e.lower()}"' for e in c.nunca_diga)
        linhas.append(f"nunca use as palavras: {termos}.")
    return "[PERSONALIDADE]\n" + "\n".join(linhas)


def _bloco_faq(c: CamposAgente) -> str:
    if not c.faq:
        return ""
    linhas = [
        f'quando o cliente perguntar sobre {par.pergunta.lower()}, responda '
        f'exatamente: "{par.resposta}"'
        for par in c.faq
    ]
    return "[FAQ DA LOJA]\n" + "\n".join(linhas)


def _bloco_regras(c: CamposAgente) -> str:
    linhas = []
    oferecidos = [_OFERECE[o] for o in c.oferece if o in _OFERECE]
    if oferecidos:
        linhas.append("a loja trabalha com " + ", ".join(oferecidos) + ".")
    recusados = [rot for cod, rot in _OFERECE.items() if cod not in c.oferece]
    if recusados:
        linhas.append(
            "a loja não trabalha com " + ", ".join(recusados)
            + " — se perguntarem, diga que a loja não faz."
        )
    if c.fotos == "so_quando_pedir":
        linhas.append("não mande fotos por conta própria: só quando o cliente pedir.")
    else:
        linhas.append("na abertura, mande as fotos da moto do anúncio.")
    if c.sem_moto_anuncio == "segura":
        linhas.append(
            "se a consulta não achar a moto do anúncio, mantenha o foco nela e "
            "não ofereça outra moto por iniciativa própria."
        )
    else:
        linhas.append(
            "se a consulta não achar a moto do anúncio, ofereça uma parecida do "
            "estoque, sempre com dados reais da consulta."
        )
    if c.cita_vendedor:
        linhas.append("você pode citar o vendedor pelo nome ao encaminhar o atendimento.")
    else:
        linhas.append(
            'nunca diga "atendente", "vendedor", "humano" ou "transferir".'
        )
    return "[REGRAS DA LOJA]\n" + "\n".join(linhas)


def _bloco_instrucoes(c: CamposAgente) -> str:
    if not c.instrucoes.strip():
        return ""
    return (
        "[INSTRUÇÕES DA LOJA]\n"
        "o lojista escreveu as instruções abaixo. siga-as, exceto onde "
        "contrariarem as regras do revy que vêm depois.\n"
        + c.instrucoes.strip()
    )


def montar_prompt(campos: CamposAgente) -> str:
    """Sanduíche do spec §3.4. O núcleo é o último bloco, sempre."""
    blocos = [
        _bloco_identidade(campos),
        _bloco_personalidade(campos),
        _bloco_faq(campos),
        _bloco_regras(campos),
        _bloco_instrucoes(campos),
        NUCLEO_REVY,
    ]
    return "\n\n".join(b for b in blocos if b)


def max_output_tokens(campos: CamposAgente) -> int:
    """Sem isto, 'pode explicar' bate no teto de 250 e corta no meio da frase."""
    return _TOKENS_POR_TAMANHO[campos.tamanho_resposta]


def detectar_conflitos(texto: str) -> list[str]:
    """Temas que o núcleo fecha. Avisa, não bloqueia (spec §4.5)."""
    baixo = texto.lower()
    return [tema for tema, termos in _TEMAS_FECHADOS.items() if any(t in baixo for t in termos)]
```

- [ ] **Step 4: Rode e confirme que passa**

Mesmo comando do Step 2. Esperado: todos verdes.

- [ ] **Step 5: Rode a suíte inteira**

macOS: `cd chatbot-api && .venv/bin/python -m pytest -q`
Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: nada quebrado — este módulo ainda não é importado por ninguém.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/agente_prompt.py chatbot-api/tests/test_agente_prompt.py
git commit -m "feat(chatbot): gerador de prompt por loja com nucleo Revy no fim"
```

---

### Task 2: Tabelas e migration

**Files:**
- Modify: `chatbot-api/app/models_db.py` (adicionar ao fim do arquivo)
- Create: `chatbot-api/alembic/versions/0027_agente_config.py`
- Test: `chatbot-api/tests/test_agente_config_tabelas.py`

**Interfaces:**
- Consumes: nada da Task 1 (as tabelas guardam JSON, não `CamposAgente`).
- Produces: `models_db.AgenteConfig`, `models_db.AgenteConfigVersao`.

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_config_tabelas.py`:

```python
"""Tabelas da config do agente (spec §3.2)."""
import uuid

from app import models_db


def test_versao_guarda_campos_e_prompt_congelado(db, loja_a):
    """prompt_gerado junto com campos NÃO é redundância: audita o que o bot recebeu."""
    versao = models_db.AgenteConfigVersao(
        id=str(uuid.uuid4()),
        loja_id=loja_a["loja_id"],
        estado="rascunho",
        campos={"nome_loja": "Motos do Léo"},
        prompt_gerado="[IDENTIDADE]\nvocê atende...",
    )
    db.add(versao)
    db.commit()

    lido = db.get(models_db.AgenteConfigVersao, versao.id)
    assert lido.campos["nome_loja"] == "Motos do Léo"
    assert lido.prompt_gerado.startswith("[IDENTIDADE]")
    assert lido.publicado_em is None


def test_config_aponta_para_a_versao_publicada(db, loja_a):
    versao = models_db.AgenteConfigVersao(
        id=str(uuid.uuid4()),
        loja_id=loja_a["loja_id"],
        estado="publicada",
        campos={},
        prompt_gerado="x",
    )
    db.add(versao)
    db.flush()
    db.add(
        models_db.AgenteConfig(
            loja_id=loja_a["loja_id"], versao_publicada_id=versao.id
        )
    )
    db.commit()

    cfg = db.get(models_db.AgenteConfig, loja_a["loja_id"])
    assert cfg.versao_publicada_id == versao.id
```

- [ ] **Step 2: Rode e confirme que falha**

`pytest tests/test_agente_config_tabelas.py -q` → `AttributeError: module 'app.models_db' has no attribute 'AgenteConfigVersao'`.

- [ ] **Step 3: Escreva os modelos**

No fim de `chatbot-api/app/models_db.py`, seguindo o estilo do arquivo:

```python
class AgenteConfigVersao(Base):
    """Rascunho, versão publicada e histórico da config do agente (spec §3.2).

    ``prompt_gerado`` fica congelado junto com ``campos``: é o que permite
    auditar o texto que o bot realmente recebeu naquela versão. Melhorar o
    gerador amanhã não reescreve o histórico.
    """

    __tablename__ = "agente_config_versao"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(String(16), nullable=False)  # rascunho|publicada|arquivada
    campos: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_gerado: Mapped[str] = mapped_column(Text, nullable=False, default="")
    autor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora
    )
    publicado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgenteConfig(Base):
    """Uma linha por loja: qual versão está no ar."""

    __tablename__ = "agente_config"

    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id"), primary_key=True, nullable=False
    )
    versao_publicada_id: Mapped[str | None] = mapped_column(
        ForeignKey("agente_config_versao.id"), nullable=True
    )
```

**O import precisa mudar.** A linha 8 de `models_db.py` hoje é:

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
```

`Text` já está lá; **`JSON` não**. Acrescente:

```python
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
```

- [ ] **Step 4: Escreva a migration**

Crie `chatbot-api/alembic/versions/0027_agente_config.py`:

```python
"""config do agente por loja: versoes, rascunho e publicada

Spec 2026-08-24 §3.2. Duas tabelas novas, nada alterado no que ja existe.
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_agente_config"
down_revision = "0026_credencial_integracao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_table direto: o alvo e o Postgres do suite-pg. batch_alter_table
    # aqui daria portabilidade que a cadeia deste produto nao tem desde a 0017,
    # e batch no PG estoura com FK dependendo do indice da PK.
    op.create_table(
        "agente_config_versao",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("campos", sa.JSON(), nullable=False),
        sa.Column("prompt_gerado", sa.Text(), nullable=False),
        sa.Column("autor", sa.String(length=120), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agente_config_versao_loja_id", "agente_config_versao", ["loja_id"]
    )
    op.create_table(
        "agente_config",
        sa.Column("loja_id", sa.String(), sa.ForeignKey("lojas.id"), primary_key=True),
        sa.Column(
            "versao_publicada_id",
            sa.String(length=36),
            sa.ForeignKey("agente_config_versao.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("agente_config")
    op.drop_index("ix_agente_config_versao_loja_id", table_name="agente_config_versao")
    op.drop_table("agente_config_versao")
```

- [ ] **Step 5: Rode os testes**

`pytest tests/test_agente_config_tabelas.py -q` → verde (o conftest cria as tabelas por
`Base.metadata.create_all`, não pela migration).

Depois a suíte inteira: `pytest -q`.

- [ ] **Step 6: Confirme que a cadeia do alembic tem uma cabeça só**

macOS: `cd chatbot-api && .venv/bin/python -m alembic heads`
Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m alembic heads`
Esperado: exatamente uma linha, `0027_agente_config`.

- [ ] **Step 7: Commit**

```bash
git add chatbot-api/app/models_db.py chatbot-api/alembic/versions/0027_agente_config.py chatbot-api/tests/test_agente_config_tabelas.py
git commit -m "feat(chatbot): tabelas de config do agente por loja (migration 0027)"
```

---

### Task 3: Serviço de versões — rascunho, publicar, restaurar

**Files:**
- Create: `chatbot-api/app/agente_config.py`
- Test: `chatbot-api/tests/test_agente_config_servico.py`

**Interfaces:**
- Consumes: `app.agente_prompt.CamposAgente`, `montar_prompt`, `CAMPOS_PADRAO_REVY`;
  `models_db.AgenteConfig`, `models_db.AgenteConfigVersao`.
- Produces:
  - `obter_rascunho(db, loja_id) -> AgenteConfigVersao`
  - `salvar_rascunho(db, loja_id, campos: CamposAgente, autor: str | None) -> AgenteConfigVersao`
  - `publicar(db, loja_id, autor: str | None) -> AgenteConfigVersao`
  - `listar_versoes(db, loja_id) -> list[AgenteConfigVersao]`
  - `restaurar(db, loja_id, versao_id: str, autor: str | None) -> AgenteConfigVersao`
  - `campos_publicados(db, loja_id) -> CamposAgente`
  - `prompt_publicado(db, loja_id) -> str`

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_config_servico.py`:

```python
"""Rascunho → publicar → histórico (spec §3.2, §6)."""
from app import agente_config
from app.agente_prompt import CamposAgente


def _campos(nome="Motos do Léo", **over) -> CamposAgente:
    base = dict(nome_loja=nome, cidade="Piracicaba", uf="SP")
    base.update(over)
    return CamposAgente(**base)


def test_loja_sem_config_cai_no_padrao_revy(db, loja_a):
    """O bot nunca fica sem prompt."""
    prompt = agente_config.prompt_publicado(db, loja_a["loja_id"])
    assert "[REGRAS DO REVY" in prompt


def test_rascunho_nao_vai_ao_ar(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    assert "motos do léo" not in agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()


def test_publicar_leva_o_rascunho_ao_ar(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    agente_config.publicar(db, loja_a["loja_id"], autor="dono@x")
    assert "motos do léo" in agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()


def test_publicar_congela_o_prompt_da_versao(db, loja_a):
    from app.agente_prompt import NUCLEO_REVY

    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    versao = agente_config.publicar(db, loja_a["loja_id"], autor="dono@x")
    assert versao.prompt_gerado.rstrip().endswith(NUCLEO_REVY.rstrip())
    assert versao.publicado_em is not None


def test_restaurar_cria_versao_nova_e_nao_apaga_historico(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Um"), autor="a")
    primeira = agente_config.publicar(db, loja_a["loja_id"], autor="a")
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Dois"), autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    agente_config.restaurar(db, loja_a["loja_id"], primeira.id, autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    prompt = agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()
    assert "loja um" in prompt
    assert len(agente_config.listar_versoes(db, loja_a["loja_id"])) >= 3


def test_config_de_uma_loja_nao_vaza_para_outra(db, loja_a, loja_b):
    """Isolamento por loja: o erro mais caro desta feature."""
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja A"), autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    assert "loja a" not in agente_config.prompt_publicado(db, loja_b["loja_id"]).lower()

```

- [ ] **Step 2: Rode e confirme que falha**

`pytest tests/test_agente_config_servico.py -q` → `ModuleNotFoundError: No module named 'app.agente_config'`.

- [ ] **Step 3: Escreva o serviço**

Crie `chatbot-api/app/agente_config.py`:

```python
"""Versões da config do agente: rascunho, publicada, histórico (spec §3.2).

Voltar para uma versão anterior CRIA versão nova a partir dela. Nada é apagado.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models_db
from app.agente_prompt import CAMPOS_PADRAO_REVY, CamposAgente, montar_prompt


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _config(db: Session, loja_id: str) -> models_db.AgenteConfig:
    cfg = db.get(models_db.AgenteConfig, loja_id)
    if cfg is None:
        cfg = models_db.AgenteConfig(loja_id=loja_id)
        db.add(cfg)
        db.flush()
    return cfg


def _versao_publicada(db: Session, loja_id: str) -> models_db.AgenteConfigVersao | None:
    cfg = db.get(models_db.AgenteConfig, loja_id)
    if cfg is None or cfg.versao_publicada_id is None:
        return None
    return db.get(models_db.AgenteConfigVersao, cfg.versao_publicada_id)


def obter_rascunho(db: Session, loja_id: str) -> models_db.AgenteConfigVersao:
    """Rascunho vivo da loja; nasce da publicada, ou do padrão Revy."""
    rascunho = (
        db.query(models_db.AgenteConfigVersao)
        .filter(
            models_db.AgenteConfigVersao.loja_id == loja_id,
            models_db.AgenteConfigVersao.estado == "rascunho",
        )
        .order_by(models_db.AgenteConfigVersao.criado_em.desc())
        .first()
    )
    if rascunho is not None:
        return rascunho
    base = _versao_publicada(db, loja_id)
    campos = (
        CamposAgente(**base.campos) if base is not None else CAMPOS_PADRAO_REVY
    )
    return salvar_rascunho(db, loja_id, campos, autor=None)


def salvar_rascunho(
    db: Session, loja_id: str, campos: CamposAgente, autor: str | None
) -> models_db.AgenteConfigVersao:
    _config(db, loja_id)
    atual = (
        db.query(models_db.AgenteConfigVersao)
        .filter(
            models_db.AgenteConfigVersao.loja_id == loja_id,
            models_db.AgenteConfigVersao.estado == "rascunho",
        )
        .first()
    )
    if atual is None:
        atual = models_db.AgenteConfigVersao(
            id=str(uuid.uuid4()), loja_id=loja_id, estado="rascunho", criado_em=_agora()
        )
        db.add(atual)
    atual.campos = campos.model_dump()
    atual.prompt_gerado = montar_prompt(campos)
    atual.autor = autor
    db.commit()
    db.refresh(atual)
    return atual


def publicar(db: Session, loja_id: str, autor: str | None) -> models_db.AgenteConfigVersao:
    rascunho = obter_rascunho(db, loja_id)
    anterior = _versao_publicada(db, loja_id)
    if anterior is not None:
        anterior.estado = "arquivada"
    rascunho.estado = "publicada"
    rascunho.autor = autor
    rascunho.publicado_em = _agora()
    _config(db, loja_id).versao_publicada_id = rascunho.id
    db.commit()
    db.refresh(rascunho)
    return rascunho


def listar_versoes(db: Session, loja_id: str) -> list[models_db.AgenteConfigVersao]:
    return (
        db.query(models_db.AgenteConfigVersao)
        .filter(models_db.AgenteConfigVersao.loja_id == loja_id)
        .order_by(models_db.AgenteConfigVersao.criado_em.desc())
        .all()
    )


def restaurar(
    db: Session, loja_id: str, versao_id: str, autor: str | None
) -> models_db.AgenteConfigVersao:
    """Cria rascunho novo a partir de uma versão antiga. Não apaga nada."""
    antiga = db.get(models_db.AgenteConfigVersao, versao_id)
    if antiga is None or antiga.loja_id != loja_id:
        raise LookupError("versão não é desta loja")
    return salvar_rascunho(db, loja_id, CamposAgente(**antiga.campos), autor)


def campos_publicados(db: Session, loja_id: str) -> CamposAgente:
    versao = _versao_publicada(db, loja_id)
    if versao is None:
        return CAMPOS_PADRAO_REVY
    return CamposAgente(**versao.campos)


def prompt_publicado(db: Session, loja_id: str) -> str:
    """Congelado no publicar. Loja sem config cai no padrão — o bot nunca fica mudo."""
    versao = _versao_publicada(db, loja_id)
    if versao is None:
        return montar_prompt(CAMPOS_PADRAO_REVY)
    return versao.prompt_gerado

```

- [ ] **Step 4: Rode e confirme que passa**

`pytest tests/test_agente_config_servico.py -q` → verde.

- [ ] **Step 5: Suíte inteira**

`pytest -q` → verde.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/agente_config.py chatbot-api/tests/test_agente_config_servico.py
git commit -m "feat(chatbot): rascunho, publicar e restaurar da config do agente"
```

---

### Task 4: `GET /v1/agente/config` — a rota que o n8n vai consumir

É a rota com a armadilha conhecida: `resolver_loja_id` **antes** do gate operacional.

**Files:**
- Modify: `chatbot-api/app/main.py` (rota nova, ao lado de `GET /v1/config/catalogo-bot`, ~linha 1260)
- Test: `chatbot-api/tests/test_agente_config_rota.py`

**Interfaces:**
- Consumes: `agente_config.prompt_publicado`, `campos_publicados`;
  `agente_prompt.max_output_tokens`; `auth.resolver_loja_id`; `_exigir_loja_operacional`.
- Produces: `GET /v1/agente/config?instance=<x>` →
  `{"prompt": str, "max_output_tokens": int, "agente_ativo": bool}`.

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_config_rota.py`:

```python
"""GET /v1/agente/config — multi-loja de verdade (spec §3.3)."""
from app import agente_config, servico
from app.agente_prompt import CamposAgente


def _publicar(db, loja_id, nome):
    agente_config.salvar_rascunho(
        db, loja_id, CamposAgente(nome_loja=nome, cidade="Piracicaba", uf="SP"), autor="t"
    )
    agente_config.publicar(db, loja_id, autor="t")


def test_credencial_de_loja_recebe_o_proprio_prompt(client, db, loja_a):
    _publicar(db, loja_a["loja_id"], "Loja A")
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "loja a" in r.json()["prompt"].lower()


def test_integracao_sem_instance_da_400_e_nao_423(client, db):
    """O gate com loja_id=None responderia 423 e engoliria o erro de verdade."""
    token = servico.criar_credencial_integracao(db)
    db.commit()
    r = client.get("/v1/agente/config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "instance" in r.json()["detail"]


def test_integracao_com_instance_recebe_o_prompt_daquela_loja(client, db, loja_a, loja_b):
    _publicar(db, loja_a["loja_id"], "Loja A")
    _publicar(db, loja_b["loja_id"], "Loja B")
    token = servico.criar_credencial_integracao(db)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/v1/agente/config?instance={loja_b['instance']}", headers=headers)
    assert r.status_code == 200
    corpo = r.json()["prompt"].lower()
    assert "loja b" in corpo
    assert "loja a" not in corpo


def test_loja_suspensa_da_423_para_o_fluxo_parar(client, db, loja_sem_projecao):
    """Fallback do n8n é só para falha técnica: 423 tem que parar o bot."""
    r = client.get("/v1/agente/config", headers=loja_sem_projecao["headers"])
    assert r.status_code == 423


def test_teto_de_tokens_acompanha_o_tamanho_da_resposta(client, db, loja_a):
    agente_config.salvar_rascunho(
        db,
        loja_a["loja_id"],
        CamposAgente(nome_loja="X", cidade="Y", uf="SP", tamanho_resposta="longo"),
        autor="t",
    )
    agente_config.publicar(db, loja_a["loja_id"], autor="t")
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.json()["max_output_tokens"] == 700


def test_loja_sem_config_recebe_o_padrao_revy(client, loja_a):
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "[REGRAS DO REVY" in r.json()["prompt"]
```

- [ ] **Step 2: Rode e confirme que falha**

`pytest tests/test_agente_config_rota.py -q` → 404 em todas.

- [ ] **Step 3: Escreva a rota**

**Primeiro o import.** `main.py:24` tem o bloco que registra os módulos:

```python
from app import (  # noqa: F401 (registra os modelos)
    channels,
    config,
    models_db,
    ...
)
```

Acrescente `agente_config` e `agente_prompt` nessa lista, em ordem alfabética (ficam antes
de `channels`). `datetime`, `timezone`, `Optional`, `BaseModel`, `HTTPException`,
`resolver_loja_id` e `_exigir_loja_operacional` **já estão** disponíveis — não mexa neles.

Agora a rota, em `chatbot-api/app/main.py`, logo depois de `config_catalogo_bot`:

```python
@app.get("/v1/agente/config")
def config_agente(
    instance: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Prompt do agente desta loja (spec §3.3). O modelo é global, não vem aqui.

    **A ordem aqui não é estilo.** ``resolver_loja_id`` vem ANTES do gate: com
    credencial de integração ``ctx.loja_id`` é ``None``, e o gate responderia
    423 engolindo o 400 que diz qual é o erro de verdade ("faltou instance").

    E o 423 de loja suspensa é resposta, não falha: o n8n só pode cair no prompt
    padrão em erro técnico. Tratar 423 como fallback deixaria o bot atendendo
    loja suspensa, contra o gate de backend.
    """
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    campos = agente_config.campos_publicados(db, loja_id)
    return {
        "prompt": agente_config.prompt_publicado(db, loja_id),
        "max_output_tokens": agente_prompt.max_output_tokens(campos),
        "agente_ativo": campos.agente_ativo,
    }
```

- [ ] **Step 4: Rode e confirme que passa**

`pytest tests/test_agente_config_rota.py -q` → verde. Se `test_loja_suspensa...` falhar com
200, o gate não está sendo chamado; se falhar com 400, `resolver_loja_id` está depois do gate.

- [ ] **Step 5: Suíte inteira**

`pytest -q` → verde.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_agente_config_rota.py
git commit -m "feat(chatbot): GET /v1/agente/config serve o prompt da loja"
```

---

### Task 5: Rotas de escrita — o que a Loja vai usar

**Files:**
- Modify: `chatbot-api/app/main.py` (depois da rota da Task 4)
- Test: `chatbot-api/tests/test_agente_config_escrita.py`

**Interfaces:**
- Consumes: tudo da Task 3, mais `agente_prompt.detectar_conflitos`.
- Produces:
  - `GET /v1/agente/rascunho` → `{"campos": {...}, "prompt": str, "conflitos": [str]}`
  - `PUT /v1/agente/rascunho` (body = `CamposAgente`) → mesmo formato
  - `POST /v1/agente/publicar` → `{"versao_id": str, "publicado_em": str}`
  - `GET /v1/agente/versoes` → `[{"id","estado","autor","criado_em","publicado_em"}]`
  - `POST /v1/agente/versoes/{versao_id}/restaurar` → mesmo formato do rascunho

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_config_escrita.py`:

```python
"""Rotas de escrita da config (spec §6). Quem consome é a Revy Loja."""

CAMPOS = {"nome_loja": "Motos do Léo", "cidade": "Piracicaba", "uf": "SP"}


def test_put_rascunho_devolve_o_prompt_gerado(client, loja_a):
    r = client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    assert r.status_code == 200
    assert "motos do léo" in r.json()["prompt"].lower()


def test_rascunho_salvo_nao_muda_o_publicado(client, loja_a):
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    publicado = client.get("/v1/agente/config", headers=loja_a["headers"]).json()["prompt"]
    assert "motos do léo" not in publicado.lower()


def test_publicar_leva_ao_ar(client, loja_a):
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    assert client.post("/v1/agente/publicar", headers=loja_a["headers"]).status_code == 200
    publicado = client.get("/v1/agente/config", headers=loja_a["headers"]).json()["prompt"]
    assert "motos do léo" in publicado.lower()


def test_conflito_avisa_mas_deixa_salvar(client, loja_a):
    """Avisa, não bloqueia (decisão do dono, spec §4.5)."""
    corpo = dict(CAMPOS, instrucoes="pode dizer o valor da parcela pro cliente")
    r = client.put("/v1/agente/rascunho", json=corpo, headers=loja_a["headers"])
    assert r.status_code == 200
    assert "parcela" in r.json()["conflitos"]


def test_instrucao_acima_do_teto_e_recusada(client, loja_a):
    corpo = dict(CAMPOS, instrucoes="a" * 1001)
    assert client.put("/v1/agente/rascunho", json=corpo, headers=loja_a["headers"]).status_code == 422


def test_restaurar_traz_a_versao_antiga_para_o_rascunho(client, loja_a):
    client.put("/v1/agente/rascunho", json=dict(CAMPOS, nome_loja="Loja Um"), headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])
    primeira = client.get("/v1/agente/versoes", headers=loja_a["headers"]).json()[0]["id"]

    client.put("/v1/agente/rascunho", json=dict(CAMPOS, nome_loja="Loja Dois"), headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])

    r = client.post(f"/v1/agente/versoes/{primeira}/restaurar", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "loja um" in r.json()["prompt"].lower()


def test_uma_loja_nao_restaura_versao_da_outra(client, loja_a, loja_b):
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])
    versao_a = client.get("/v1/agente/versoes", headers=loja_a["headers"]).json()[0]["id"]

    r = client.post(f"/v1/agente/versoes/{versao_a}/restaurar", headers=loja_b["headers"])
    assert r.status_code == 404
```

- [ ] **Step 2: Rode e confirme que falha**

`pytest tests/test_agente_config_escrita.py -q` → 404 em todas.

- [ ] **Step 3: Escreva as rotas**

Em `chatbot-api/app/main.py`, logo depois de `config_agente`:

```python
def _rascunho_para_saida(db: Session, loja_id: str) -> dict:
    versao = agente_config.obter_rascunho(db, loja_id)
    return {
        "campos": versao.campos,
        "prompt": versao.prompt_gerado,
        "conflitos": agente_prompt.detectar_conflitos(
            str(versao.campos.get("instrucoes") or "")
        ),
    }


@app.get("/v1/agente/rascunho")
def obter_rascunho_agente(
    instance: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    return _rascunho_para_saida(db, loja_id)


@app.put("/v1/agente/rascunho")
def salvar_rascunho_agente(
    campos: agente_prompt.CamposAgente,
    instance: Optional[str] = None,
    autor: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Salva sem publicar. Conflito com o núcleo vira aviso, nunca recusa."""
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    agente_config.salvar_rascunho(db, loja_id, campos, autor)
    return _rascunho_para_saida(db, loja_id)


@app.post("/v1/agente/publicar")
def publicar_agente(
    instance: Optional[str] = None,
    autor: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    versao = agente_config.publicar(db, loja_id, autor)
    return {
        "versao_id": versao.id,
        "publicado_em": versao.publicado_em.isoformat() if versao.publicado_em else None,
    }


@app.get("/v1/agente/versoes")
def listar_versoes_agente(
    instance: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    return [
        {
            "id": v.id,
            "estado": v.estado,
            "autor": v.autor,
            "criado_em": v.criado_em.isoformat() if v.criado_em else None,
            "publicado_em": v.publicado_em.isoformat() if v.publicado_em else None,
        }
        for v in agente_config.listar_versoes(db, loja_id)
    ]


@app.post("/v1/agente/versoes/{versao_id}/restaurar")
def restaurar_versao_agente(
    versao_id: str,
    instance: Optional[str] = None,
    autor: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Cria rascunho novo a partir da versão antiga. Não apaga histórico."""
    loja_id = resolver_loja_id(db, ctx, instance)
    _exigir_loja_operacional(db, loja_id)
    try:
        agente_config.restaurar(db, loja_id, versao_id, autor)
    except LookupError:
        raise HTTPException(status_code=404, detail="versão não encontrada nesta loja")
    return _rascunho_para_saida(db, loja_id)
```

- [ ] **Step 4: Rode e confirme que passa**

`pytest tests/test_agente_config_escrita.py -q` → verde.

- [ ] **Step 5: Suíte inteira**

`pytest -q` → verde.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_agente_config_escrita.py
git commit -m "feat(chatbot): rotas de rascunho, publicar, versoes e restaurar"
```

---

### Task 6: Liga/desliga e horário no gate que já existe

O ponto de aplicação **não** é um nó novo do n8n: é `pode-responder`, que o workflow já
chama antes de acionar a IA, já resolve a loja e já é onde mora o debounce.

**Files:**
- Modify: `chatbot-api/app/agente_config.py` (função `esta_em_horario`)
- Modify: `chatbot-api/app/main.py:921` (rota `pode_responder`)
- Test: `chatbot-api/tests/test_agente_liga_desliga.py`

**Interfaces:**
- Consumes: `agente_config.campos_publicados`.
- Produces: `agente_config.esta_em_horario(campos, agora) -> bool`; `pode_responder` passa a
  devolver `{"pode_responder": False, "motivo": "agente_desligado" | "fora_de_horario"}`.

- [ ] **Step 1: Escreva o teste que falha**

Crie `chatbot-api/tests/test_agente_liga_desliga.py`:

```python
"""Liga/desliga por loja e janela de horário (spec §4.6). Fuso: America/Sao_Paulo."""
from datetime import datetime, timezone

from app import agente_config
from app.agente_prompt import CamposAgente


def _publicar(db, loja_id, **over):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", **over)
    agente_config.salvar_rascunho(db, loja_id, campos, autor="t")
    agente_config.publicar(db, loja_id, autor="t")


def test_agente_desligado_nao_responde(client, db, loja_a):
    """`instance` é obrigatório no corpo: PodeResponderInput tem extra='forbid'."""
    _publicar(db, loja_a["loja_id"], agente_ativo=False)
    r = client.post(
        "/v1/conversas/5519999999999/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "m1"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    assert r.json()["pode_responder"] is False
    assert r.json()["motivo"] == "agente_desligado"


def test_agente_ligado_segue_o_fluxo_normal(client, db, loja_a):
    _publicar(db, loja_a["loja_id"], agente_ativo=True)
    r = client.post(
        "/v1/conversas/5519999999999/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "m2"},
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    assert r.json().get("motivo") != "agente_desligado"


def test_fora_do_horario_quando_a_loja_pediu_so_comercial(db):
    """14h de uma terça está dentro; 23h não. Fuso fixo America/Sao_Paulo."""
    campos = CamposAgente(
        nome_loja="X", cidade="Y", uf="SP",
        so_horario_comercial=True,
        horario={"ter": ["08:00", "18:00"]},
    )
    dentro = datetime(2026, 8, 25, 17, 0, tzinfo=timezone.utc)   # 14h em SP
    fora = datetime(2026, 8, 26, 2, 0, tzinfo=timezone.utc)      # 23h de terça em SP
    assert agente_config.esta_em_horario(campos, dentro) is True
    assert agente_config.esta_em_horario(campos, fora) is False


def test_sem_grade_de_horario_atende_sempre(db):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", so_horario_comercial=True)
    assert agente_config.esta_em_horario(campos, datetime.now(timezone.utc)) is True
```

- [ ] **Step 2: Rode e confirme que falha**

`pytest tests/test_agente_liga_desliga.py -q` → `AttributeError: module 'app.agente_config' has no attribute 'esta_em_horario'`.

- [ ] **Step 3: Escreva `esta_em_horario`**

No fim de `chatbot-api/app/agente_config.py`:

```python
from zoneinfo import ZoneInfo

# lojas não tem coluna de timezone (models_db.py:19). Fuso fixo até existir
# loja fora do horário de Brasília (spec §4.1).
FUSO_LOJA = ZoneInfo("America/Sao_Paulo")

_DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


def esta_em_horario(campos: CamposAgente, agora: datetime) -> bool:
    """Grade vazia = atende sempre. Dia ausente da grade = fechado naquele dia."""
    if not campos.so_horario_comercial or not campos.horario:
        return True
    local = agora.astimezone(FUSO_LOJA)
    faixa = campos.horario.get(_DIAS[local.weekday()])
    if not faixa or len(faixa) != 2:
        return False
    return faixa[0] <= local.strftime("%H:%M") < faixa[1]
```

- [ ] **Step 4: Ligue no `pode_responder`**

Em `chatbot-api/app/main.py`, dentro de `pode_responder`, logo **depois** de
`loja_id = resolver_loja_id(db, ctx, dados.instance)` e **antes** de
`servico.pode_responder_mensagem`:

```python
    # Liga/desliga por loja e janela de horário (spec §4.6). Fica aqui, e não
    # num nó do n8n, porque este é o gate que o workflow já chama antes da IA.
    campos_agente = agente_config.campos_publicados(db, loja_id)
    if not campos_agente.agente_ativo:
        return {"pode_responder": False, "motivo": "agente_desligado"}
    if not agente_config.esta_em_horario(campos_agente, datetime.now(timezone.utc)):
        return {"pode_responder": False, "motivo": "fora_de_horario"}
```

O formato do retorno **não é invenção**: é o mesmo que `servico.pode_responder_mensagem`
já devolve (`{"pode_responder": False, "motivo": "bot_inativo"}`), e o gate do n8n lê
`pode_responder !== true`. Nada no workflow precisa mudar por causa desta task.

`datetime` e `timezone` já estão importados em `main.py:11`. Não mexa no import.

- [ ] **Step 5: Rode e confirme que passa**

`pytest tests/test_agente_liga_desliga.py -q` → verde.

- [ ] **Step 6: Suíte inteira — atenção aqui**

`pytest -q`. Esta task muda uma rota do caminho quente; se algum teste antigo de
`pode-responder` ou de fluxo ponta-a-ponta quebrar, **não relaxe a asserção nova**: o
default é `agente_ativo=True` e loja sem config cai no padrão, então nenhum teste antigo
deveria mudar de resposta. Se mudou, o bug é no código novo.

- [ ] **Step 7: Commit**

```bash
git add chatbot-api/app/agente_config.py chatbot-api/app/main.py chatbot-api/tests/test_agente_liga_desliga.py
git commit -m "feat(chatbot): liga/desliga do agente e janela de horario no pode-responder"
```

---

### Task 7: `followup_ativo` respeitado pelo worker

Decisão do dono (25/08): na v1 entra o **interruptor**, não a configuração. Cadência, número
de toques e texto na voz do agente ficam fora (spec §4.4.2).

**Files:**
- Modify: `chatbot-api/app/followup_job.py` (dentro de `FollowupWorker.run_once`)
- Test: `chatbot-api/tests/test_followup_desligado_por_loja.py`

**Interfaces:**
- Consumes: `agente_config.campos_publicados`.
- Produces: nada novo — só o filtro.

- [ ] **Step 1: Leia o worker antes de escrever**

Abra `chatbot-api/app/followup_job.py` e leia `FollowupWorker.run_once` inteiro. Ele já
filtra por `loja_opera_modo2` e `Conversa.bot_ativo`. O filtro novo entra ao lado desses,
por loja, **antes** de montar os toques.

- [ ] **Step 2: Escreva o teste que falha**

Crie `chatbot-api/tests/test_followup_desligado_por_loja.py`. Os helpers abaixo são os
mesmos de `tests/test_followup_worker.py` — repetidos aqui de propósito, para não refatorar
o teste antigo dentro deste card:

```python
"""Interruptor do follow-up por loja (spec §4.4.2). Só Modo 2, como o worker já era."""
from datetime import datetime, timedelta, timezone

from app import agente_config
from app.agente_prompt import CamposAgente
from app.followup_job import FollowupWorker
from app.models_db import Conversa, LojaOperacionalProjecao, Mensagem


def _projetar_modo2(db, loja_id):
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-modo-{loja_id[:8]}",
    ))
    db.commit()


def _conversa_calada(db, loja_id, telefone):
    sufixo = f"{loja_id[:8]}-{telefone}"
    c = Conversa(id=f"c-{sufixo}", loja_id=loja_id, telefone=telefone, bot_ativo=True)
    db.add(c)
    db.add(Mensagem(
        id=f"m-{sufixo}", loja_id=loja_id, conversa_id=c.id,
        direcao="saida", texto="oi",
        criada_em=datetime.now(timezone.utc) - timedelta(minutes=31),
    ))
    db.commit()
    return c


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, *, instance, number, text):
        self.textos.append((number, text))
        return {"messages": [{"id": "wamid.F"}]}


def _config(db, loja_id, *, ligado: bool):
    campos = CamposAgente(nome_loja="X", cidade="Y", uf="SP", followup_ativo=ligado)
    agente_config.salvar_rascunho(db, loja_id, campos, autor="t")
    agente_config.publicar(db, loja_id, autor="t")


def test_loja_com_followup_desligado_nao_recebe_toque(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa_calada(db, loja_a["loja_id"], "5511900000010")
    _config(db, loja_a["loja_id"], ligado=False)
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 0
    assert fake.textos == []


def test_loja_sem_config_continua_recebendo(db, loja_a, monkeypatch):
    """Default é ligado: nenhuma loja perde follow-up por não ter configurado."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo2(db, loja_a["loja_id"])
    _conversa_calada(db, loja_a["loja_id"], "5511900000011")
    fake = _OutboundFake()

    assert FollowupWorker().run_once(db, outbound=fake)["toques"] == 1
    assert len(fake.textos) == 1
```

- [ ] **Step 3: Rode e confirme que falha**

`pytest tests/test_followup_desligado_por_loja.py -q` → o primeiro teste falha porque o
toque é enviado mesmo com o interruptor desligado.

- [ ] **Step 4: Escreva o filtro**

O laço é **por conversa**, não por loja. No topo de `run_once`, junto do import tardio que
já existe:

```python
    def run_once(self, db: Session, *, outbound) -> dict[str, int]:
        from app.rodizio import loja_opera_modo2
        from app import agente_config

        # Cache por loja: o laço é por conversa, e sem isto seria uma consulta
        # de config por conversa calada.
        followup_ligado: dict[str, bool] = {}
```

Import tardio pelo mesmo motivo do `auth`: `agente_config` importa `models_db` e o topo
daria ciclo.

Dentro do laço, **logo depois** da linha que já existe:

```python
            if not loja_opera_modo2(db, conversa.loja_id):
                continue
```

acrescente:

```python
            if conversa.loja_id not in followup_ligado:
                followup_ligado[conversa.loja_id] = agente_config.campos_publicados(
                    db, conversa.loja_id
                ).followup_ativo
            if not followup_ligado[conversa.loja_id]:
                continue
```

Nada mais muda: a cadência, o teto de dois toques e os textos de `_TEXTOS` ficam como
estão. Esta task é o interruptor, não a configuração (spec §4.4.2).

- [ ] **Step 5: Rode e confirme que passa**

`pytest tests/test_followup_desligado_por_loja.py tests/test_followup_worker.py tests/test_followup_silencio.py -q` → verde.

- [ ] **Step 6: Suíte inteira**

`pytest -q` → verde.

- [ ] **Step 7: Commit**

```bash
git add chatbot-api/app/followup_job.py chatbot-api/tests/test_followup_desligado_por_loja.py
git commit -m "feat(chatbot): loja pode desligar o follow-up (spec 4.4.2)"
```

---

## Fechamento do card

- [ ] `cd chatbot-api && pytest -q` verde, com o número de testes **maior** que o da abertura.
- [ ] `cd chatbot-api && alembic heads` → uma cabeça só, `0027_agente_config`.
- [ ] `git diff --check` limpo e `git status --short` sem arquivo alheio.
- [ ] Regerar o mapa (este card cria rota, modelo ORM e migration):
      `cd .claude/skills/revy-research && python gerar_mapa.py` (Windows) ou `python3` (macOS),
      e commitar junto.
- [ ] Nada foi deployado. As rotas existem e ninguém as chama ainda — é o esperado.
- [ ] Algo te surpreendeu? Escreva um learning, procurando duplicata **pelo gatilho** antes.

## O que este card NÃO faz

- Não muda uma vírgula do prompt que está no ar. O bot continua falando exatamente igual,
  porque o `systemMessage` do n8n não foi tocado. Isso é o card 2.
- Não tem tela. Ninguém consegue editar nada pela Revy Loja ainda — card 3. **Se você é o
  agente do card 3 ou 4, leia a §6.0 do spec antes de escrever a primeira linha de HTML**:
  não existe componente de abas no `app.css`, o padrão é rota própria com link no
  `.heading-actions`, o `?v=` do `app.css` tem que subir (são dois arquivos, Loja em `v16` e
  Control em `v12`), e duas das 13 recusas do dono encostam nesta tela.
- Não tem preview nem modo seco das tools — card 4.
- Não liga flag nenhuma e não deploya.
