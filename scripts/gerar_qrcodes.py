"""Gera os QR Codes de todos os elementos cadastrados em ``content/``.

Uso:
    python scripts/gerar_qrcodes.py            # um PNG por elemento + folha A4
    python scripts/gerar_qrcodes.py --cm 4     # QRs de 4 cm na folha A4

Saída (pasta qrcodes/):
    agricultura.png, pecuaria.png, ...   QR individual com legenda
    folha_impressao_A4.png               todos os QRs em tamanho real (300 dpi)
    demo_maquete.png                     "maquete virtual" para testes sem câmera
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from ar.overlay import configure_console_utf8  # noqa: E402
from core.config import load_config  # noqa: E402
from core.content import ContentManager  # noqa: E402
from qr.generator import QRCodeGenerator, build_demo_board, make_print_sheets, qr_payload  # noqa: E402


def main() -> int:
    configure_console_utf8()
    parser = argparse.ArgumentParser(description="Gera os QR Codes da maquete")
    parser.add_argument("--out", type=Path, default=ROOT / "qrcodes", help="pasta de saída")
    parser.add_argument("--cm", type=float, default=5.0, help="lado de cada QR na folha A4 (cm)")
    args = parser.parse_args()

    contents = ContentManager(ROOT / "content")
    for err in contents.errors:
        print(f"[aviso] {err}")
    if not len(contents):
        print("Nenhum conteúdo válido em content/. Nada a gerar.")
        return 1

    config = load_config(ROOT / "config.json")
    base_url = config["web"]["url"]  # versão celular: QR com link do site
    if base_url:
        print(f"QR Codes com link para o site: {base_url}")
    else:
        print('Aviso: "web.url" vazio no config.json -> QR sem link (o celular não abrirá o site).')
    gen = QRCodeGenerator()
    items = [(cid, contents.get(cid).titulo) for cid in contents.ids]  # type: ignore[union-attr]
    for cid, titulo in items:
        path = gen.save(cid, args.out, label=titulo, payload=qr_payload(cid, base_url))
        print(f"  ✔ {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    # Fase 4: o ArUco de cada elemento sai ao lado do QR, no tamanho do config.json
    aruco_ids = {element: marker for marker, element in contents.aruco_map.items()}
    aruco_cm = float(config["aruco"]["marker_length_m"]) * 100
    sheets = make_print_sheets(items, gen, qr_cm=args.cm, aruco_ids=aruco_ids, aruco_cm=aruco_cm, base_url=base_url)
    for old in args.out.glob("folha_impressao_A4*.png"):  # remove folhas de uma geração anterior
        old.unlink()
    for n, sheet in enumerate(sheets, start=1):
        sheet_path = args.out / ("folha_impressao_A4.png" if n == 1 else f"folha_impressao_A4_{n}.png")
        sheet.save(sheet_path, dpi=(300, 300))
        print(f"  ✔ {sheet_path.name}")
    print("    imprima em 100% ('tamanho real') e cole cada ArUco junto do seu QR, no mesmo plano")

    board = build_demo_board(items, aruco_ids=aruco_ids)
    ok, buf = cv2.imencode(".png", board)
    if ok:
        buf.tofile(str(args.out / "demo_maquete.png"))
        print("  ✔ demo_maquete.png (teste: python app.py --source qrcodes/demo_maquete.png)")
    print(f"\n{len(items)} QR Codes gerados em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
