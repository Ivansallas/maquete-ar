"""Testes de integração: câmera (sem hardware), ArUco e o pipeline completo."""

from __future__ import annotations

import json

import cv2
import numpy as np

from app import MaqueteARApp
from ar.renderer import ARRenderer
from camera.camera import CameraManager, FileSource, build_source
from conftest import ROOT, make_scene
from core.config import load_config
from vision.aruco import ArucoDetector
from vision.perspective import marker_homography, project_points, quad_is_valid


def test_arquivo_inexistente_nao_lanca_excecao(tmp_path):
    cam = CameraManager(FileSource(tmp_path / "nao_existe.mp4"), reconnect_interval=999)
    assert cam.open() is False
    assert "não encontrado" in (cam.error or "")
    assert cam.read() is None  # continua respondendo, sem exceção


def test_fonte_imagem_repete_quadro(tmp_path, generator):
    scene, _ = make_scene(generator, ["trator"])
    path = tmp_path / "cena.png"
    cv2.imwrite(str(path), scene)
    cam = CameraManager(FileSource(path))
    assert cam.open()
    assert cam.read().shape == scene.shape
    assert cam.read().shape == scene.shape


def test_build_source():
    cfg = load_config(ROOT / "config.json")["camera"]
    assert build_source(cfg, "demo").description == "modo demonstração"
    assert build_source(cfg, "2").description == "câmera 2"
    assert build_source(cfg, "video.mp4").description == "arquivo video.mp4"


def test_pipeline_completo_com_varios_qr(tmp_path, generator):
    scene, _ = make_scene(generator, ["agricultura", "pecuaria", "codigo_sem_conteudo"], qr_px=200)
    path = tmp_path / "cena.png"
    cv2.imwrite(str(path), scene)
    app = MaqueteARApp(load_config(ROOT / "config.json"), str(path))
    app.camera.open()
    for _ in range(3):
        out = app.next_frame()
    assert out.shape == scene.shape
    assert not np.array_equal(out, scene)  # algo foi desenhado
    ids = {t.marker.element_id for t in app.tracker.tracks}
    assert ids == {"agricultura", "pecuaria", "codigo_sem_conteudo"}
    assert app.stats.detected == 3
    assert app.contents.get("codigo_sem_conteudo") is None  # exibido como "desconhecido"
    app.close()


def test_tela_de_erro():
    img = ARRenderer.message_screen((640, 360), "Câmera indisponível", "Teste de mensagem")
    assert img.shape == (360, 640, 3) and img.std() > 0


def test_aruco_detecta_e_estima_pose():
    det = ArucoDetector("DICT_4X4_50", 0.04)
    marker = det.generate(7, 300)
    scene = np.full((720, 1280), 255, np.uint8)
    scene[200 : 200 + marker.shape[0], 500 : 500 + marker.shape[1]] = marker
    from camera.calibration import CameraCalibration

    calib = CameraCalibration.approximate_for(1280, 720)
    found = det.detect(cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR), calib)
    assert [m.marker_id for m in found] == [7]
    assert found[0].tvec is not None and found[0].distance_m > 0


def test_homografia_projeta_cantos_do_qr():
    corners = np.float32([[100, 100], [200, 110], [210, 220], [90, 200]])
    H = marker_homography(corners)
    proj = project_points(H, [[0, 0], [1, 0], [1, 1], [0, 1]])
    assert np.allclose(proj, corners, atol=1e-3)
    assert quad_is_valid(proj, (720, 1280))
    assert not quad_is_valid(np.float32([[0, 0], [100, 100], [100, 0], [0, 100]]), (720, 1280))


class _FonteQuebrada(FileSource):
    """Fonte que falha com exceções inesperadas (nem CameraError nem cv2.error)."""

    def __init__(self, falha_ao_abrir: bool) -> None:
        super().__init__("quebrada.png")
        self.falha_ao_abrir = falha_ao_abrir

    def open(self) -> None:
        if self.falha_ao_abrir:
            raise PermissionError("arquivo bloqueado por outro programa")

    def read(self) -> np.ndarray | None:
        raise OSError("dispositivo removido")


def test_excecao_inesperada_ao_abrir_nao_derruba(tmp_path):
    cam = CameraManager(_FonteQuebrada(falha_ao_abrir=True), reconnect_interval=999)
    assert cam.open() is False
    assert "bloqueado" in (cam.error or "")


def test_excecao_inesperada_ao_ler_nao_derruba():
    cam = CameraManager(_FonteQuebrada(falha_ao_abrir=False))
    assert cam.open()
    assert cam.read() is None  # conta como leitura falha, sem exceção


def test_calibracao_corrompida_usa_aproximacao(tmp_path):
    from camera.calibration import CameraCalibration

    eye = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    for ruim in ({"width": 0, "height": 720}, {"width": "1280", "height": None}):
        path = tmp_path / "calibration.json"
        path.write_text(json.dumps({"camera_matrix": eye, "dist_coeffs": [0] * 5, **ruim}), encoding="utf-8")
        calib = CameraCalibration.load(path, (1280, 720))
        assert calib.approximate
