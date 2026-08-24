"""Testes do preflight da revy-deploy.

Rodar da pasta da skill:
    python -m pytest test_preflight.py -q      # Windows
    python3 -m pytest test_preflight.py -q     # Mac do dono
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

import preflight


class TestRoteador(unittest.TestCase):
    """De caminho mudado para alvo. So deploya o que mudou."""

    def test_nada_mudou_nao_deploya_nada(self):
        self.assertEqual(preflight.alvos_para([]), set())

    def test_doc_e_teste_nao_deployam(self):
        caminhos = [
            "docs/fila/card.md",
            "AGENTS.md",
            "chatbot-api/tests/test_x.py",
            ".claude/skills/revy-research/mapa/portal.md",
        ]
        self.assertEqual(preflight.alvos_para(caminhos), set())

    def test_codigo_de_produto_vai_para_o_bundle(self):
        for caminho in [
            "portal-gestao/app/main.py",
            "revy-trafego/app/servico.py",
            "chatbot-api/app/servico.py",
            "estoque-api/app/models_db.py",
            "catalogo-publico/app/main.py",
            "portal-gestao/alembic/versions/0007_x.py",
        ]:
            with self.subTest(caminho=caminho):
                self.assertIn("app2037", preflight.alvos_para([caminho]))

    def test_site_vai_para_cloudflare_e_nao_para_o_fly(self):
        alvos = preflight.alvos_para(["site/index.html"])
        self.assertEqual(alvos, {"site"})

    def test_prompt_do_bot_vai_para_o_n8n_e_nao_para_o_app(self):
        """O systemMessage mora no workflow, nao no chatbot-api.

        Mexer no prompt e subir o app2037 deixa o bot falando igual.
        """
        alvos = preflight.alvos_para(["n8n/workflow-ai-nao-salvos.json"])
        self.assertEqual(alvos, {"n8n2037"})

    def test_motor_sobe_nos_dois_lugares(self):
        """motor-api vive no bundle; o worker Playwright e o motor2037."""
        alvos = preflight.alvos_para(["motor-simulacao/app/simulador.py"])
        self.assertIn("app2037", alvos)
        self.assertIn("motor2037", alvos)

    def test_toml_do_n8n_nao_arrasta_o_bundle(self):
        self.assertEqual(
            preflight.alvos_para(["deploy/fly/3vm/fly.n8n.toml"]), {"n8n2037"}
        )

    def test_dockerfile_do_bundle_sobe_o_bundle(self):
        self.assertEqual(
            preflight.alvos_para(["deploy/fly/3vm/Dockerfile.app"]), {"app2037"}
        )

    def test_mudanca_em_varios_produtos_junta_alvos(self):
        alvos = preflight.alvos_para(
            ["portal-gestao/app/main.py", "site/index.html", "n8n/workflow-ai-nao-salvos.json"]
        )
        self.assertEqual(alvos, {"app2037", "site", "n8n2037"})


class TestCacheBust(unittest.TestCase):
    """app.css mudou e o ?v= nao subiu = prod serve CSS velho."""

    def test_css_mudou_e_versao_ficou_igual_bloqueia(self):
        pendentes = preflight.cache_bust_pendente(
            ["portal-gestao/app/static/css/app.css"],
            versoes_antes={"portal-gestao": "v15"},
            versoes_agora={"portal-gestao": "v15"},
        )
        self.assertEqual(pendentes, ["portal-gestao"])

    def test_css_mudou_e_versao_subiu_passa(self):
        pendentes = preflight.cache_bust_pendente(
            ["portal-gestao/app/static/css/app.css"],
            versoes_antes={"portal-gestao": "v15"},
            versoes_agora={"portal-gestao": "v16"},
        )
        self.assertEqual(pendentes, [])

    def test_css_intocado_nao_exige_bump(self):
        pendentes = preflight.cache_bust_pendente(
            ["portal-gestao/app/main.py"],
            versoes_antes={"portal-gestao": "v15"},
            versoes_agora={"portal-gestao": "v15"},
        )
        self.assertEqual(pendentes, [])

    def test_le_o_v_dos_dois_produtos_no_repo_de_verdade(self):
        """O Control usa public_path(); o Portal usa href direto.

        Um regex que so pega o Portal deixa o Control servir CSS velho.
        """
        versoes = preflight.versoes_css(preflight.raiz_repo())
        self.assertIn("portal-gestao", versoes)
        self.assertIn("revy-trafego", versoes)
        for produto, por_arquivo in versoes.items():
            with self.subTest(produto=produto):
                self.assertTrue(por_arquivo, f"nenhum ?v= achado em {produto}")

    def test_telas_de_auth_fora_de_sincronia_sao_denunciadas(self):
        """5 templates no Portal, 3 no Control. Bumpar so o base.html
        deixa login e convite servindo CSS velho."""
        divergentes = preflight.versoes_divergentes(
            {"base.html": "v16", "login.html": "v15", "convite_aceitar.html": "v15"}
        )
        self.assertEqual(sorted(divergentes), ["convite_aceitar.html", "login.html"])

    def test_repo_de_verdade_esta_sincronizado(self):
        for produto, por_arquivo in preflight.versoes_css(preflight.raiz_repo()).items():
            with self.subTest(produto=produto):
                self.assertEqual(preflight.versoes_divergentes(por_arquivo), [])


class TestRepoLimpo(unittest.TestCase):
    """fly deploy usa a arvore local, nao o commit. Sujo = prod diverge do repo."""

    def _repo_temporario(self):
        tmp = tempfile.mkdtemp()
        raiz = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=raiz, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=raiz, check=True)
        (raiz / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
        subprocess.run(["git", "commit", "-qm", "inicial"], cwd=raiz, check=True)
        return raiz

    def test_repo_limpo_passa(self):
        raiz = self._repo_temporario()
        limpo, sujos = preflight.repo_limpo(raiz)
        self.assertTrue(limpo)
        self.assertEqual(sujos, [])

    def test_arquivo_modificado_bloqueia(self):
        raiz = self._repo_temporario()
        (raiz / "a.py").write_text("x = 2\n", encoding="utf-8")
        limpo, sujos = preflight.repo_limpo(raiz)
        self.assertFalse(limpo)
        self.assertIn("a.py", " ".join(sujos))

    def test_arquivo_novo_nao_rastreado_bloqueia(self):
        raiz = self._repo_temporario()
        (raiz / "b.py").write_text("y = 1\n", encoding="utf-8")
        limpo, sujos = preflight.repo_limpo(raiz)
        self.assertFalse(limpo, "arquivo novo entra na imagem e some do repo")


class TestShaDeProd(unittest.TestCase):
    """O /healthz carimbado e a unica fonte de 'o que esta em prod'."""

    def test_le_o_sha_do_corpo(self):
        self.assertEqual(preflight.sha_do_healthz("ok sha:a1b2c3d\n"), "a1b2c3d")

    def test_prod_sem_carimbo_devolve_none(self):
        """Prod antes do primeiro deploy carimbado. Nao da pra rotear: e cego."""
        self.assertIsNone(preflight.sha_do_healthz("ok\n"))

    def test_healthz_falhando_devolve_none(self):
        self.assertIsNone(preflight.sha_do_healthz("fail:chatbot,estoque\n"))


if __name__ == "__main__":
    unittest.main()
