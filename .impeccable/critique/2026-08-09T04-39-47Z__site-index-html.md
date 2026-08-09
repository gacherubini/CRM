---
target: site/index.html
total_score: 24
max_score: 32
na_heuristics: 7,10
p0_count: 2
p1_count: 3
timestamp: 2026-08-09T04-39-47Z
slug: site-index-html
---
Method: dual-agent (A: accd3971908d032ea · B: ae459cf35ef74458f)
Target: site/index.html (live: https://app2037.fly.dev/site/) · Surface: Persuade (marketing landing) · JS-only bundle, 2.59 MB

# Design Health Score (Nielsen, Persuade-normalized)

| # | Heuristic | Score | Key issue |
|---|-----------|:---:|-----------|
| 1 | Visibility of system status | 2 | Animated panels reveal as blank white cards until centered; heavy motion, no loading cue |
| 2 | Match system ↔ real world | 4 | Flawless audience language; real bank names |
| 3 | User control & freedom | 3 | Good dual path, but animation can't be paused and pegs the main thread |
| 4 | Consistency & standards | 4 | Tight internal system + faithful brand kit |
| 5 | Error prevention | 2 | No visible form validation/format guidance; logo strip pre-loads a relationship error |
| 6 | Recognition over recall | 4 | Everything on-screen; nav mirrors sections; demo shows |
| 7 | Flexibility & efficiency | n/a | One-shot landing — no expert accelerators to judge |
| 8 | Aesthetic & minimalist | 3 | Superb/restrained visually, but 2.59 MB + two auto-animating panels fight true minimalism |
| 9 | Error recovery | 2 | noscript is a dead end; form error states unverified |
| 10 | Help & documentation | n/a | The page *is* the documentation |
| **Total** | | **24/32** | **Good, with real gaps** |

Usability ≠ trust: the heuristic frame does not capture this page's worst defect (the fabricated logo strip), which sits outside usability.

# Audit Health Score (technical)

| # | Dimension | Score | Evidence |
|---|-----------|:---:|----------|
| 1 | Accessibility | 2/4 | label for/id on inputs, single h1, alt on imgs — but no lang, no `<main>`, no `<form>`, no reduced-motion, custom `<sc-raw-select>` |
| 2 | Performance | 1/4 | 2.59 MB JS-only; in-browser JSX transpile of 10 modules re-imported 3–4×; main-thread saturation; no SSR |
| 3 | Responsive | 2/4 | viewport meta + 20 clamp()/grid auto-fit/flex-wrap, but zero @media; dense mockups unverified on mobile |
| 4 | Theming | 3/4 | brand-faithful palette, green #1f4d3a exact, no banned colors — but 195 hardcoded hex, 0 tokens |
| 5 | Implementation integrity | 3/4 | unmistakably product-specific; no fabricated numbers — but runtime-transpiled JSX bundle with structural gaps |
| **Total** | | **11/20** | **Acceptable** |

# Design specificity / integrity verdict (start here)
Both assessments independently reached the same verdict: the page is strongly authored-for-Revy — real WhatsApp handoff, the store's own banks (Santander/Bradesco/PAN/Fontecred), Revy Loja mockups, the dark "O que a Revy não faz" section, and a "Resultado da campanha" chart that shows growth shape with NO fabricated numbers. The single place it degrades into a generic template gesture — the customer-logo wall — is exactly where it breaks its own ethics. Detector ran clean (exit 0) but blind: it inspected only the loader shell, not the JS-generated page.

# What's working
1. Mechanism-as-proof — the WhatsApp handoff + Revy Loja dossier + named banks with the loja's own credentials render the exact moat a neighbor product "wouldn't copy honestly."
2. Honesty enacted, not just claimed — the black "O que a Revy não faz" section and the numbers-free growth chart honor PRODUCT.md principle #1 and disarm a numbers-wary buyer.
3. Brand discipline — Newsreader only where the brand speaks, Hanken UI, mono numerals, black/white + green micro-accent; zero fintech-glow / "IA gradient" clichés. Looks like Revy, not a template.

# Priority issues (deduped across both assessments)

[P0] Fabricated / unauthorized customer-logo strip — "Vitor Motos · RR Motos · Motos Vale · Sena Motos". Both A and B flag it. Violates principle #1 (honestidade vence conversão) and the explicit "NUNCA fabricar logotipo/nome de cliente, número de lojas" — there is ONE pilot store and its name is NOT authorized. "Motos Vale" is also the hero demo store, so the same name is product-mock AND "customer." Fix: remove the strip; replace with a capability row that names no customers, or a single honest "loja piloto" line; name a store only after written authorization. → clarify / audit

[P0] JS-only render, no SSR → invisible to search & social. noscript = "requires JavaScript"; 0 meta description; content injected at runtime. A marketing page whose job is acquisition returns an empty shell to crawlers and WhatsApp/social scrapers — self-refuting for a product whose pitch is attribution/CPL/ROAS. Fix: pre-render/SSR the copy, add meta description + OG/Twitter tags + social image, give noscript a real fallback. → optimize + harden

[P1] 2.59 MB + in-browser JSX transpile (3–4× re-import) → main-thread saturation. LCP/TTI suffer; mid-tier mobile stutters; scroll-reveal panels render blank until centered. Fix: pre-transpile at build time, split/lazy-load modules, kill the re-import, give panels static fallback content at rest. → optimize

[P1] No prefers-reduced-motion on a continuous, un-pausable loop. WCAG 2.3.3 (AAA) + 2.2.2 (A). Fix: wrap non-essential motion in the media query; static equivalents for demo panels. → animate

[P1] A11y container semantics missing (B caught; A did not). No `lang="pt-BR"` (WCAG 3.1.1); no `<main>` (1.3.1/2.4.1); contact is NOT a `<form>` (buttons are type=button, no submit); "Motos em estoque" is a custom `<sc-raw-select>` with uncertain keyboard/AT support (4.1.2/2.1.1). Fix: add lang, wrap in `<main>` + real `<form>`/submit, replace the custom select with a native one. → harden

[P2] Scroll-reveal fragility — the two biggest proof panels ("Cinco telas", "Resultado da campanha") show as blank white cards when not centered; reads as broken software right where you demo polished software. Fix: static content at rest, motion as enhancement. → harden + quieter

[P2] Jargon + tiny mock text for the #1 (non-technical) user. CPL/CPA/ROAS/ROI unglossed; mockup labels very small. Fix: gloss acronyms in plain PT-BR; enlarge/caption proof-panel labels. → clarify + typeset

[P3] 195 hardcoded hex, 0 design tokens. On-brand but can't sync with shared/brand/revy-tokens.css ("sincronizadas, não editadas à mão"). Fix: emit colors as CSS custom properties mapped to canonical token names. → colorize

[P3] Hero motorcycle photo as CSS background-image. Invisible to AT if meaningful (WCAG 1.1.1). Decide: decorative → leave; informative → real `<img alt>`. → harden

# Persona red flags
- Dono de revenda (non-technical, busy shop desktop, wants to trust the number): the logo strip is the kill shot — if he recognizes a named store as a local competitor, or sees his own pilot store named without authorization, trust collapses. CPL/CPA/ROAS are noise to him. Cruel irony: the most "number-like" element on a page promising trustworthy numbers is the fabricated one.
- Riley (stress-tester): Googles "RR Motos Revy" / "Sena Motos Revy", finds nothing, concludes the wall is fabricated, retroactively distrusts the honesty section. Disables JS → dead end. DevTools → 2.59 MB, modules re-imported 4×.
- Casey (mobile): worst-case device for this bundle — 2.59 MB + in-browser transpile on mid-range Android/4G → slow paint, stutter, blank reveal cards; true mobile responsiveness unverified.
- Jordan (first-timer): warm hero → unverifiable logo bar → blank panel mid-scroll ("loading or broken?") → CPL/CPA/ROAS cold.

# Minor observations
- CPF 123.456.789-00 is an obviously invalid sequential placeholder — good, reads as demo, no real PII.
- In-mock parcelas (48× R$ 489; PAN 48× R$ 1.189) are fine as illustrative demo content; keep them visibly inside the mock.
- `<title>` present; no meta description or OG image → social shares preview blank.
- The number-less chart is the correct honest template for ALL proof on this page.
- "Limites" as a nav item pointing at the honesty section is an on-brand integrity signal — keep it.
- Green appears only as micro-accent; no banned colors (neon orange, IA gradient, fintech blue, colored glow).

# Questions to consider
1. If honestidade vence conversão is principle #1, how does a fabricated four-store logo wall survive the page's own "O que a Revy não faz"?
2. For a product whose whole pitch is attribution/ROI, would you accept the CPL of an acquisition page that's invisible to search engines and social scrapers?
3. The chart shows a shape without numbers because there honestly isn't volume yet — so what does the logo strip claim to have that the chart openly admits it doesn't?
