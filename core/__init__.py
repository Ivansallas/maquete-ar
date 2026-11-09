"""Núcleo da aplicação: configuração e gerenciamento de conteúdo."""

from core.config import DEFAULT_CONFIG, load_config
from core.content import ContentError, ContentManager, ElementContent, parse_color

__all__ = [
    "DEFAULT_CONFIG",
    "load_config",
    "ContentError",
    "ContentManager",
    "ElementContent",
    "parse_color",
]
