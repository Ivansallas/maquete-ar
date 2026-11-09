"""Leitura, representação e geração de QR Codes (identificam os elementos)."""

from qr.detector import QRCodeDetector
from qr.markers import MarkerStatus, QRMarker, normalize_qr_text

__all__ = ["QRCodeDetector", "MarkerStatus", "QRMarker", "normalize_qr_text"]
