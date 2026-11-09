"""Testes da Fase 4: um ArUco por elemento (identifica e posiciona quando o QR falha)."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from conftest import ROOT, make_scene
from core.content import ContentError, ContentManager, ElementContent
from qr.markers import MarkerStatus, QRMarker
from vision.aruco import ArucoDetector, ArucoMarker
from vision.fusion import MarkerFusion


def square(x: float, y: float, side: float) -> np.ndarray:
    return np.float32([[x, y], [x + side, y], [x + side, y + side], [x, y + side]])


def qr(text: str, x: float, y: float, side: float = 200) -> QRMarker:
    return QRMarker.from_detection(text, square(x, y, side))


def aruco(marker_id: int, x: float, y: float, side: float = 80) -> ArucoMarker:
    return ArucoMarker(marker_id, square(x, y, side))


@pytest.fixture
def fusion() -> MarkerFusion:
    return MarkerFusion({7: "trator", 5: "pecuaria"})


# --------------------------------------------------------------- conteúdo
def test_campo_aruco_e_lido():
    item = ElementContent.from_dict({"id": "trator", "titulo": "T", "descricao": "d", "aruco": 7})
    assert item.aruco == 7
    assert ElementContent.from_dict({"id": "x", "titulo": "T", "descricao": "d"}).aruco is None


@pytest.mark.parametrize("valor", ["7", 7.5, True, -1, 1000])
def test_campo_aruco_invalido(valor):
    with pytest.raises(ContentError, match="aruco"):
        ElementContent.from_dict({"id": "trator", "titulo": "T", "descricao": "d", "aruco": valor})


def test_aruco_repetido_gera_erro_e_e_ignorado_no_segundo(tmp_path):
    for cid in ("agricultura", "trator"):
        data = {"id": cid, "titulo": cid, "descricao": "d", "aruco": 3}
        (tmp_path / f"{cid}.json").write_text(json.dumps(data), encoding="utf-8")
    cm = ContentManager(tmp_path)
    assert set(cm.ids) == {"agricultura", "trator"}  # os dois carregam
    assert cm.aruco_map == {3: "agricultura"}  # ordem alfabética: o primeiro fica
    assert len(cm.errors) == 1 and "trator.json" in cm.errors[0] and "3" in cm.errors[0]


def test_elementos_base_tem_aruco_unico():
    cm = ContentManager(ROOT / "content")
    ids = [cm.get(cid).aruco for cid in cm.ids]  # type: ignore[union-attr]
    assert None not in ids and len(set(ids)) == len(ids)


# --------------------------------------------------------------- fusão
def test_qr_legivel_passa_direto(fusion):
    out = fusion.update([qr("trator", 100, 100)], [])
    assert len(out) == 1 and out[0].element_id == "trator" and not out[0].via_aruco


def test_so_aruco_vira_marcador_do_elemento(fusion):
    out = fusion.update([], [aruco(7, 400, 300)])
    assert len(out) == 1
    m = out[0]
    assert m.element_id == "trator" and m.status == MarkerStatus.OK and m.via_aruco
    np.testing.assert_allclose(m.corners, square(400, 300, 80), atol=1e-3)  # nada aprendido: o próprio ArUco


def test_aprende_posicao_do_qr_e_usa_quando_o_qr_some(fusion):
    # QR 200x200 em (100,100) e ArUco 80x80 à direita, em (320,160)
    fusion.update([qr("trator", 100, 100)], [aruco(7, 320, 160)])
    # câmera se moveu +50 px em x e o QR não foi lido: ArUco recria o QR no lugar certo
    out = fusion.update([], [aruco(7, 370, 160)])
    assert len(out) == 1 and out[0].via_aruco
    np.testing.assert_allclose(out[0].corners, square(150, 100, 200), atol=0.5)


def test_aprendizado_acompanha_escala(fusion):
    fusion.update([qr("trator", 100, 100)], [aruco(7, 320, 160)])
    out = fusion.update([], [aruco(7, 160, 80, side=40)])  # tudo pela metade (câmera mais longe)
    np.testing.assert_allclose(out[0].corners, square(50, 50, 100), atol=0.5)


def test_nao_duplica_quando_qr_e_aruco_aparecem(fusion):
    out = fusion.update([qr("trator", 100, 100)], [aruco(7, 320, 160)])
    assert [m.element_id for m in out] == ["trator"] and not out[0].via_aruco


def test_qr_ilegivel_no_lugar_do_qr_e_substituido(fusion):
    fusion.update([qr("trator", 100, 100)], [aruco(7, 320, 160)])
    out = fusion.update([qr("", 102, 101)], [aruco(7, 320, 160)])
    assert len(out) == 1 and out[0].element_id == "trator" and out[0].via_aruco


def test_qr_ilegivel_em_outro_lugar_e_mantido(fusion):
    out = fusion.update([qr("", 900, 500)], [aruco(7, 320, 160)])
    assert {m.status for m in out} == {MarkerStatus.OK, MarkerStatus.UNREADABLE}


def test_aruco_desconhecido_e_ignorado(fusion):
    assert fusion.update([], [aruco(42, 100, 100)]) == []


def test_associacao_absurda_nao_e_aprendida(fusion):
    # QR "trator" muito longe do ArUco 7 (outro trator? reflexo?): não aprende
    fusion.update([qr("trator", 0, 0)], [aruco(7, 1200, 650, side=20)])
    out = fusion.update([], [aruco(7, 1200, 650, side=20)])
    np.testing.assert_allclose(out[0].corners, square(1200, 650, 20), atol=1e-3)


# --------------------------------------------------------------- pipeline com imagem
def _paste_aruco(scene: np.ndarray, marker_id: int, x: int, y: int, side: int) -> None:
    img = ArucoDetector().generate(marker_id, side)
    h, w = img.shape
    scene[y : y + h, x : x + w] = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_pipeline_mantem_elemento_quando_qr_e_coberto(generator):
    from app import MaqueteARApp
    from core.config import load_config

    app = MaqueteARApp(load_config(ROOT / "config.json"), source="demo")
    trator_aruco = app.contents.get("trator").aruco  # type: ignore[union-attr]
    scene, _ = make_scene(generator, ["trator"], qr_px=220)
    _paste_aruco(scene, trator_aruco, 1000, 260, 140)
    app.process(scene.copy())  # QR + ArUco: aprende
    covered = scene.copy()
    covered[200:520, 500:780] = 128  # mão na frente do QR
    for _ in range(20):  # bem mais que max_missing_frames
        app.process(covered.copy())
    tracks = [t for t in app.tracker.tracks if t.marker.element_id == "trator"]
    assert len(tracks) == 1 and tracks[0].visible and tracks[0].marker.via_aruco
    np.testing.assert_allclose(tracks[0].marker.center, (640, 360), atol=6)  # onde o QR estava


def test_demo_tem_aruco_ao_lado_dos_qrs():
    from camera.camera import build_source
    from core.config import load_config

    cm = ContentManager(ROOT / "content")
    src = build_source(load_config(ROOT / "config.json")["camera"], "demo", demo_ids=cm.ids, aruco_map=cm.aruco_map)
    src.open()
    found = ArucoDetector().detect(src.read())
    assert {m.marker_id for m in found} & set(cm.aruco_map)


# --------------------------------------------------------------- impressão
def test_folha_a4_tem_todos_os_elementos_com_aruco(generator):
    """Regressão: com o ArUco ao lado, a folha ficava com 1 coluna e os
    elementos que não cabiam eram descartados sem aviso."""
    from qr.generator import make_print_sheets

    items = [(f"elem_{i}", f"Elemento {i}") for i in range(11)]
    arucos = {data: i for i, (data, _) in enumerate(items)}
    pages = make_print_sheets(items, generator, qr_cm=5.0, aruco_ids=arucos, aruco_cm=3.0, dpi=100)
    assert len(pages) == 2  # 8 por página (2 colunas x 4 linhas) -> 11 elementos = 2 páginas
    found: set[int] = set()
    for page in pages:
        found |= {m.marker_id for m in ArucoDetector().detect(cv2.cvtColor(np.array(page), cv2.COLOR_GRAY2BGR))}
    assert found == set(range(11))
