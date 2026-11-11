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

from core.assets import ANIMATION_EXTS, IMAGE_EXTS, AssetError, resolve_asset

log = logging.getLogger(__name__)

#: Identificadores válidos: letras minúsculas, números e "_" (ex.: meio_ambiente).
ID_PATTERN = re.compile(r"^[a-z0-9_]{1,40}$")
#: Maior id de ArUco aceito no campo "aruco" (os dicionários do OpenCV vão até 1000).
MAX_ARUCO_ID = 999
#: Quantidade de alternativas aceita no quiz (o padrão do projeto é 3).
MIN_ALTERNATIVAS, MAX_ALTERNATIVAS = 2, 4

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
class Quiz:
    """Pergunta de múltipla escolha do modo Missões (versão para celular)."""

    pergunta: str
    alternativas: tuple[str, ...]
    correta: int  # índice da alternativa certa (0 = primeira)
    explicacao: str = ""  # mostrada quando o aluno acerta

    def to_dict(self) -> dict[str, Any]:
        return {
            "pergunta": self.pergunta,
            "alternativas": list(self.alternativas),
            "correta": self.correta,
            "explicacao": self.explicacao,
        }


def parse_mission(missao: Any, quiz: Any) -> tuple[str, Quiz]:
    """Valida o par ``missao`` (pista) + ``quiz``. Os dois são obrigatórios juntos."""
    if not isinstance(missao, str) or not missao.strip():
        raise ContentError("campo 'missao' (a pista) ausente ou vazio")
    if not isinstance(quiz, dict):
        raise ContentError("campo 'quiz' ausente ou não é um objeto {...}")
    pergunta = quiz.get("pergunta")
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise ContentError("quiz: campo 'pergunta' ausente ou vazio")
    alternativas = quiz.get("alternativas")
    if (
        not isinstance(alternativas, list)
        or not MIN_ALTERNATIVAS <= len(alternativas) <= MAX_ALTERNATIVAS
        or not all(isinstance(a, str) and a.strip() for a in alternativas)
    ):
        raise ContentError(
            f"quiz: 'alternativas' deve ser uma lista de {MIN_ALTERNATIVAS} a {MAX_ALTERNATIVAS} textos não vazios"
        )
    correta = quiz.get("correta")
    # bool é subclasse de int em Python: "correta": true não pode virar 1
    if not isinstance(correta, int) or isinstance(correta, bool) or not 0 <= correta < len(alternativas):
        raise ContentError(f"quiz: 'correta' deve ser o número da alternativa certa, de 0 a {len(alternativas) - 1}")
    explicacao = quiz.get("explicacao", "")
    if not isinstance(explicacao, str):
        raise ContentError("quiz: campo 'explicacao' deve ser texto")
    return missao.strip(), Quiz(
        pergunta=pergunta.strip(),
        alternativas=tuple(a.strip() for a in alternativas),
        correta=correta,
        explicacao=explicacao.strip(),
    )


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
    aruco: int | None = None  # id do marcador ArUco colado ao lado do QR (Fase 4)
    missao: str | None = None  # pista do modo Missões ("Encontre o elemento que...")
    quiz: Quiz | None = None
    extras: dict[str, Any] = field(default_factory=dict, compare=False)
    #: Problemas que não impedem o elemento de aparecer (ex.: quiz mal escrito).
    avisos: tuple[str, ...] = field(default=(), compare=False)

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
        aruco = data.get("aruco")
        # bool é subclasse de int em Python: "aruco": true não pode virar 1
        if aruco is not None and (
            not isinstance(aruco, int) or isinstance(aruco, bool) or not 0 <= aruco <= MAX_ARUCO_ID
        ):
            raise ContentError(f"campo 'aruco' deve ser um número inteiro de 0 a {MAX_ARUCO_ID}")
        # Missão com erro não esconde o elemento: só sai do modo Missões, com aviso.
        missao: str | None = None
        quiz: Quiz | None = None
        avisos: list[str] = []
        if "missao" in data or "quiz" in data:
            try:
                missao, quiz = parse_mission(data.get("missao"), data.get("quiz"))
            except ContentError as exc:
                avisos.append(f"missão ignorada: {exc}")
        known = {"id", "titulo", "descricao", "aruco", "missao", "quiz", *optional}
        return cls(
            id=element_id,
            titulo=data["titulo"].strip(),
            descricao=data["descricao"].strip(),
            icone=optional["icone"] or "",
            cor=optional["cor"] or "white",
            imagem=optional["imagem"],
            animacao=optional["animacao"],
            modelo=optional["modelo"],
            aruco=aruco,
            missao=missao,
            quiz=quiz,
            extras={k: v for k, v in data.items() if k not in known},
            avisos=tuple(avisos),
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
        #: id do ArUco -> id do elemento (Fase 4)
        self.aruco_map: dict[int, str] = {}
        self.errors: list[str] = []
        self.load_all()

    def load_all(self) -> int:
        """(Re)carrega todos os conteúdos. Retorna quantos foram carregados."""
        self._items.clear()
        self.aruco_map.clear()
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
            for aviso in item.avisos:
                self._error(f"{path.name}: {aviso}")
            if item.aruco is not None:
                owner = self.aruco_map.setdefault(item.aruco, item.id)
                if owner != item.id:  # o elemento carrega, só o ArUco repetido é ignorado
                    self._error(f"{path.name}: aruco {item.aruco} já é usado por '{owner}' (ignorado)")
            if self.assets_dir is not None:
                self._check_media(path.name, item)
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

    def _check_media(self, file_name: str, item: ElementContent) -> None:
        """Avisa (sem descartar o elemento) se a imagem/animação não puder ser usada."""
        assert self.assets_dir is not None
        for key, value, exts in (("animacao", item.animacao, ANIMATION_EXTS), ("imagem", item.imagem, IMAGE_EXTS)):
            if not value:
                continue
            try:
                resolve_asset(self.assets_dir, value, exts)
            except AssetError as exc:
                self._error(f"{file_name}: {key} {exc} (será ignorada)")

    def _error(self, message: str) -> None:
        self.errors.append(message)
        log.error("Conteúdo: %s", message)
