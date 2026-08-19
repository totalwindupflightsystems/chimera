"""Module entry point — enables ``python -m chimera`` (CH-GAP-035).

Delegates to the click CLI so ``python -m chimera --help`` behaves exactly
like the ``chimera`` console script, and users without the script on PATH
(fresh clone, non-activated venv) still have an escape hatch.
"""

from chimera.cli.main import main

if __name__ == "__main__":
    main()
