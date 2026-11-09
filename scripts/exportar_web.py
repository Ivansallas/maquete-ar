"""Monta o site da versão para celular (pasta pronta para publicar).

Junta as páginas de ``web/`` com o conteúdo de ``content/*.json`` e só as
imagens/animações de ``assets/`` que os elementos usam (validadas pelas
mesmas regras do programa do PC). O professor não precisa rodar isto: a
publicação no GitHub Pages roda automaticamente a cada ``git push``
(``.github/workflows/site.yml``).

Uso:
    python scripts/exportar_web.py                 # gera em build/web/
    python scripts/exportar_web.py --out _site

Para testar no PC (a câmera funciona em http://localhost):
    python -m http.server -d build/web 8000
    -> abra http://localhost:8000/            (webcam)
    -> ou  http://localhost:8000/?teste=1     (maquete virtual, sem câmera)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from core.assets import ANIMATION_EXTS, IMAGE_EXTS, AssetError, resolve_asset  # noqa: E402
from core.content import ContentManager, ElementContent  # noqa: E402
from qr.generator import build_demo_board  # noqa: E402

WEB_DIR = ROOT / "web"
#: Arquivos de web/ que não vão para o site (testes e configuração do Node).
NOT_PUBLISHED = {"tests", "package.json"}


def export_site(
    out: Path,
    content_dir: Path = ROOT / "content",
    assets_dir: Path = ROOT / "assets",
) -> list[str]:
    """Gera o site em ``out`` (apagando o que havia). Retorna os avisos."""
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out, ignore=lambda _d, names: [n for n in names if n in NOT_PUBLISHED])
    (out / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: servir os arquivos como estão

    contents = ContentManager(content_dir, assets_dir=assets_dir)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    elements = {cid: _element(item, Path(assets_dir), data_dir) for cid in contents.ids if (item := contents.get(cid))}
    payload = {
        "elementos": elements,
        "aruco": {str(marker): element for marker, element in sorted(contents.aruco_map.items())},
    }
    (data_dir / "conteudo.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # imagem da "maquete virtual" para o modo ?teste=1 (sem câmera)
    aruco_ids = {element: marker for marker, element in contents.aruco_map.items()}
    board = build_demo_board([(cid, cid) for cid in contents.ids[:8]], aruco_ids=aruco_ids)
    ok, buf = cv2.imencode(".png", board)
    if ok:
        buf.tofile(str(data_dir / "teste.png"))
    return list(contents.errors)


def _element(item: ElementContent, assets_dir: Path, data_dir: Path) -> dict[str, object]:
    return {
        "titulo": item.titulo,
        "descricao": item.descricao,
        "icone": item.icone,
        "cor": "#{2:02x}{1:02x}{0:02x}".format(*item.color_bgr),  # BGR -> #rrggbb
        "aruco": item.aruco,
        "imagem": _copy_media(item.imagem, IMAGE_EXTS, assets_dir, data_dir),
        "animacao": _copy_media(item.animacao, ANIMATION_EXTS, assets_dir, data_dir),
    }


def _copy_media(relative: str | None, exts: set[str], assets_dir: Path, data_dir: Path) -> str | None:
    """Copia o arquivo validado para ``data/assets/...`` e devolve o caminho do site."""
    if not relative:
        return None
    try:
        src = resolve_asset(assets_dir, relative, exts)  # dentro de assets/, extensão permitida
    except AssetError:
        return None  # já avisado pelo ContentManager; o painel fica sem a mídia
    rel = src.relative_to(Path(assets_dir).resolve()).as_posix()
    dst = data_dir / "assets" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"data/assets/{rel}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o site da versão para celular")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "web", help="pasta de saída")
    args = parser.parse_args()
    warnings = export_site(args.out)
    for w in warnings:
        print(f"[aviso] {w}")
    print(f"Site gerado em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
