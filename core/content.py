"""Gerenciamento do conteúdo educativo (arquivos JSON em ``content/``).

Segurança: o texto lido do QR Code é usado **somente como chave** para
procurar um conteúdo já carregado em memória. Ele nunca é executado e
nunca é usado para montar caminhos de arquivo.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.assets import AssetError, resolve_asset

log = logging.getLogger(__name__)

#: Identificadores válidos: letras minúsculas, números e "_" (ex.: meio_ambiente).
ID_PATTERN = re.compile(r"^[a-z0-9_]{1,40}$")

#: Cores nomeadas aceitas no campo "cor" (valores em BGR, padrão do OpenCV).
COLOR_NAMES: dict[str, tuple[int, int, int]] = {
    "green": (60, 180, 75),
    "darkgreen": (34, 120, 34),
    "brown": (40, 90, 150),
    "orange": (0, 140, 255),
    "gray": (150, 150, 150),
    "blue": (210, 130, 40),
    "red": (60, 60, 220),
    "yellow": (0, 200, 240),
    "purple": (160, 60, 140),
    "cyan": (200, 200, 0),
    "white": (240, 240, 240),
}
DEFAULT_COLOR = COLOR_NAMES["white"]


class ContentError(ValueError):
    """Conteúdo JSON inválido (campo ausente, tipo errado, id inválido...)."""


def parse_color(value: Any) -> tuple[int, int, int]:
    """Converte ``"green"`` ou ``"#RRGGBB"`` em uma tupla BGR."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in COLOR_NAMES:
            return COLOR_NAMES[text]
        if re.fullmatch(r"#[0-9a-f]{6}", text):
            r, g, b = (int(text[i : i + 2], 16) for i in (1, 3, 5))
            return (b, g, r)
    log.warning("Cor inválida %r; usando branco.", value)
    return DEFAULT_COLOR


@dataclass(frozen=True)
class ElementContent:
    """Conteúdo de um elemento da maquete.

    Os campos opcionais ``imagem``, ``animacao`` e ``modelo`` já fazem
    parte do formato para as próximas fases (imagens, animações e 3D).
    """

    id: str
    titulo: str
    descricao: str
    icone: str = ""
    cor: str = "white"
    imagem: str | None = None
    animacao: str | None = None
    modelo: str | None = None
    extras: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def color_bgr(self) -> tuple[int, int, int]:
        return parse_color(self.cor)

    @classmethod
    def from_dict(cls, data: Any, expected_id: str | None = None) -> ElementContent:
        """Valida um dicionário vindo do JSON e cria o conteúdo."""
        if not isinstance(data, dict):
            raise ContentError("o arquivo deve conter um objeto JSON {...}")
        for key in ("id", "titulo", "descricao"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ContentError(f"campo obrigatório '{key}' ausente ou vazio")
        element_id = data["id"].strip()
        if not ID_PATTERN.fullmatch(element_id):
            raise ContentError(f"id inválido '{element_id}' (use a-z, 0-9 e _)")
        if expected_id is not None and element_id != expected_id:
            raise ContentError(f"id '{element_id}' diferente do nome do arquivo '{expected_id}.json'")
        optional: dict[str, str | None] = {}
        for key in ("icone", "cor", "imagem", "animacao", "modelo"):
            value = data.get(key)
            if value is not None and not isinstance(value, str):
                raise ContentError(f"campo '{key}' deve ser texto")
            optional[key] = value
        known = {"id", "titulo", "descricao", *optional}
        return cls(
            id=element_id,
            titulo=data["titulo"].strip(),
            descricao=data["descricao"].strip(),
            icone=optional["icone"] or "",
            cor=optional["cor"] or "white",
            imagem=optional["imagem"],
            animacao=optional["animacao"],
            modelo=optional["modelo"],
            extras={k: v for k, v in data.items() if k not in known},
        )


class ContentManager:
    """Carrega todos os ``*.json`` de uma pasta e responde consultas por id.

    Arquivos com erro não derrubam a aplicação: são ignorados e a mensagem
    fica disponível em :attr:`errors` (e no log).

    Se ``assets_dir`` for informado, a imagem de cada elemento é verificada
    já no carregamento. Imagem ausente/inválida gera um aviso em
    :attr:`errors`, mas o elemento continua disponível (painel só com texto).
    """

    def __init__(self, content_dir: str | Path = "content", assets_dir: str | Path | None = None) -> None:
        self.content_dir = Path(content_dir)
        self.assets_dir = Path(assets_dir) if assets_dir is not None else None
        self._items: dict[str, ElementContent] = {}
        self.errors: list[str] = []
        self.load_all()

    def load_all(self) -> int:
        """(Re)carrega todos os conteúdos. Retorna quantos foram carregados."""
        self._items.clear()
        self.errors.clear()
        if not self.content_dir.is_dir():
            self._error(f"Pasta de conteúdo '{self.content_dir}' não encontrada.")
            return 0
        for path in sorted(self.content_dir.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                item = ElementContent.from_dict(data, expected_id=path.stem)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ContentError) as exc:
                self._error(f"{path.name}: {exc}")
                continue
            self._items[item.id] = item
            if item.imagem and self.assets_dir is not None:
                try:
                    resolve_asset(self.assets_dir, item.imagem)
                except AssetError as exc:
                    self._error(f"{path.name}: imagem {exc} (painel será exibido só com texto)")
        log.info("%d conteúdos carregados de '%s'.", len(self._items), self.content_dir)
        return len(self._items)

    def get(self, element_id: str | None) -> ElementContent | None:
        """Retorna o conteúdo do elemento ou ``None`` se for desconhecido."""
        if element_id is None:
            return None
        return self._items.get(element_id)

    def __contains__(self, element_id: object) -> bool:
        return element_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    @property
    def ids(self) -> list[str]:
        return sorted(self._items)

    def _error(self, message: str) -> None:
        self.errors.append(message)
        log.error("Conteúdo: %s", message)
