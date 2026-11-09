"""Captura de vídeo (webcam, arquivos, demonstração) e calibração."""

from camera.calibration import CameraCalibration
from camera.camera import (
    CameraError,
    CameraManager,
    DemoSource,
    DeviceSource,
    FileSource,
    FrameSource,
    build_source,
)

__all__ = [
    "CameraCalibration",
    "CameraError",
    "CameraManager",
    "DemoSource",
    "DeviceSource",
    "FileSource",
    "FrameSource",
    "build_source",
]
