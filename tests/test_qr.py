"""Testes de geração, leitura, validação e rastreamento de QR Codes."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
import qrcode

from conftest import make_scene
from qr.detector import QRCodeDetector
from qr.markers import MarkerStatus, QRMarker, normalize_qr_text
from vision.tracking import MarkerTracker

BACKENDS = ["aruco", "classic"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_le_um_qr(generator, backend):
    scene, centers = make_scene(generator, ["agricultura"])
    markers = QRCodeDetector(backend).detect(scene)
    assert len(markers) == 1
    m = markers[0]
    assert m.element_id == "agricultura"
    assert m.status == MarkerStatus.OK
    assert m.corners.shape == (4, 2)
    cx, cy = m.center
    assert abs(cx - centers[0][0]) < 10 and abs(cy - centers[0][1]) < 10
    x, y, w, h = m.bbox
    assert 150 < w < 230 and 150 < h < 230


@pytest.mark.parametrize("backend", BACKENDS)
def test_multiplos_qr(generator, backend):
    ids = ["agricultura", "pecuaria", "trator"]
    scene, _ = make_scene(generator, ids, qr_px=200)
    found = {m.element_id for m in QRCodeDetector(backend).detect(scene)}
    assert found == set(ids)


def test_qr_inclinado(generator):
    scene, _ = make_scene(generator, ["comercio"], qr_px=240)
    h, w = scene.shape[:2]
    R = cv2.getRotationMatrix2D((w / 2, h / 2), 35, 1.0)
    rotated = cv2.warpAffine(scene, R, (w, h), borderValue=(128, 128, 128))
    markers = QRCodeDetector().detect(rotated)
    assert [m.element_id for m in markers] == ["comercio"]
    # a borda superior do QR acompanha a rotação (-35° no sistema da imagem)
    assert abs(markers[0].angle + 35) < 5


def test_qr_em_perspectiva(generator):
    scene, _ = make_scene(generator, ["industria"], qr_px=260)
    h, w = scene.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[180, 60], [w - 180, 0], [w, h], [0, h - 30]])
    warped = cv2.warpPerspective(scene, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(128, 128, 128))
    markers = QRCodeDetector().detect(warped)
    assert [m.element_id for m in markers] == ["industria"]


def test_imagem_sem_qr():
    assert QRCodeDetector().detect(np.full((480, 640, 3), 200, np.uint8)) == []
    assert QRCodeDetector().detect(np.zeros((0, 0, 3), np.uint8)) == []


def test_detect_scale_retorna_coordenadas_originais(generator):
    scene, centers = make_scene(generator, ["supermercado"], qr_px=300)
    m = QRCodeDetector(detect_scale=0.5).detect(scene)[0]
    assert abs(m.center[0] - centers[0][0]) < 12


def test_qr_com_conteudo_invalido_e_reconhecido_como_invalido():
    qr = qrcode.QRCode(box_size=8, border=4)
    qr.add_data("https://exemplo.com/../../rm -rf")
    img = np.array(qr.make_image().get_image().convert("L"))
    scene = np.full((720, 1280), 128, np.uint8)
    img = cv2.resize(img, (300, 300), interpolation=cv2.INTER_NEAREST)
    scene[200:500, 400:700] = img
    markers = QRCodeDetector().detect(scene)
    assert len(markers) == 1
    assert markers[0].status == MarkerStatus.INVALID
    assert markers[0].element_id is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("agricultura", "agricultura"),
        ("  Meio_Ambiente \n", "meio_ambiente"),
        ("../content/agricultura", None),
        ("rm -rf /", None),
        ("__import__('os').system('dir')", None),
        ("https://exemplo.com", None),
        ("a" * 41, None),
        ("", None),
        (None, None),
    ],
)
def test_validacao_texto_qr(raw, expected):
    assert normalize_qr_text(raw) == expected


def test_gerador_rejeita_id_invalido(generator):
    with pytest.raises(ValueError):
        generator.make_qr("../hack")


def test_marker_ilegivel():
    m = QRMarker.from_detection("", np.float32([[0, 0], [10, 0], [10, 10], [0, 10]]))
    assert m.status == MarkerStatus.UNREADABLE and m.label == "?"


def _marker(text: str, x: float) -> QRMarker:
    return QRMarker.from_detection(text, np.float32([[x, 0], [x + 100, 0], [x + 100, 100], [x, 100]]))


def test_tracker_mantem_marcador_por_alguns_quadros():
    tracker = MarkerTracker(smoothing=0.0, max_missing_frames=2)
    first = tracker.update([_marker("agricultura", 0)], now=0.0)
    track_id = first[0].track_id
    for i in range(2):
        tracks = tracker.update([], now=0.1 * (i + 1))
        assert len(tracks) == 1 and not tracks[0].visible
    assert tracker.update([], now=0.4) == []  # expirou
    # reaparece: novo rastro
    assert tracker.update([_marker("agricultura", 0)], now=0.5)[0].track_id != track_id


def test_tracker_associa_e_suaviza():
    tracker = MarkerTracker(smoothing=0.5)
    tracker.update([_marker("trator", 0), _marker("pecuaria", 500)], now=0)
    tracks = tracker.update([_marker("trator", 20), _marker("pecuaria", 500)], now=0.03)
    by_id = {t.marker.element_id: t for t in tracks}
    assert by_id["trator"].hits == 2
    assert 5 < by_id["trator"].marker.center[0] - 50 < 15  # suavizado (entre 0 e 20)


def test_tracker_qr_ilegivel_mantem_identidade():
    tracker = MarkerTracker(smoothing=0.0)
    tracker.update([_marker("trator", 0)], now=0)
    tracks = tracker.update([_marker("", 5)], now=0.03)
    assert len(tracks) == 1 and tracks[0].marker.element_id == "trator"


def test_tracker_ignora_qr_ilegivel_com_tamanho_incompativel():
    """Regressão: o detector às vezes devolve um QR "ilegível" com cantos
    absurdos (bem maior que o QR real). Ele não pode deformar o rastro
    de um QR conhecido que está perto (cantos reais do modo demo).
    """
    tracker = MarkerTracker(smoothing=0.5)
    real = np.float32([[332, 366], [462, 353], [466, 502], [330, 517]])
    tracker.update([QRMarker.from_detection("pecuaria", real)], now=0)
    bogus = np.float32([[333, 57], [661, 28], [699, 478], [329, 517]])
    tracks = tracker.update([QRMarker.from_detection("", bogus)], now=0.03)
    pecuaria = [t for t in tracks if t.marker.element_id == "pecuaria"]
    assert len(pecuaria) == 1
    np.testing.assert_allclose(pecuaria[0].marker.corners, real)
    assert not pecuaria[0].visible  # não foi visto neste quadro
