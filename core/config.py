"""Carregamento do arquivo ``config.json`` com valores padrão seguros.

Qualquer chave ausente no arquivo é preenchida com o valor padrão, então
o ``config.json`` pode conter apenas o que se deseja alterar.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "camera": {
        "index": 0,  # índice da webcam (0 = primeira câmera)
        "source": None,  # opcional: caminho de imagem/vídeo ou "demo"
        "width": 1280,
        "height": 720,
        "fps": 30,
        "backend": "auto",  # auto | dshow | msmf | v4l2 | any
        "mirror": False,  # espelhar a imagem (útil com webcam frontal)
        "reconnect_interval": 2.0,
    },
    "debug": True,
    "qr": {
        "backend": "auto",  # auto | aruco | classic
        "detect_scale": 0.75,  # < 1.0 reduz a imagem antes de detectar (mais FPS)
    },
    "tracking": {
        "smoothing": 0.5,  # 0 = sem suavização, 0.9 = muito suave
        "max_missing_frames": 10,  # quadros que o painel "sobrevive" sem o QR
    },
    "ar": {
        "enabled": True,
        "mode": "perspective",  # perspective | billboard
        "panel_width": 3.2,  # largura do painel em "lados do QR"
        "panel_gap": 0.25,  # distância entre QR e painel (lados do QR)
        "min_panel_width_px": 260,  # abaixo disso usa painel plano (legível)
        "panel_opacity": 0.9,
        "max_panels": 3,  # painéis simultâneos (0 = todos)
        "fade_in_seconds": 0.3,
    },
    "aruco": {
        "enabled": True,
        "dictionary": "DICT_4X4_50",
        "marker_length_m": 0.03,  # lado do marcador impresso, em metros
    },
    "window": {"title": "Maquete AR", "fullscreen": False},
    # Versão para celular: endereço HTTPS do site (ex.: GitHub Pages). Com ele,
    # os QR Codes gerados levam o link "<url>/?e=<id>".
    "web": {"url": None},
    "paths": {
        "content": "content",
        "assets": "assets",  # imagens (Fase 2) do campo "imagem"
        "screenshots": "screenshots",
        "calibration": "camera/calibration.json",
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Retorna uma cópia de ``base`` com os valores de ``override`` aplicados."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path = "config.json") -> dict[str, Any]:
    """Lê o arquivo de configuração. Em caso de erro, usa os valores padrão.

    A aplicação nunca deve deixar de abrir por causa de um ``config.json``
    ausente ou mal formatado: o problema é registrado no log e a execução
    continua com a configuração padrão.
    """
    path = Path(path)
    if not path.exists():
        log.warning("Arquivo de configuração '%s' não encontrado; usando padrões.", path)
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with path.open(encoding="utf-8") as fh:
            user_cfg = json.load(fh)
        if not isinstance(user_cfg, dict):
            raise ValueError("o conteúdo deve ser um objeto JSON")
    except (OSError, ValueError) as exc:
        log.error("Erro ao ler '%s' (%s); usando configuração padrão.", path, exc)
        return copy.deepcopy(DEFAULT_CONFIG)
    return deep_merge(DEFAULT_CONFIG, user_cfg)
