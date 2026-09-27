#!/usr/bin/env python3
"""Vendor Swagger UI's static assets into app/static/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

DEFAULT_BASE_URL = "https://cdn.jsdelivr.net/npm"

ASSETS: list[tuple[str, str, int]] = [
    ("swagger-ui-dist", "swagger-ui-bundle.js", 500_000),
    ("swagger-ui-dist", "swagger-ui.css", 50_000),
    ("redoc", "bundles/redoc.standalone.js", 500_000),
]

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


def fetch(base_url: str, package: str, path: str, minimum: int) -> bytes:
    version = "5" if package == "swagger-ui-dist" else "2"
    url = f"{base_url}/{package}@{version}/{path}"
    name = path.rsplit("/", 1)[-1]
    print(f"  GET {url}")

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    payload = response.content

    if len(payload) < minimum:
        raise RuntimeError(
            f"{name} came back at {len(payload):,} bytes, below the expected "
            f"{minimum:,}. This is usually a proxy interstitial or error page "
            f"returned with a 200 status, not the real asset."
        )

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="npm registry or mirror to pull from (e.g. an internal Nexus).",
    )
    args = parser.parse_args()

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Vendoring Swagger UI {args.version} into {STATIC_DIR}")

    try:
        downloaded = {
            path.rsplit("/", 1)[-1]: fetch(args.base_url, package, path, minimum)
            for package, path, minimum in ASSETS
        }
    except Exception as exc:  # noqa: BLE001
        print(f"\nFailed: {exc}", file=sys.stderr)
        print(
            "\nIf this host cannot reach the CDN, pass --base-url pointing at "
            "an internal npm mirror, or copy the files across manually (see "
            "this script's docstring).",
            file=sys.stderr,
        )
        return 1

    for name, payload in downloaded.items():
        (STATIC_DIR / name).write_bytes(payload)
        print(f"  wrote {name} ({len(payload):,} bytes)")

    print("\nDone. Restart the backend and reload http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
