"""Output size presets and unit conversion."""

from dataclasses import dataclass

MM_PER_INCH = 25.4


def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, round(mm / MM_PER_INCH * dpi))


def px_to_mm(px: int, dpi: int) -> float:
    return px / dpi * MM_PER_INCH


@dataclass(frozen=True)
class OutputSize:
    width_px: int
    height_px: int
    dpi: int

    @property
    def aspect(self) -> float:
        return self.width_px / self.height_px

    def describe(self) -> str:
        w_mm = px_to_mm(self.width_px, self.dpi)
        h_mm = px_to_mm(self.height_px, self.dpi)
        return f"{self.width_px} × {self.height_px} px · {w_mm:.0f} × {h_mm:.0f} mm à {self.dpi} dpi"


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    size: OutputSize | None  # None means "custom"


PRESETS: list[Preset] = [
    # 413 × 532 is what V1.2 produced: 35 × 45 mm at 300 dpi.
    Preset("lparc", "LPARC 35 × 45 mm · 300 dpi", OutputSize(413, 532, 300)),
    Preset("id600", "Photo d'identité 35 × 45 mm · 600 dpi", OutputSize(mm_to_px(35, 600), mm_to_px(45, 600), 600)),
    Preset("badge", "Badge 30 × 40 mm · 300 dpi", OutputSize(mm_to_px(30, 300), mm_to_px(40, 300), 300)),
    Preset("square", "Carré 600 × 600 px", OutputSize(600, 600, 300)),
    Preset("custom", "Personnalisé…", None),
]

DEFAULT_PRESET = "lparc"


def preset_by_key(key: str) -> Preset:
    for preset in PRESETS:
        if preset.key == key:
            return preset
    return preset_by_key(DEFAULT_PRESET)
