"""Tela Ordem na vitrine — grade, paginação e save da ordem global."""
from conftest import csrf_da_resposta, login


class _EstoqueFake:
    def __init__(self, n=2):
        self.veiculos = []
        for i in range(n):
            self.veiculos.append(
                {
                    "id": f"v-{i}",
                    "marca": "Honda" if i % 2 == 0 else "Yamaha",
                    "modelo": f"Moto {i}",
                    "ano_modelo": 2020 + (i % 5),
                    "preco": 10000 + i * 100,
                    "km": i * 1000,
                    "tipo": "moto",
                    "publicado": True,
                    "status": "disponivel",
                    "ordem_vitrine": i,
                    "foto_url": f"https://img.test/{i}.jpg" if i % 3 else None,
                }
            )
        self.reordenacoes: list[list[dict]] = []

    def listar(self, **filtros):
        return list(self.veiculos)

    def reordenar_vitrine(self, itens):
        self.reordenacoes.append(itens)
        for item in itens:
            for v in self.veiculos:
                if v["id"] == item["id"]:
                    v["ordem_vitrine"] = item["ordem_vitrine"]
        return {"ok": True, "atualizados": len(itens)}


def test_vitrine_renderiza_e_salva_ordem(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    fake = _EstoqueFake(n=2)

    from app.main import app
    from app.web import loja_estoque

    app.dependency_overrides[loja_estoque.get_estoque_client] = lambda: fake
    try:
        login(client)
        get = client.get("/app/loja/estoque/vitrine")
        assert get.status_code == 200
        assert "Ordem na vitrine" in get.text
        assert "Moto 0" in get.text
        assert "data-vitrine-grid" in get.text
        assert "vitrine-grid" in get.text
        assert "Salvar ordem" in get.text

        csrf = csrf_da_resposta(get)
        post = client.post(
            "/app/loja/estoque/vitrine",
            data={"csrf": csrf, "ordem_ids": "v-1,v-0", "limit": "12", "offset": "0"},
            follow_redirects=False,
        )
        assert post.status_code == 303
        assert "/app/loja/estoque/vitrine" in post.headers["location"]
        assert fake.reordenacoes == [
            [
                {"id": "v-1", "ordem_vitrine": 0},
                {"id": "v-0", "ordem_vitrine": 1},
            ]
        ]
    finally:
        app.dependency_overrides.pop(loja_estoque.get_estoque_client, None)


def test_vitrine_paginacao_12_por_pagina(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    fake = _EstoqueFake(n=25)

    from app.main import app
    from app.web import loja_estoque

    app.dependency_overrides[loja_estoque.get_estoque_client] = lambda: fake
    try:
        login(client)
        p1 = client.get("/app/loja/estoque/vitrine")
        assert p1.status_code == 200
        assert "Mostrando" in p1.text
        assert "1–12" in p1.text.replace(" ", "") or "1–12" in p1.text
        assert "de <strong>25</strong>" in p1.text or "de 25" in p1.text.replace(
            "<strong>", ""
        ).replace("</strong>", "")
        assert "Moto 0" in p1.text
        assert "Moto 12" not in p1.text  # segunda página
        assert "Próxima" in p1.text
        assert 'href="/app/loja/estoque/vitrine?limit=12&amp;offset=12"' in p1.text or (
            "offset=12" in p1.text and "limit=12" in p1.text
        )
        # Números de página no estilo catálogo
        assert "vitrine-pagination" in p1.text
        assert "vitrine-page-btn" in p1.text

        p2 = client.get("/app/loja/estoque/vitrine?limit=12&offset=12")
        assert p2.status_code == 200
        assert "Moto 12" in p2.text
        assert "Moto 0" not in p2.text
        assert "13–24" in p2.text or "13–24" in p2.text.replace(" ", "")
        assert "Anterior" in p2.text
    finally:
        app.dependency_overrides.pop(loja_estoque.get_estoque_client, None)
