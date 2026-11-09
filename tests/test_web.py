"""Testes da versão para celular: QR com link, exportação do site e testes JS."""

from __future__ import annotations

import json
import shutil
import subprocess

import cv2
import numpy as np
import pytest

from conftest import ROOT, make_scene
from core.config import load_config
from qr.detector import QRCodeDetector
from qr.generator import QRCodeGenerator, qr_payload
from qr.markers import MarkerStatus, QRMarker, normalize_qr_text

URL = "https://professora.github.io/maquete-ar/"


# --------------------------------------------------------------- QR com link
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("trator", "trator"),
        (f"{URL}?e=trator", "trator"),
        (f"{URL}?e=meio_ambiente", "meio_ambiente"),
        (f"{URL}index.html?x=1&e=pecuaria#topo", "pecuaria"),
        ("HTTPS://Exemplo.org/?e=Trator", "trator"),
        (f"{URL}?e=../hack", None),
        (f"{URL}?e=", None),
        (URL, None),  # link sem elemento
        ("javascript:alert(1)?e=trator", None),
        ("file:///C:/x?e=trator", None),
        ("ftp://x/?e=trator", None),
        (f"{URL}?e=trator&e=pecuaria", None),  # ambíguo
        ("https://x/?e=" + "a" * 300, None),
    ],
)
def test_qr_aceita_id_ou_link_com_elemento(texto, esperado):
    assert normalize_qr_text(texto) == esperado


def test_qr_payload():
    assert qr_payload("trator", None) == "trator"
    assert qr_payload("trator", "") == "trator"
    assert qr_payload("trator", URL) == f"{URL}?e=trator"
    assert qr_payload("trator", URL.rstrip("/")) == f"{URL}?e=trator"
    with pytest.raises(ValueError):
        qr_payload("../x", URL)
    with pytest.raises(ValueError):
        qr_payload("trator", "http://inseguro.org/")  # câmera do celular exige HTTPS


def test_qr_com_link_e_lido_pelo_app_do_pc(generator):
    payload = qr_payload("trator", URL)
    scene, _ = make_scene(generator, [], qr_px=300)
    qr = np.array(generator.make_qr(payload).resize((300, 300)))
    scene[200:500, 500:800] = qr[:, :, None]
    found = QRCodeDetector("aruco").detect(scene)
    assert len(found) == 1 and found[0].element_id == "trator" and found[0].status == MarkerStatus.OK


def test_marcador_de_link_mostra_o_id_no_rotulo():
    m = QRMarker.from_detection(f"{URL}?e=trator", np.float32([[0, 0], [9, 0], [9, 9], [0, 9]]))
    assert m.label == "trator"


def test_gerador_aceita_link_e_rejeita_texto_qualquer():
    gen = QRCodeGenerator(box_size=4)
    assert gen.make_qr(qr_payload("trator", URL)).width > 0
    with pytest.raises(ValueError):
        gen.make_qr("https://site-qualquer.org/")


def test_config_web_url_padrao_e_vazia():
    assert load_config(ROOT / "nao_existe.json")["web"]["url"] is None


# --------------------------------------------------------------- exportação do site
@pytest.fixture
def site(tmp_path):
    from scripts.exportar_web import export_site

    out = tmp_path / "site"
    export_site(out)
    return out


def test_exporta_paginas_bibliotecas_e_dados(site):
    for rel in ("index.html", "css/app.css", "js/main.js", "vendor/jsQR.js", "vendor/aruco/aruco.js", ".nojekyll"):
        assert (site / rel).is_file(), rel
    assert not (site / "tests").exists()  # testes JS não são publicados
    data = json.loads((site / "data" / "conteudo.json").read_text(encoding="utf-8"))
    els = data["elementos"]
    assert set(els) >= {"agricultura", "pecuaria", "trator"}
    assert els["pecuaria"]["titulo"] == "Pecuária"  # acentos preservados
    assert els["trator"]["cor"] == "#f0c800"  # "yellow" (BGR 0,200,240) em hex RGB
    assert data["aruco"]["7"] == "trator"
    assert (site / "data" / "teste.png").stat().st_size > 10_000


def test_exporta_so_midia_valida_e_referenciada(tmp_path):
    from scripts.exportar_web import export_site

    content, assets = tmp_path / "content", tmp_path / "assets"
    (assets / "images").mkdir(parents=True)
    content.mkdir()
    ok, png = cv2.imencode(".png", np.zeros((20, 30, 3), np.uint8))
    assert ok
    png.tofile(str(assets / "images" / "trator.png"))
    (assets / "images" / "nao_usada.png").write_bytes(b"x")
    (tmp_path / "segredo.png").write_bytes(b"x")
    items = {
        "trator": {"imagem": "images/trator.png"},
        "pecuaria": {"imagem": "../segredo.png"},
        "comercio": {"animacao": "animations/sumiu.gif"},
    }
    for cid, extra in items.items():
        data = {"id": cid, "titulo": cid, "descricao": "d", **extra}
        (content / f"{cid}.json").write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "site"
    export_site(out, content_dir=content, assets_dir=assets)
    els = json.loads((out / "data" / "conteudo.json").read_text(encoding="utf-8"))["elementos"]
    assert els["trator"]["imagem"] == "data/assets/images/trator.png"
    assert (out / "data" / "assets" / "images" / "trator.png").is_file()
    assert els["pecuaria"]["imagem"] is None and els["comercio"]["animacao"] is None
    copied = {p.name for p in (out / "data" / "assets").rglob("*") if p.is_file()}
    assert copied == {"trator.png"}


def test_exportacao_limpa_saida_antiga(tmp_path):
    from scripts.exportar_web import export_site

    out = tmp_path / "site"
    (out / "data").mkdir(parents=True)
    (out / "data" / "velho.json").write_text("{}", encoding="utf-8")
    export_site(out)
    assert not (out / "data" / "velho.json").exists()


# --------------------------------------------------------------- testes do JavaScript
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado")
def test_javascript_da_pagina():
    result = subprocess.run(
        ["node", "--test", "web/tests/*.test.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
