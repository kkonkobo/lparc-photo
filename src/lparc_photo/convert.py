"""Find photos in a folder and convert them between JPEG and PNG.

A photo's format is read from its content, not its name: a PNG saved as `123.jpg` is reported as
PNG with a mismatched extension, and converting it fixes the name too."""

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .imaging import FORMATS

EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".png"}
PIL_FORMATS = {"JPEG": "jpeg", "MPO": "jpeg", "PNG": "png"}  # MPO: JPEGs from some phone cameras
ORIGINALS_DIR = "avant-conversion"
DEFAULT_DPI = 300


@dataclass(frozen=True)
class Photo:
    path: Path
    format: str  # "jpeg" or "png", from the file's content
    width: int
    height: int
    bytes: int
    dpi: int | None
    has_alpha: bool

    @property
    def extension_matches(self) -> bool:
        return (self.path.suffix.lower() in (".jpg", ".jpeg", ".jpe")) == (self.format == "jpeg")


@dataclass(frozen=True)
class Unreadable:
    path: Path
    reason: str


def scan(folder: Path, recursive: bool = False) -> tuple[list[Photo], list[Unreadable]]:
    """Every JPEG or PNG in `folder`, by name, sorted. Files the conversion itself set aside are skipped."""
    pattern = "**/*" if recursive else "*"
    photos, unreadable = [], []
    for path in sorted(folder.glob(pattern), key=lambda p: str(p).lower()):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS or path.name.startswith("."):
            continue
        if ORIGINALS_DIR in path.relative_to(folder).parts[:-1]:
            continue
        try:
            with Image.open(path) as image:
                fmt = PIL_FORMATS.get(image.format or "")
                if fmt is None:
                    unreadable.append(Unreadable(path, f"format {image.format} non pris en charge"))
                    continue
                dpi = image.info.get("dpi")
                has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
                photos.append(Photo(path, fmt, image.width, image.height, path.stat().st_size,
                                    round(dpi[0]) if dpi and dpi[0] else None, has_alpha))
        except (UnidentifiedImageError, OSError) as error:
            unreadable.append(Unreadable(path, str(error) or "fichier illisible"))
    return photos, unreadable


@dataclass(frozen=True)
class Result:
    source: Path
    target: Path | None
    status: str  # "converted", "skipped" or "failed"
    message: str = ""


def target_path(photo: Photo, fmt: str) -> Path:
    return photo.path.with_suffix(FORMATS[fmt])


def needs_conversion(photo: Photo, fmt: str) -> bool:
    return photo.format != fmt or not photo.extension_matches


def convert(photo: Photo, fmt: str, quality: int = 95, keep_original: bool = True,
            replace_existing: bool = False, discard=None) -> Result:
    """Write `photo` as `fmt` next to it, then set the original aside.

    `keep_original` moves the original into an `avant-conversion` folder beside it; otherwise
    `discard(path)` is called on it (the app sends it to the trash). The same applies to an existing
    file of the target name when `replace_existing` is set. Nothing is touched until the new image
    is fully written to a temporary file."""
    target = target_path(photo, fmt)
    if not needs_conversion(photo, fmt):
        return Result(photo.path, None, "skipped", "déjà au bon format")
    same_file = target == photo.path or (target.exists() and target.samefile(photo.path))
    if target.exists() and not same_file and not replace_existing:
        return Result(photo.path, target, "skipped", f"{target.name} existe déjà")
    tmp = target.with_name(f".{target.name}.convert-tmp")
    try:
        with Image.open(photo.path) as image:
            image.load()
            dpi = photo.dpi or DEFAULT_DPI
            out = _flatten(image) if fmt == "jpeg" else _for_png(image)
        if fmt == "png":
            out.save(tmp, format="PNG", dpi=(dpi, dpi), optimize=True)
        else:
            out.save(tmp, format="JPEG", dpi=(dpi, dpi), quality=quality, subsampling=0, optimize=True)

        def set_aside(path: Path) -> None:
            if keep_original:
                backup_dir = path.parent / ORIGINALS_DIR
                backup_dir.mkdir(exist_ok=True)
                os.replace(path, _free_name(backup_dir / path.name))
            else:
                (discard or os.remove)(path)

        if same_file:
            # e.g. a PNG named 123.jpg becoming a real 123.jpg: the original must move first.
            if keep_original:
                set_aside(photo.path)
            os.replace(tmp, target)
        else:
            if target.exists():  # replace_existing: the file being replaced is set aside, not lost
                set_aside(target)
            os.replace(tmp, target)
            set_aside(photo.path)
    except Exception as error:
        tmp.unlink(missing_ok=True)
        return Result(photo.path, target, "failed", str(error))
    return Result(photo.path, target, "converted")


def _flatten(image: Image.Image) -> Image.Image:
    """JPEG has no transparency: transparent areas become white, like the app's white background."""
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        white = Image.new("RGB", rgba.size, (255, 255, 255))
        white.paste(rgba, mask=rgba.getchannel("A"))
        return white
    return image.convert("RGB")


def _for_png(image: Image.Image) -> Image.Image:
    return image if image.mode in ("RGB", "RGBA", "L", "LA") else image.convert("RGB")


def _free_name(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while (candidate := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return candidate


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo"):
        if n < 1024 or unit == "Mo":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n} o"
