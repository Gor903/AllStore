"""Prints the OpenAPI schema without starting a server.

Used by CI to regenerate frontend types and fail when the committed ones drift.
"""

import json
import sys

from app.main import create_app


def main() -> int:
    schema = create_app().openapi()
    json.dump(schema, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
