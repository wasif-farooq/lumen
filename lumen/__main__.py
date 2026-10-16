"""`python -m lumen`: the same as the `lumen` command."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
