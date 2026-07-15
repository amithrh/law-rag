#!/usr/bin/env python3
"""Assert an installed wheel can load its embedded authority manifests."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    if not args.wheel.exists():
        raise SystemExit(f"wheel not found: {args.wheel}")
    expected = "authority_registry/migrations/0001_crpc_436a.json"
    with zipfile.ZipFile(args.wheel) as archive:
        if expected not in archive.namelist():
            raise SystemExit(f"wheel is missing {expected}")
    sys.path.insert(0, str(args.wheel))
    from authority_registry import load_authority_registry  # noqa: PLC0415

    registry = load_authority_registry()
    record = registry.by_key("crpc_1973_section_436a")
    if record is None or record.authority_id_expected != "authority_348b7d2511bb3e5a2618":
        raise SystemExit("wheel registry did not resolve the CrPC 436A authority")
    print(f"wheel registry ok: {record.canonical_key}")


if __name__ == "__main__":
    main()
