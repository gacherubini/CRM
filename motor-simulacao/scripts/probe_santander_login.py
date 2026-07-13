"""Smoke: abre login Santander com a mesma stack anti-WAF do worker."""
from playwright.sync_api import sync_playwright

from app.motor.santander import fabrica_santander


def main() -> None:
    d = fabrica_santander()
    print("headless", d.headless)
    with sync_playwright() as p:
        browser = d._launch_browser(p)
        ctx = d._new_context(browser)
        page = ctx.new_page()
        page.set_default_timeout(45_000)
        try:
            try:
                page.goto(d.login_url, wait_until="networkidle", timeout=45_000)
            except Exception:
                page.goto(d.login_url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(1500)
            html = page.content() or ""
            blocked = (
                "Access Denied" in html
                or "errors.edgesuite" in html
                or "You don't have permission" in html
            )
            has_login = (
                "CPF" in html
                or "Entrar" in html
                or "senha" in html.lower()
                or "Portal Auto" in html
            )
            print("title", page.title())
            print("url", (page.url or "")[:160])
            print("blocked", blocked, "has_login_ui", has_login)
            page.screenshot(
                path="/srv/data/screenshots/probe_headed.png", full_page=True
            )
            print("shot ok")
            if blocked:
                d._assert_portal_acessivel(page)
            print("RESULT", "BLOQUEADO" if blocked else "OK")
        except Exception as e:
            print("ERR", type(e).__name__, str(e).replace("\n", " ")[:240])
            print("RESULT FAIL")
        finally:
            ctx.close()
            browser.close()


if __name__ == "__main__":
    main()
