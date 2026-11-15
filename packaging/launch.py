"""PyInstaller entry point (the package's __main__ uses absolute imports, but a plain script keeps this explicit)."""

import sys

from lparc_photo import main

sys.exit(main())
