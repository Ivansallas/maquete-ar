"""Testes do carregamento de conteúdo JSON e da configuração."""

from __future__ import annotations

import json

import pytest

from conftest import ROOT
from core.config import DEFAULT_CONFIG, load_config
from core.content import ContentError, ContentManager, ElementContent, parse_color

# Elementos construídos na maquete física (ver assets/Documents/).
REQUIRED_IDS = {
    "agricultura",
    "armazem",
    "comercio",
    "cooperativa",
    "distribuidora",
    "escritorio_comercial",
    "escritorio_fazenda",
    "feira_produtor",
    "industria",
    "leilao",
    "loja_insumos",
    "maquinarios",
    "meio_ambiente",
    "paineis_solares",
    "pecuaria",
    "supermercado",
    "trator",
    "veterinaria",
}

# Elementos retirados: id e ArUco nunca podem ser reaproveitados (QRs antigos impressos).
RETIRED_IDS = {"infraestrutura", "residencia"}
RETIRED_ARUCOS = {3, 6}


def write(path, data) -> None:
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_todos_os_conteudos_do_projeto_carregam():
    cm = ContentManager(ROOT / "content")
    assert cm.errors == []
    assert set(cm.ids) >= REQUIRED_IDS
    assert not set(cm.ids) & RETIRED_IDS
    assert not {item.aruco for cid in cm.ids if (item := cm.get(cid))} & RETIRED_ARUCOS
    agri = cm.get("agricultura")
    assert agri is not None and agri.titulo == "Agricultura" and agri.icone == "🌱"


def test_conteudo_desconhecido_retorna_none():
    cm = ContentManager(ROOT / "content")
    assert cm.get("nave_espacial") is None
    assert cm.get(None) is None
    assert "nave_espacial" not in cm


def test_json_invalido_nao_derruba_os_demais(tmp_path):
    write(tmp_path / "bom.json", {"id": "bom", "titulo": "Bom", "descricao": "ok"})
    write(tmp_path / "quebrado.json", "{ isto não é json ")
    cm = ContentManager(tmp_path)
    assert cm.ids == ["bom"]
    assert len(cm.errors) == 1 and "quebrado.json" in cm.errors[0]


@pytest.mark.parametrize(
    "data, message",
    [
        ({"titulo": "x", "descricao": "y"}, "id"),
        ({"id": "x", "descricao": "y"}, "titulo"),
        ({"id": "x", "titulo": "x", "descricao": ""}, "descricao"),
        ({"id": "../x", "titulo": "x", "descricao": "y"}, "id inválido"),
        ({"id": "x", "titulo": "x", "descricao": "y", "cor": 123}, "cor"),
        ([1, 2, 3], "objeto"),
    ],
)
def test_conteudo_invalido(data, message):
    with pytest.raises(ContentError, match=message):
        ElementContent.from_dict(data)


def test_id_diferente_do_nome_do_arquivo(tmp_path):
    write(tmp_path / "trator.json", {"id": "carro", "titulo": "Carro", "descricao": "x"})
    cm = ContentManager(tmp_path)
    assert len(cm) == 0 and "diferente" in cm.errors[0]


def test_pasta_inexistente(tmp_path):
    cm = ContentManager(tmp_path / "nao_existe")
    assert len(cm) == 0 and cm.errors


def test_campos_extras_e_futuros_sao_preservados():
    item = ElementContent.from_dict(
        {"id": "x", "titulo": "X", "descricao": "d", "imagem": "assets/images/x.png", "nivel": 2}
    )
    assert item.imagem == "assets/images/x.png"
    assert item.extras == {"nivel": 2}


def test_cores():
    assert parse_color("green") == (60, 180, 75)
    assert parse_color("#FF0000") == (0, 0, 255)  # BGR
    assert parse_color("cor_que_nao_existe") == (240, 240, 240)
    assert parse_color(None) == (240, 240, 240)


def test_config_ausente_usa_padrao(tmp_path):
    assert load_config(tmp_path / "nada.json") == DEFAULT_CONFIG


def test_config_parcial_e_mesclada(tmp_path):
    write(tmp_path / "c.json", {"camera": {"index": 2}, "debug": False})
    cfg = load_config(tmp_path / "c.json")
    assert cfg["camera"]["index"] == 2
    assert cfg["camera"]["width"] == DEFAULT_CONFIG["camera"]["width"]
    assert cfg["debug"] is False


def test_config_quebrada_usa_padrao(tmp_path):
    write(tmp_path / "c.json", "{ quebrado")
    assert load_config(tmp_path / "c.json") == DEFAULT_CONFIG


def test_config_do_projeto_e_valida():
    cfg = load_config(ROOT / "config.json")
    assert cfg["camera"]["width"] > 0 and isinstance(cfg["debug"], bool)
