"""Porte de validation backend en une seule commande.

Usage : uv run python scripts/validate.py
"""

import subprocess
import sys

COMMANDS: list[list[str]] = [
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
    ["uv", "run", "mypy", "app", "migrations", "tests", "scripts"],
    ["uv", "run", "pytest"],
]


def main() -> int:
    for command in COMMANDS:
        print(f"$ {' '.join(command)}")
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
