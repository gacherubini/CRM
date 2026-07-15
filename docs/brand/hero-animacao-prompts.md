# Hero Revy — animação “Bolha → Parcela → Chave”

**Conceito:** conversa no WhatsApp → condições de financiamento → fechamento sutil (chave / aperto de mão).  
**Pipeline:** Nano Banana (stills) → Seedance (motion) → `docs/brand/assets/hero.mp4` + `hero-poster.jpg`  
**Duração alvo:** 8–10s, loop, 16:9, 1080p, **muted** no site.  
**Estilo:** monocromático / editorial, sem laranja neon, sem robô de IA.

---

## Storyboard (3 beats)

| # | Tempo | Nome | O que aparece | Emoção |
|---|---|---|---|---|
| 1 | 0–3s | **Bolha** | Chat WhatsApp da loja, bolha “Confirma pra eu buscar as condições?” | Clareza, confiança |
| 2 | 3–6.5s | **Parcela** | Números elegantes: **R$ 489 · 48x** (e talvez 2ª opção sutil) | Resultado real |
| 3 | 6.5–10s | **Chave** | Mão recebendo chave de moto **ou** aperto de mão sutil (não corporativo de stock) | Fechou, humano |

**Regra de ouro:** mesma luz, mesma câmera, mesma paleta nos 3 frames → Seedance não “pula” de estilo.

---

## Nano Banana — prompts

### Frame A — Bolha (first frame / poster)

```
Clean editorial product still for a Brazilian software brand called Revy.
Scene: close-up of a modern smartphone held at a slight angle on a white desk,
screen showing a realistic WhatsApp chat of a motorcycle dealership assistant.
Visible message bubble in Portuguese: "Confirma pra eu buscar as condições?"
Soft natural daylight from the left, black and white and soft gray only,
no orange, no neon, no purple gradients, no robots, no 3D AI clichés.
Minimal composition, generous negative space on the left for website headline.
Photorealistic, 16:9, high detail UI, calm premium mood.
```

### Frame B — Parcela (middle keyframe)

```
Same camera angle, same desk, same lighting, same smartphone as previous frame.
On the phone screen the chat has progressed: clean UI cards show financing results
in large typography "R$ 489" and "48x", second smaller option "R$ 512 · 48x".
Black white gray palette only, no bank logos, no neon, photorealistic 16:9,
editorial product photography, calm and precise, seamless continuity with previous still.
```

### Frame C — Chave / aperto (last frame, ideal pro loop)

**Opção chave (recomendada — mais “revenda”):**
```
Same lighting and color palette as previous frames, seamless continuity.
Gentle close-up of a hand receiving a motorcycle key over a clean counter,
soft bokeh of a motorcycle showroom in the background, black white gray only,
no logos, no neon, photorealistic, warm human moment but minimal and premium,
16:9, calm, no exaggerated celebration, no confetti.
```

**Opção aperto de mão (alternativa):**
```
Same lighting and monochrome palette as previous frames.
Subtle handshake between salesperson and customer beside a motorcycle,
half bodies only, faces optional soft out of focus, clean Brazilian dealership,
no suits from corporate stock, casual smart clothes, photorealistic 16:9,
quiet closed-deal feeling, no confetti, no "approved" text.
```

### Dicas Nano Banana
- Gere A → use A como **referência de estilo** para B e C (se a ferramenta permitir).  
- Se o texto na tela sair quebrado: peça “UI with soft blur on small text, only large numbers sharp” ou faça o número grande no Seedance como motion, não OCR perfeito.  
- Poster do site = **Frame A**.

---

## Seedance — prompts de motion

### Versão 1 — um take contínuo (melhor se tiver first+last frame)

**First frame:** A · **Last frame:** C  

```
Smooth continuous product film, 8 seconds, seamless loopable ending.
Start on smartphone WhatsApp bubble, gentle slow push-in.
Mid sequence: financing numbers R$ 489 and 48x fade or slide in softly on screen.
End: transition dissolve to motorcycle key handoff (or subtle handshake), same light.
Camera motion: slow, stable, cinematic, no whip pans, no glitch, no morphing faces.
Mood: calm, trustworthy Brazilian dealership software. Monochrome, no orange neon.
No distorted text, no extra logos, no robot, muted audio not required.
```

### Versão 2 — só image-to-video a partir do Frame A

```
Animate this still: subtle parallax on phone, soft ambient light shift,
WhatsApp bubble already visible, then elegant appearance of large financing numbers
"R$ 489" "48x" on screen, end with gentle dissolve hint toward a key in hand.
Slow push-in, 8s, loopable, photoreal, monochrome, calm premium product video.
```

### Versão 3 — três clips curtos (mais controle)

| Clip | Input | Motion prompt (curto) |
|---|---|---|
| 1 | Frame A | `Slow push-in on phone, slight screen reflection, 3s, loop start` |
| 2 | Frame B | `Numbers settle into place, micro hold, 3s` |
| 3 | Frame C | `Tiny hand motion receiving key, soft breathe, 3s` |

Depois junta no CapCut/DaVinci com crossfade 8–12 frames.

---

## Texto na tela (se o modelo estragar letra)

Não dependa do modelo para PT perfeito. Opções:

1. Números grandes só (`489` / `48x`) e o resto fora de foco  
2. Overlay no site (HTML) em cima do vídeo: a animação fica abstrata  
3. After Effects / CapCut: text layer “R$ 489 · 48x” no beat 2  

Para a Revy, **overlay no HTML** no beat 2 é o mais seguro e on-brand.

---

## Specs de entrega

| Arquivo | Spec |
|---|---|
| `assets/hero-poster.jpg` | Frame A, 1920×1080 |
| `assets/hero.mp4` | H.264, 1920×1080, 8–10s, **sem áudio** ou áudio removido |
| Opcional `hero-mobile.mp4` | 1080×1920 se quiser crop vertical |

---

## Checklist de marca

- [ ] Sem laranja / roxo “IA”  
- [ ] Sem “aprovado” / confete  
- [ ] Bolha com tom Revy (confirma, não pressiona)  
- [ ] Parcela parece real, não mágica  
- [ ] Fechamento humano e quieto  
- [ ] Loop não “pula” de cor no corte final  

---

## Narrativa em uma frase (pra você lembrar)

> O cliente confirma no WhatsApp, a parcela aparece com clareza, e a loja fecha o trato — sem teatro.
