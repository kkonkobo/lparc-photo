"""LPARC Photo: ID photos from a webcam, named by matricule."""

__version__ = "2.0.0"


def main() -> int:
    from .app import main as run

    return run()
