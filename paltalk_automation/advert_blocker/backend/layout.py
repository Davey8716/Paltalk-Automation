"""Paltalk-window-relative advert layout calculations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Orientation(str, Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class MonitorGeometry:
    left: int
    top: int
    width: int
    height: int

    @property
    def orientation(self) -> Orientation:
        return Orientation.LANDSCAPE if self.width >= self.height else Orientation.PORTRAIT


_BASELINES = {
    Orientation.LANDSCAPE: (1920, 1080, Rect(1620, 240, 300, 640)),
    Orientation.PORTRAIT: (1080, 1920, Rect(246, 88, 833, 94)),
}
_PORTRAIT_X_OFFSET = -10


def scaled_advert_rect(window: Rect) -> Rect:
    """Return the physical-screen advert rectangle within a Paltalk window."""
    orientation = Orientation.LANDSCAPE if window.width >= window.height else Orientation.PORTRAIT
    base_width, base_height, base_rect = _BASELINES[orientation]
    x_scale = window.width / base_width
    y_scale = window.height / base_height
    x_offset = _PORTRAIT_X_OFFSET if orientation is Orientation.PORTRAIT else 0
    return Rect(
        window.x + round(base_rect.x * x_scale) + x_offset,
        window.y + round(base_rect.y * y_scale),
        round(base_rect.width * x_scale),
        round(base_rect.height * y_scale),
    )
