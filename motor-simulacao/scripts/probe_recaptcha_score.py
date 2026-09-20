"""Mede a nota do reCAPTCHA v3 DENTRO do worker do Fly, sem tocar em banco.

Roda com o mesmo Chromium, as mesmas flags e o mesmo contexto vanilla que o
driver do Bradesco usa. Imprime a nota que a demo do Google devolve.

Uso (Windows, do repo):
  Get-Content -Raw probe_worker.py | fly ssh console -a motor2037 `
    --machine 784ede55b11428 -C 'python3 -'
"""
from playwright.sync_api import sync_playwright

URL = "https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php"

# Copiados de app/motor/playwright_base.py para medir o que o driver realmente usa.
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

JS_WEBGL = """() => {
  try {
    const c = document.createElement('canvas').getContext('webgl');
    const d = c.getExtension('WEBGL_debug_renderer_info');
    return c.getParameter(d.UNMASKED_RENDERER_WEBGL);
  } catch (e) { return 'erro'; }
}"""

with sync_playwright() as p:
    br = p.chromium.launch(
        headless=False,  # igual ao worker: headed sob Xvfb
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
    capturado = []
    pg.on(
        "response",
        lambda r: capturado.append(r.text()[:300])
        if "recaptcha-v3-verify" in r.url
        else None,
    )
    pg.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    for _ in range(40):
        if capturado:
            break
        pg.wait_for_timeout(1_000)
    print("webgl    :", pg.evaluate(JS_WEBGL))
    print("webdriver:", pg.evaluate("() => navigator.webdriver"))
    print("ua       :", pg.evaluate("() => navigator.userAgent")[:100])
    print("hardware :", pg.evaluate("() => navigator.hardwareConcurrency"))
    print("NOTA     :", capturado[0] if capturado else "<nao capturou>")
    ctx.close()
    br.close()
