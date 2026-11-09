"""Testes da Fase 3: animações (GIF/WebP/APNG) dentro dos painéis."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from ar.animations import FadeIn, FadeOut, Pulse
from ar.objects import AnimatedPanel, ARObjectFactory, ImagePanel, RenderContext, TextPanel
from core.assets import ANIMATION_EXTS, AnimatedImage, AssetError, load_animation, resolve_asset
from core.content import ContentManager, ElementContent
from qr.markers import QRMarker

RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]


def save_gif(path, colors=RGB, size=(120, 80), duration=100, **kw) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = [Image.new("RGB", size, c) for c in colors]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=duration, loop=0, **kw)


@pytest.fixture
def assets(tmp_path):
    root = tmp_path / "assets"
    save_gif(root / "animations" / "cores.gif")
    save_gif(root / "animations" / "rapido.gif", duration=0)  # duração 0 = navegador usa 100 ms
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (60, 40), (255, 0, 0)).save(root / "images" / "foto.png")
    (root / "animations" / "quebrada.gif").write_bytes(b"GIF89a lixo")
    return root


def content(animacao: str | None = None, imagem: str | None = None) -> ElementContent:
    data = {"id": "trator", "titulo": "Trator", "descricao": "Máquina agrícola.", "animacao": animacao}
    if imagem:
        data["imagem"] = imagem
    return ElementContent.from_dict(data)


# --------------------------------------------------------------- carga
def test_load_animation_le_quadros_e_duracoes(assets):
    clip = load_animation(assets / "animations" / "cores.gif")
    assert len(clip.frames) == 3
    assert clip.durations == pytest.approx([0.1, 0.1, 0.1])
    assert all(f.shape == (80, 120, 4) and f.dtype == np.uint8 for f in clip.frames)
    assert clip.frames[1][0, 0, :3].tolist() == [0, 255, 0]  # BGR do verde


def test_duracao_zero_vira_padrao(assets):
    clip = load_animation(assets / "animations" / "rapido.gif")
    assert min(clip.durations) >= 0.02


def test_frame_index_em_loop():
    clip = AnimatedImage(frames=[np.zeros((2, 2, 4), np.uint8)] * 3, durations=[0.1, 0.2, 0.1])
    assert [clip.frame_index(t) for t in (0, 0.05, 0.1, 0.29, 0.3, 0.39, 0.4, 0.45)] == [0, 0, 1, 1, 2, 2, 0, 0]
    assert clip.frame_index(-1.0) == 0


def test_load_animation_limita_memoria(assets):
    clip = load_animation(assets / "animations" / "cores.gif", max_bytes=120 * 80 * 4 * 2)
    assert len(clip.frames) == 2  # para quando o orçamento acaba (o loop fica mais curto)


def test_load_animation_reduz_quadros_grandes(tmp_path):
    save_gif(tmp_path / "grande.gif", size=(2000, 1000))
    clip = load_animation(tmp_path / "grande.gif", max_side=500)
    assert clip.frames[0].shape[:2] == (250, 500)


def test_load_animation_corrompida(assets):
    with pytest.raises(AssetError):
        load_animation(assets / "animations" / "quebrada.gif")


def test_png_estatico_vira_animacao_de_um_quadro(assets):
    clip = load_animation(assets / "images" / "foto.png")
    assert len(clip.frames) == 1


def test_extensoes_de_animacao():
    assert {".gif", ".webp", ".png"} <= ANIMATION_EXTS


def test_resolve_animacao_rejeita_extensao_de_video(assets):
    (assets / "animations" / "filme.mp4").write_bytes(b"x")
    with pytest.raises(AssetError):
        resolve_asset(assets, "animations/filme.mp4", ANIMATION_EXTS)


# --------------------------------------------------------------- painel animado
def _render(obj, elapsed: float) -> np.ndarray:
    frame = np.zeros((720, 1280, 3), np.uint8)
    marker = QRMarker.from_detection("trator", np.float32([[560, 450], [720, 450], [720, 610], [560, 610]]))
    assert obj.render(frame, marker, RenderContext(elapsed=elapsed, opacity=1.0)) is not None
    return frame


def _dominant(frame: np.ndarray) -> int:
    """Canal BGR mais forte entre pixels quase puros (0=azul, 1=verde, 2=vermelho)."""
    counts = [int(((frame[:, :, c] > 200) & (frame.sum(axis=2) < 300)).sum()) for c in range(3)]
    return int(np.argmax(counts))


def test_painel_animado_troca_de_quadro_com_o_tempo(assets):
    obj = ARObjectFactory(assets_dir=assets).get(content("animations/cores.gif"))
    assert isinstance(obj, AnimatedPanel)
    assert _dominant(_render(obj, 0.0)) == 2  # vermelho
    assert _dominant(_render(obj, 0.15)) == 1  # verde
    assert _dominant(_render(obj, 0.25)) == 0  # azul
    assert _dominant(_render(obj, 0.35)) == 2  # recomeça


def test_painel_animado_mantem_tamanho_entre_quadros(assets):
    obj = ARObjectFactory(assets_dir=assets).get(content("animations/cores.gif"))
    assert isinstance(obj, AnimatedPanel)
    shapes = set()
    for t in (0.0, 0.15, 0.25):
        _render(obj, t)
        shapes.add(obj.image.shape)
    assert len(shapes) == 1


def test_animacao_tem_prioridade_sobre_imagem(assets):
    obj = ARObjectFactory(assets_dir=assets).get(content("animations/cores.gif", "images/foto.png"))
    assert isinstance(obj, AnimatedPanel)


@pytest.mark.parametrize(
    ("animacao", "imagem", "esperado"),
    [
        ("animations/quebrada.gif", "images/foto.png", ImagePanel),
        ("animations/nao_existe.gif", None, TextPanel),
        ("../fora.gif", None, TextPanel),
    ],
)
def test_animacao_com_problema_cai_para_imagem_ou_texto(assets, animacao, imagem, esperado):
    obj = ARObjectFactory(assets_dir=assets).get(content(animacao, imagem))
    assert type(obj) is esperado


def test_content_manager_avisa_animacao_ausente(tmp_path, assets):
    folder = tmp_path / "content"
    folder.mkdir()
    data = {"id": "trator", "titulo": "Trator", "descricao": "d", "animacao": "animations/sumiu.gif"}
    (folder / "trator.json").write_text(json.dumps(data), encoding="utf-8")
    cm = ContentManager(folder, assets_dir=assets)
    assert cm.ids == ["trator"]
    assert len(cm.errors) == 1 and "animacao" in cm.errors[0]


# --------------------------------------------------------------- efeitos de tempo
def test_efeitos_de_tempo():
    assert FadeIn(0.3).value(0) == 0 and FadeIn(0.3).value(1) == 1
    assert FadeOut(1).value(0.5) == pytest.approx(0.5)
    assert 0.4 <= Pulse(1.0, 0.4).value(0.75) <= 1.0
