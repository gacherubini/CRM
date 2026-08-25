#!/usr/bin/env node
/*
 * EXECUTA as ferramentas do preview com um `helpers.httpRequest` de mentira e
 * afirma que nenhuma chamada que age acontece.
 *
 * O `validate_preview_workflow.py` prova que a chamada que causa efeito vem
 * *depois* do freio no texto do arquivo. Isso não é a mesma coisa que provar que
 * o freio sempre dispara: um `return` dentro de um `if` passaria na checagem
 * estática e deixaria o efeito alcançável. A spec §10 pede o teste explícito, e
 * chama isto de risco nº 1 — com razão: `simular1` cria lead no portal, avisa a
 * equipe no WhatsApp e pausa o bot. Um preview furado toca o celular do vendedor
 * num sábado porque o lojista digitou um CPF numa tela.
 *
 * Os casos são o **caminho feliz** de cada ferramenta: aquele em que a versão de
 * produção faz a chamada. Se o freio não estiver ali, o teste vê a chamada.
 *
 * `node n8n/test_modo_seco.js`
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const PREVIEW = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'workflow-preview.json'), 'utf8'),
);
const MODO1 = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'workflow-ai-nao-salvos.json'), 'utf8'),
);

const codigo = (wf, nome) => {
  const n = wf.nodes.find((x) => x.name === nome);
  assert(n, `${nome} não existe`);
  return n.parameters.jsCode;
};

const ORIGEM = {
  telefone: '0244798567928', // sintético: o preview nunca usa numero real
  instance: 'inst-a',
  destino: '0244798567928',
  providerMessageId: 'preview:0244798567928:1',
  pushName: 'Ana',
  ehGrupo: false,
  grupoJid: null,
};

const MOTO = {
  id: '77',
  placa: 'ABC1D23',
  valor: 12000,
  categoria: 'moto',
  interesse: 'honda biz 2020',
};

// Nasceu ha 30 anos: maior de idade em qualquer data de execucao.
const NASCIMENTO = `01/01/${new Date().getUTCFullYear() - 30}`;

async function rodar(js, { query, respostas = {}, estado = {} }) {
  const chamadas = [];
  const helpers = {
    async httpRequest(opcoes) {
      chamadas.push(opcoes.url);
      for (const [trecho, resposta] of Object.entries(respostas)) {
        if (opcoes.url.includes(trecho)) return resposta;
      }
      return {};
    },
  };
  const $ = (nome) => {
    assert.strictEqual(nome, 'Extrair1', `nó inesperado: ${nome}`);
    return { first: () => ({ json: ORIGEM }) };
  };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const fn = new AsyncFunction(
    'query',
    'helpers',
    '$',
    '$getWorkflowStaticData',
    js,
  );
  const saida = await fn(query, helpers, $, () => estado);
  return { saida: JSON.parse(saida), chamadas };
}

// O que NUNCA pode ser chamado num preview, e o estrago de cada um.
const PROIBIDO = [
  ['/v1/simulacoes/solicitar', 'dispara simulacao no Motor'],
  ['/v1/operacao/solicitacoes-simulacao-humana', 'cria lead e avisa a equipe'],
  ['/v1/operacao/moto-escolhida', 'cria Conversa para o telefone sintetico'],
  ['/v1/operacao/veiculos', 'cadastra veiculo no Estoque'],
  ['/v1/conversas/', 'pausa o bot de uma conversa'],
  ['/v1/operacao/numeros-autorizados', 'busca o vendedor de plantao'],
  ['/message/sendText/', 'manda WhatsApp para o vendedor'],
  ['/message/sendMedia/', 'manda midia'],
];

function semEfeito(nome, chamadas) {
  for (const [url, estrago] of PROIBIDO) {
    const achou = chamadas.find((c) => c.includes(url));
    assert(!achou, `${nome} chamou ${url} no modo seco — isso ${estrago}`);
  }
}

const CASOS = [
  {
    nome: 'simular1',
    // Caminho feliz completo: moto escolhida, CPF valido, maior de idade, CNH
    // respondida. Em producao isto cria o lead.
    query: { cpf: '12345678901', nascimento: NASCIMENTO, tem_cnh: 'sim' },
    estado: { [`moto-escolhida:${ORIGEM.telefone}`]: MOTO },
    confere: ({ saida }) => {
      assert.strictEqual(saida.ok, true);
      assert.strictEqual(saida.simulacao_humana_solicitada, true);
      assert.match(saida.mensagem, /encaminhar pro setor de simulação/);
    },
  },
  {
    nome: 'TEMP continuar sem estoque1',
    query: {
      interesse: 'honda biz 2020',
      cpf: '12345678901',
      nascimento: NASCIMENTO,
      tem_cnh: 'nao',
      confirmar_simulacao: true,
    },
    confere: ({ saida }) => {
      assert.strictEqual(saida.ok, true);
      assert.strictEqual(saida.simulacao_humana_solicitada, true);
      assert.strictEqual(saida.pode_oferecer_fotos, false);
    },
  },
  {
    nome: 'solicitar_handoff1',
    query: { motivo: 'cliente pediu atendimento humano' },
    confere: ({ saida }) => {
      assert.strictEqual(saida.mensagem, 'certo. vou encaminhar seu atendimento.');
    },
  },
  {
    nome: 'enviar_foto_veiculo1',
    query: { veiculo_id: '77' },
    confere: ({ saida }) => {
      assert.strictEqual(saida.ok, true);
      assert(saida.fotos_enviadas > 0, 'o agente precisa responder como se tivesse mandado');
    },
  },
  {
    nome: 'cadastrar_veiculo1',
    query: { tipo: 'moto', marca: 'Honda', modelo: 'Biz', ano_modelo: 2020, preco: 12000 },
    confere: ({ saida }) => {
      assert.strictEqual(saida.ok, true);
    },
  },
];

(async () => {
  for (const caso of CASOS) {
    const r = await rodar(codigo(PREVIEW, caso.nome), {
      query: caso.query,
      estado: caso.estado || {},
    });
    semEfeito(caso.nome, r.chamadas);
    try {
      caso.confere(r);
    } catch (e) {
      console.error(`${caso.nome} devolveu:`, JSON.stringify(r.saida));
      throw e;
    }
  }

  // `consultar_estoque1` e o oposto: a BUSCA tem que acontecer — e ela que faz o
  // teste valer — e so a gravacao no CRM some.
  {
    const r = await rodar(codigo(PREVIEW, 'consultar_estoque1'), {
      query: { termo: 'biz 2020' },
      respostas: {
        '/v1/estoque/buscar': {
          veiculos: [{ id: '77', placa: 'ABC1D23', preco: 12000, tipo: 'moto', marca: 'Honda', modelo: 'Biz' }],
        },
      },
    });
    semEfeito('consultar_estoque1', r.chamadas);
    assert(
      r.chamadas.some((c) => c.includes('/v1/estoque/buscar')),
      'consultar_estoque1 parou de consultar o estoque: o preview nao prova mais nada',
    );
  }

  // O teste nao pode ser vazio. A MESMA ferramenta, na versao de producao, tem
  // que fazer a chamada — senao ele passaria mesmo com o freio ausente.
  {
    const r = await rodar(codigo(MODO1, 'simular1'), {
      query: { cpf: '12345678901', nascimento: NASCIMENTO, tem_cnh: 'sim' },
      estado: { [`moto-escolhida:${ORIGEM.telefone}`]: MOTO },
      respostas: {
        '/v1/operacao/solicitacoes-simulacao-humana': {
          ok: true,
          simulacao_humana_solicitada: true,
        },
      },
    });
    assert(
      r.chamadas.some((c) => c.includes('/v1/operacao/solicitacoes-simulacao-humana')),
      'o simular1 do Modo 1 deixou de criar lead — ou este teste virou vazio',
    );
  }

  console.log(
    `modo seco OK: ${CASOS.length} ferramentas executadas no caminho feliz e nenhuma ` +
      'agiu; a busca no estoque continua acontecendo; o Modo 1 continua criando lead',
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
