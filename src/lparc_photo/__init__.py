"""LPARC Photo: ID photos from a webcam, named by matricule."""

import sys

__version__ = "2.3.0"


def main() -> int:
    if "--self-test" in sys.argv:
        from .selftest import run as self_test

        i = sys.argv.index("--self-test")
        return self_test(sys.argv[i + 1], sys.argv[i + 2])

    from .app import main as run

    return run()
