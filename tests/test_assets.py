"""Testes da Fase 2: imagens nos painéis (caminhos seguros, carga, fallback)."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from ar.objects import ARObjectFactory, ImagePanel, RenderContext, TextPanel
from ar.overlay import render_panel
from core.assets import AssetError, load_image, resolve_asset
from core.content import ContentManager, ElementContent
from qr.markers import QRMarker


def save_png(path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    buf.tofile(str(path))


@pytest.fixture
def assets(tmp_path):
    root = tmp_path / "assets"
    img = np.zeros((300, 400, 3), np.uint8)
    img[:, :200] = (0, 0, 255)  # metade vermelha (BGR)
    save_png(root / "images" / "trator.png", img)
    rgba = np.zeros((50, 50, 4), np.uint8)
    rgba[10:40, 10:40] = (255, 0, 0, 255)
    save_png(root / "images" / "transparente.png", rgba)
    save_png(tmp_path / "fora.png", img)  # fora da pasta assets
    (root / "images" / "corrompida.png").write_bytes(b"isto nao e um png")
    (root / "images" / "texto.txt").write_text("oi", encoding="utf-8")
    return root


def content(imagem: str | None) -> ElementContent:
    return ElementContent.from_dict(
        {"id": "trator", "titulo": "Trator", "descricao": "Máquina agrícola.", "imagem": imagem}
    )


# --------------------------------------------------------------- caminhos
def test_resolve_caminho_relativo(assets):
    assert resolve_asset(assets, "images/trator.png") == (assets / "images" / "trator.png").resolve()


def test_resolve_aceita_prefixo_assets_e_barra_invertida(assets):
    expected = (assets / "images" / "trator.png").resolve()
    assert resolve_asset(assets, "assets/images/trator.png") == expected
    assert resolve_asset(assets, "images\\trator.png") == expected


@pytest.mark.parametrize(
    "caminho",
    ["../fora.png", "images/../../fora.png", "/etc/passwd.png", "C:/Windows/win.png", "", "images/texto.txt"],
)
def test_resolve_rejeita_caminhos_perigosos_ou_invalidos(assets, caminho):
    with pytest.raises(AssetError):
        resolve_asset(assets, caminho)


def test_resolve_arquivo_inexistente(assets):
    with pytest.raises(AssetError, match="não encontrad"):
        resolve_asset(assets, "images/nao_existe.png")


# --------------------------------------------------------------- carga
def test_load_image_devolve_bgra(assets):
    img = load_image(assets / "images" / "trator.png")
    assert img.shape == (300, 400, 4) and img.dtype == np.uint8
    assert (img[:, :, 3] == 255).all()


def test_load_image_preserva_transparencia(assets):
    img = load_image(assets / "images" / "transparente.png")
    assert img[0, 0, 3] == 0 and img[25, 25, 3] == 255


def test_load_image_reduz_imagens_grandes(tmp_path):
    save_png(tmp_path / "grande.png", np.zeros((3000, 4000, 3), np.uint8))
    img = load_image(tmp_path / "grande.png", max_side=800)
    assert max(img.shape[:2]) == 800


def test_load_image_corrompida(assets):
    with pytest.raises(AssetError):
        load_image(assets / "images" / "corrompida.png")


# --------------------------------------------------------------- painel
def test_painel_com_imagem_e_mais_alto_e_contem_a_imagem():
    picture = np.zeros((300, 400, 4), np.uint8)
    picture[:] = (0, 0, 255, 255)  # vermelho puro
    sem = render_panel(content(None), 640)
    com = render_panel(content(None), 640, picture)
    assert com.shape[1] == sem.shape[1] and com.shape[0] > sem.shape[0]
    red = (com[:, :, 2] > 240) & (com[:, :, 1] < 15) & (com[:, :, 0] < 15)
    assert red.sum() > 10_000


def test_factory_usa_imagepanel_quando_ha_imagem(assets):
    factory = ARObjectFactory(assets_dir=assets)
    assert isinstance(factory.get(content("images/trator.png")), ImagePanel)


@pytest.mark.parametrize("imagem", [None, "images/corrompida.png", "images/nao_existe.png", "../fora.png"])
def test_factory_cai_para_texto_quando_imagem_falha(assets, imagem):
    obj = ARObjectFactory(assets_dir=assets).get(content(imagem))
    assert type(obj) is TextPanel


def test_imagepanel_desenha_sobre_o_qr(assets):
    frame = np.zeros((720, 1280, 3), np.uint8)
    marker = QRMarker.from_detection("trator", np.float32([[560, 450], [720, 450], [720, 610], [560, 610]]))
    obj = ARObjectFactory(assets_dir=assets).get(content("images/trator.png"))
    quad = obj.render(frame, marker, RenderContext())
    assert quad is not None and frame.any()
    assert quad[:, 1].max() <= 450  # painel acima do QR


def test_billboard_com_imagem_cabe_na_tela(assets):
    frame = np.zeros((480, 640, 3), np.uint8)
    marker = QRMarker.from_detection("trator", np.float32([[300, 200], [400, 200], [400, 300], [300, 300]]))
    obj = ARObjectFactory(assets_dir=assets).get(content("images/trator.png"))
    quad = obj.render(frame, marker, RenderContext(mode="billboard"))
    assert quad is not None
    assert quad[:, 1].min() >= 0 and quad[:, 1].max() <= 480


# --------------------------------------------------------------- conteúdo
def test_content_manager_avisa_imagem_ausente_mas_carrega_o_elemento(tmp_path, assets):
    folder = tmp_path / "content"
    folder.mkdir()
    for cid, img in (("trator", "images/trator.png"), ("pecuaria", "images/nao_existe.png")):
        data = {"id": cid, "titulo": cid, "descricao": "d", "imagem": img}
        (folder / f"{cid}.json").write_text(json.dumps(data), encoding="utf-8")
    cm = ContentManager(folder, assets_dir=assets)
    assert set(cm.ids) == {"trator", "pecuaria"}  # os dois carregam
    assert len(cm.errors) == 1 and "pecuaria.json" in cm.errors[0]


def test_painel_que_sairia_pelo_topo_vira_billboard_legivel():
    """Regressão: painel em perspectiva acima de um QR perto do topo da tela
    ficava com o título cortado. Agora ele cai para o modo billboard."""
    frame = np.zeros((720, 1280, 3), np.uint8)
    marker = QRMarker.from_detection("trator", np.float32([[560, 120], [720, 120], [720, 280], [560, 280]]))
    quad = TextPanel(content(None)).render(frame, marker, RenderContext(mode="perspective"))
    assert quad is not None
    assert quad[:, 1].min() >= 0  # título visível


@pytest.mark.parametrize("qr_y", [120, 300, 520])
def test_billboard_nunca_cobre_o_proprio_qr(assets, qr_y):
    """Regressão: sem espaço acima nem abaixo, o painel era empurrado para
    cima do QR (que deixava de ser lido). Agora ele vai para o lado."""
    frame = np.zeros((720, 1280, 3), np.uint8)
    corners = np.float32([[560, qr_y], [720, qr_y], [720, qr_y + 160], [560, qr_y + 160]])
    marker = QRMarker.from_detection("trator", corners)
    obj = ARObjectFactory(assets_dir=assets).get(content("images/trator.png"))
    quad = obj.render(frame, marker, RenderContext(mode="billboard"))
    assert quad is not None
    (px0, py0), (px1, py1) = quad.min(axis=0), quad.max(axis=0)
    overlap_x = min(px1, 720) - max(px0, 560)
    overlap_y = min(py1, qr_y + 160) - max(py0, qr_y)
    assert overlap_x <= 0 or overlap_y <= 0
    assert px0 >= 0 and py0 >= 0 and px1 <= 1280 and py1 <= 720


def test_billboard_evita_cobrir_outros_qrs(assets):
    """O espaço acima do QR está ocupado por outro QR: o painel deve ir
    para outra posição livre em vez de cobri-lo."""
    frame = np.zeros((720, 1280, 3), np.uint8)
    marker = QRMarker.from_detection("trator", np.float32([[560, 420], [720, 420], [720, 580], [560, 580]]))
    vizinho = (560.0, 150.0, 720.0, 310.0)  # x0, y0, x1, y1 de outro QR, logo acima
    obj = ARObjectFactory(assets_dir=assets).get(content("images/trator.png"))
    ctx = RenderContext(mode="billboard", obstacles=(vizinho,))
    quad = obj.render(frame, marker, ctx)
    assert quad is not None
    (px0, py0), (px1, py1) = quad.min(axis=0), quad.max(axis=0)
    assert min(px1, 720) - max(px0, 560) <= 0 or min(py1, 310) - max(py0, 150) <= 0
