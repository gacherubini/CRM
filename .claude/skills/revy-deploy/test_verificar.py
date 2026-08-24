"""Testes do pos-flight da revy-deploy.

O pos-flight existe porque 'o comando terminou sem erro' nao e prova de nada:
o Cloudflare responde 200 para um preview que ninguem esta vendo, e o Fly
volta a versao anterior sem reclamar.
"""

import unittest

import verificar


class TestApp(unittest.TestCase):
    def test_sha_bate_e_aprovado(self):
        ok, msg = verificar.conferir_app("ok sha:a1b2c3d\n", "a1b2c3d")
        self.assertTrue(ok, msg)

    def test_sha_antigo_significa_que_nao_subiu(self):
        ok, msg = verificar.conferir_app("ok sha:0000000\n", "a1b2c3d")
        self.assertFalse(ok)
        self.assertIn("0000000", msg)

    def test_health_falhando_reprova_mesmo_com_deploy_ok(self):
        ok, msg = verificar.conferir_app("fail:chatbot,estoque\n", "a1b2c3d")
        self.assertFalse(ok)
        self.assertIn("chatbot", msg)

    def test_prod_sem_carimbo_reprova(self):
        ok, _ = verificar.conferir_app("ok\n", "a1b2c3d")
        self.assertFalse(ok)

    def test_prod_fora_do_ar_reprova(self):
        ok, _ = verificar.conferir_app(None, "a1b2c3d")
        self.assertFalse(ok)


class TestSite(unittest.TestCase):
    """A armadilha do --branch=main: sem ele o wrangler sobe um PREVIEW.

    Responde 200, nao da erro nenhum, e o dominio segue na versao anterior.
    So o carimbo no dominio distingue os dois casos.
    """

    def test_dominio_com_o_sha_novo_e_aprovado(self):
        ok, msg = verificar.conferir_site("a1b2c3d\n", "a1b2c3d")
        self.assertTrue(ok, msg)

    def test_dominio_no_sha_antigo_e_preview_silencioso(self):
        ok, msg = verificar.conferir_site("0000000\n", "a1b2c3d")
        self.assertFalse(ok)
        self.assertIn("preview", msg.lower())
        self.assertIn("--branch=main", msg)

    def test_bom_nao_vira_reprova_falsa(self):
        """PowerShell 5.1 grava BOM. Reprovar por isso mandaria o dono
        re-deployar um site que ja estava certo."""
        ok, msg = verificar.conferir_site("﻿a1b2c3d\r\n", "a1b2c3d")
        self.assertTrue(ok, msg)

    def test_sem_build_txt_reprova(self):
        ok, _ = verificar.conferir_site(None, "a1b2c3d")
        self.assertFalse(ok)


class TestN8n(unittest.TestCase):
    """O import DESATIVA o workflow. Sem reativar, o webhook da 404 para sempre
    - e a Evolution cancela o retry ao ver 404."""

    def test_workflow_ativo_e_aprovado(self):
        ok, msg = verificar.conferir_n8n([{"name": "revy", "active": True}], "revy")
        self.assertTrue(ok, msg)

    def test_workflow_inativo_reprova_citando_o_comando(self):
        ok, msg = verificar.conferir_n8n([{"name": "revy", "active": False}], "revy")
        self.assertFalse(ok)
        self.assertIn("--active=true", msg)

    def test_workflow_ausente_reprova(self):
        ok, _ = verificar.conferir_n8n([{"name": "outro", "active": True}], "revy")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
