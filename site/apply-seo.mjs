#!/usr/bin/env node
// Injeta SEO + preview social + fallback sem-JS no HTML exportado do design tool.
//
// Por que existe: o site e um bundle que so renderiza via JavaScript. Sem isto,
// Google/scrapers (WhatsApp, Instagram, Facebook) recebem uma pagina vazia. Este
// script e IDEMPOTENTE: rode-o sobre cada novo export ANTES de commitar/deployar.
//
//   node site/apply-seo.mjs [caminho]   (padrao: site/index.html)
//
// So mexe no <head> e no <noscript> do head; nao toca no bundle.

import { readFileSync, writeFileSync } from 'node:fs';

const file = process.argv[2] || 'site/index.html';

const SITE_URL = 'https://app2037.fly.dev/site/';
const OG_IMAGE = 'https://app2037.fly.dev/site/assets/og-card.jpg';
const OG_W = 1200, OG_H = 630;
const TITLE = 'Revy — A revenda no ritmo certo';
const DESC =
  'A Revy atende o cliente no WhatsApp, simula financiamento nos bancos da propria ' +
  'loja e entrega o vendedor na hora certa. O sistema operacional da revenda de motos.';

const seoBlock = `<!-- revy-seo:start -->
  <meta name="description" content="${DESC}" />
  <link rel="canonical" href="${SITE_URL}" />
  <meta name="theme-color" content="#faf9f5" />
  <meta name="robots" content="index,follow" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Revy" />
  <meta property="og:locale" content="pt_BR" />
  <meta property="og:title" content="${TITLE}" />
  <meta property="og:description" content="${DESC}" />
  <meta property="og:url" content="${SITE_URL}" />
  <meta property="og:image" content="${OG_IMAGE}" />
  <meta property="og:image:width" content="${OG_W}" />
  <meta property="og:image:height" content="${OG_H}" />
  <meta property="og:image:alt" content="Revy — sistema operacional da revenda de motos" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="${TITLE}" />
  <meta name="twitter:description" content="${DESC}" />
  <meta name="twitter:image" content="${OG_IMAGE}" />
  <!-- revy-seo:end -->`;

// Conteudo real pra crawlers sem-JS e usuarios sem JavaScript (substitui o
// "This page requires JavaScript to display."). Copy tirado do proprio site.
const noscript = `<noscript>
  <style>#__bundler_loading,#__bundler_thumbnail{display:none!important}</style>
  <div style="max-width:760px;margin:0 auto;padding:48px 24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1b1b1b;background:#faf9f5;line-height:1.55">
    <p style="font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:#6b625f;margin:0 0 12px">Sistema operacional da revenda</p>
    <h1 style="font-size:32px;line-height:1.15;margin:0 0 12px">Revy — a revenda no ritmo certo</h1>
    <p style="font-size:18px;color:#4a4442;margin:0 0 28px">A Revy atende o cliente no WhatsApp, simula financiamento nos bancos da propria loja e entrega o vendedor na hora certa.</p>
    <h2 style="font-size:20px;margin:28px 0 8px">Como funciona</h2>
    <ol style="padding-left:20px;margin:0 0 24px">
      <li>Atende no WhatsApp — white-label, com o nome da sua loja.</li>
      <li>Simula nos seus bancos — Santander, Bradesco, Banco PAN e Fontecred, com as credenciais da propria loja.</li>
      <li>Entrega o vendedor — o bot cede ao humano na hora certa, com a ficha do cliente pronta.</li>
      <li>Mostra de onde veio — a venda confirmada carrega a campanha que a trouxe (CPL, CPA, ROAS).</li>
    </ol>
    <h2 style="font-size:20px;margin:28px 0 8px">O que a Revy nao faz</h2>
    <ul style="padding-left:20px;margin:0 0 24px">
      <li>Nao promete aprovacao de credito — em nenhuma tela.</li>
      <li>Nao e banco nem marketplace de credito. Os bancos sao os da sua loja.</li>
      <li>Nao cria nem pausa anuncio na Meta ou no Google.</li>
      <li>Nao e CRM generico. E a operacao da revenda de moto.</li>
    </ul>
    <p style="font-size:16px;color:#4a4442">Ative o JavaScript para ver a demonstracao completa.</p>
  </div>
</noscript>`;

let html = readFileSync(file, 'utf8');
const before = html;
const notes = [];

// 1) lang no <html> — SO no primeiro <html> do documento (o real, no topo).
// O bundle contem tokens "<html" embutidos em templates internos; nunca toca-los.
let langAdded = false;
html = html.replace(/<html\b([^>]*)>/i, (mtch, attrs) => {
  if (/\blang=/i.test(attrs)) return mtch;
  langAdded = true;
  return `<html lang="pt-BR"${attrs}>`;
});
notes.push(langAdded ? 'lang="pt-BR" adicionado ao <html>' : 'lang ja presente — mantido');

// Opera so dentro do <head>
const headRe = /(<head[^>]*>)([\s\S]*?)(<\/head>)/i;
const m = html.match(headRe);
if (!m) {
  console.error(`ERRO: <head> nao encontrado em ${file}`);
  process.exit(1);
}
let [, open, inner, close] = m;

// 2) remove bloco SEO anterior (re-run limpo)
inner = inner.replace(/\s*<!-- revy-seo:start -->[\s\S]*?<!-- revy-seo:end -->/g, '');

// 3) substitui o primeiro <noscript> do head pelo fallback com conteudo real;
//    se nao houver, injeta um.
if (/<noscript>[\s\S]*?<\/noscript>/i.test(inner)) {
  inner = inner.replace(/<noscript>[\s\S]*?<\/noscript>/i, () => noscript);
  notes.push('<noscript> substituido por fallback com conteudo real');
} else {
  inner += `\n  ${noscript}\n`;
  notes.push('<noscript> de fallback injetado');
}

// 4) viewport (so se ausente)
let viewport = '';
if (!/name=["']viewport["']/i.test(inner)) {
  viewport = '\n  <meta name="viewport" content="width=device-width, initial-scale=1" />';
  notes.push('meta viewport adicionado');
}

// 5) injeta bloco SEO antes de </head>
inner = `${inner.replace(/\s*$/, '')}${viewport}\n  ${seoBlock}\n`;

html = html.replace(headRe, `${open}${inner}${close}`);

if (html === before) {
  console.log(`Nenhuma mudanca necessaria em ${file} (ja estava aplicado).`);
} else {
  writeFileSync(file, html);
  console.log(`SEO aplicado em ${file}:`);
  for (const n of notes) console.log(`  - ${n}`);
}
