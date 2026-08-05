"""Tela Ordem na vitrine — reorder de veículos publicados."""
from conftest import csrf_da_resposta, login


class _EstoqueFake:
    def __init__(self):
        self.veiculos = [
            {
                "id": "v-2",
                "marca": "Yamaha",
                "modelo": "Fazer",
                "ano_modelo": 2022,
                "preco": 18000,
                "publicado": True,
                "status": "disponivel",
                "ordem_vitrine": 1,
                "foto_url": None,
            },
            {
                "id": "v-1",
                "marca": "Honda",
                "modelo": "CG 160",
                "ano_modelo": 2023,
                "preco": 16000,
                "publicado": True,
                "status": "disponivel",
                "ordem_vitrine": 0,
                "foto_url": "https://img.test/cg.jpg",
            },
        ]
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
    fake = _EstoqueFake()

    from app.main import app
    from app.web import loja_estoque

    app.dependency_overrides[loja_estoque.get_estoque_client] = lambda: fake
    try:
        login(client)
        get = client.get("/app/loja/estoque/vitrine")
        assert get.status_code == 200
        assert "Ordem na vitrine" in get.text
        assert "CG 160" in get.text
        assert "Fazer" in get.text
        assert "data-vitrine-grid" in get.text
        assert "vitrine-grid" in get.text
        assert "vitrine_ordem.js" in get.text
        assert "Salvar ordem" in get.text
        # Save só no submit — botão começa desabilitado até sujar a ordem.
        assert 'id="vitrine-salvar"' in get.text

        csrf = csrf_da_resposta(get)
        post = client.post(
            "/app/loja/estoque/vitrine",
            data={"csrf": csrf, "ordem_ids": "v-2,v-1"},
            follow_redirects=False,
        )
        assert post.status_code == 303
        assert post.headers["location"] == "/app/loja/estoque/vitrine"
        assert fake.reordenacoes == [
            [
                {"id": "v-2", "ordem_vitrine": 0},
                {"id": "v-1", "ordem_vitrine": 1},
            ]
        ]

        after = client.get("/app/loja/estoque/vitrine")
        assert "salva" in after.text.lower()
    finally:
        app.dependency_overrides.pop(loja_estoque.get_estoque_client, None)
