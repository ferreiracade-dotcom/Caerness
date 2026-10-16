"""Print the CAERNESS_PASSPHRASE_HASH line for the env file. The passphrase is read from a prompt, never argv."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connector.oauth import hash_passphrase  # noqa: E402

MIN_LENGTH = 12


def build_line(passphrase: str) -> str:
    if len(passphrase) < MIN_LENGTH:
        raise ValueError(f"the passphrase must be at least {MIN_LENGTH} characters")
    return f"CAERNESS_PASSPHRASE_HASH={hash_passphrase(passphrase)}"


def main() -> int:
    first = getpass.getpass("Passphrase: ")
    if getpass.getpass("Again: ") != first:
        print("The two entries differ.", file=sys.stderr)
        return 1
    try:
        print(build_line(first))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
