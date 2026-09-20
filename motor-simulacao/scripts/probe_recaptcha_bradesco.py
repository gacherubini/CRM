"""O grecaptcha.execute() da chave do Bradesco devolve token no nosso navegador?

Carrega a pagina publica de login e chama o execute na mao. Nao digita CPF, nao
digita senha, nao clica em Entrar. Nenhum login e consumido.

Se o execute estourar, o ng-recaptcha cai no catch e o Angular mostra
"Erro ao tentar verificar o reCAPTCHA" — que e o banner de producao.

Roda igual local e dentro do worker; imprime em ASCII para o console do Fly.
"""
from playwright.sync_api import sync_playwright

URL = "https://turbo.bradesco/originacaolojista/login"
SITEKEY = "6LdjHLYrAAAAAFitXimO6O8Onh3hogINT5Pb0b8c"

ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=IsolateOrigins,site-per-process",
    "--window-size=1366,768",
    "--lang=pt-BR",
]
IGNORE = ["--enable-automation", "--enable-blink-features=IdleDetection"]

JS_EXECUTE = (
    """async () => {
  const t0 = Date.now();
  if (!window.grecaptcha) return {erro: 'grecaptcha ausente'};
  try {
    await new Promise((res, rej) => {
      const to = setTimeout(() => rej(new Error('ready nao disparou em 20s')), 20000);
      window.grecaptcha.ready(() => { clearTimeout(to); res(); });
    });
  } catch (e) { return {erro: 'ready: ' + e.message, ms: Date.now() - t0}; }
  try {
    const tok = await window.grecaptcha.execute('"""
    + SITEKEY
    + """', {action: 'login'});
    return {ok: true, ms: Date.now() - t0, tam: (tok || '').length,
            inicio: (tok || '').slice(0, 24)};
  } catch (e) {
    return {erro: 'execute: ' + (e && (e.message || e)), ms: Date.now() - t0};
  }
}"""
)

with sync_playwright() as p:
    br = p.chromium.launch(
        headless=False,
        args=list(ARGS),
        ignore_default_args=list(IGNORE),
        chromium_sandbox=False,
    )
    ctx = br.new_context(
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 768},
    )
    pg = ctx.new_page()
    falhas = []
    pg.on(
        "requestfailed",
        lambda r: falhas.append(r.url[:110] + " :: " + str(r.failure))
        if ("recaptcha" in r.url or "gstatic" in r.url)
        else None,
    )
    try:
        pg.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        print("GOTO FALHOU:", type(exc).__name__, str(exc)[:140])
        raise SystemExit(1)
    pg.wait_for_timeout(6_000)
    print("url      :", pg.url)
    print("titulo   :", pg.title())
    print("EXECUTE  :", pg.evaluate(JS_EXECUTE))
    print("falhas   :", falhas[:5] or "nenhuma")
    corpo = " ".join((pg.inner_text("body") or "").split())
    print("corpo    :", corpo[:220])
    ctx.close()
    br.close()
