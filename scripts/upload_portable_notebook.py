#!/usr/bin/env python3
"""Upload and overwrite an ArcGIS Online Notebook item's .ipynb data.

This script updates item data via the ArcGIS Sharing REST endpoint:
POST /sharing/rest/content/users/{owner}/items/{itemId}/update

It is intentionally small and focused on replacing a notebook item's content
with a local portable .ipynb file.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Dict

import requests

try:
    import keyring
except ImportError:
    keyring = None

DEFAULT_ITEM_ID = "f3c7cf3d068e479f97e97fce818dea46"
DEFAULT_FILE = "Bulk editor for ArcGIS Online Item Details pages.ipynb"
DEFAULT_SHORT_ORG = "www"
DEFAULT_KEYRING_SERVICE = "system"


def short_org_to_url(short_org: str) -> str:
    short_org = (short_org or "").strip().lower()
    if not short_org:
        raise RuntimeError("Org short name is required.")
    if short_org == "www":
        return "https://www.arcgis.com"
    return f"https://{short_org}.maps.arcgis.com"


def get_password(service: str, username: str) -> str:
    if keyring is not None:
        password = keyring.get_password(service, username)
        if password:
            return password

    # Fallback if keyring entry is missing or keyring package is unavailable.
    password = getpass.getpass(f"ArcGIS Online password for '{username}': ").strip()
    if not password:
        raise RuntimeError("Password is required.")

    if keyring is not None:
        choice = input(
            f"Save password to keyring service '{service}' for username '{username}'? [y/N]: "
        ).strip().lower()
        if choice in {"y", "yes"}:
            keyring.set_password(service, username, password)
            print("Saved password to keyring.")

    return password


def generate_token(org_url: str, username: str, password: str, timeout: int) -> str:
    token_url = "https://www.arcgis.com/sharing/rest/generateToken"
    payload = {
        "f": "pjson",
        "username": username,
        "password": password,
        "client": "referer",
        "referer": org_url,
        "expiration": "60",
    }
    response = requests.post(token_url, data=payload, timeout=timeout)
    response.raise_for_status()
    body: Dict[str, Any] = response.json()

    if "error" in body:
        raise RuntimeError(json.dumps(body["error"], indent=2))

    token = (body.get("token") or "").strip()
    if not token:
        raise RuntimeError("Token response did not include token.")
    return token


def get_item_metadata(item_id: str, token: str, timeout: int) -> Dict[str, Any]:
    url = f"https://www.arcgis.com/sharing/rest/content/items/{item_id}"
    response = requests.get(url, params={"f": "pjson", "token": token}, timeout=timeout)
    response.raise_for_status()
    body: Dict[str, Any] = response.json()
    if "error" in body:
        raise RuntimeError(json.dumps(body["error"], indent=2))
    return body


def get_item_data(item_id: str, token: str, timeout: int) -> Dict[str, Any]:
    url = f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
    response = requests.get(url, params={"f": "pjson", "token": token}, timeout=timeout)
    response.raise_for_status()
    body: Dict[str, Any] = response.json()
    if "error" in body:
        raise RuntimeError(json.dumps(body["error"], indent=2))
    return body


def update_item_data(owner: str, item_id: str, token: str, local_file: Path, timeout: int) -> Dict[str, Any]:
    url = f"https://www.arcgis.com/sharing/rest/content/users/{owner}/items/{item_id}/update"
    form = {"f": "pjson", "token": token}

    with local_file.open("rb") as fp:
        files = {"file": (local_file.name, fp, "application/x-ipynb+json")}
        response = requests.post(url, data=form, files=files, timeout=timeout)

    response.raise_for_status()
    body: Dict[str, Any] = response.json()
    if "error" in body:
        raise RuntimeError(json.dumps(body["error"], indent=2))
    return body


def summarize_notebook_data(notebook_data: Dict[str, Any]) -> Dict[str, Any]:
    cells = notebook_data.get("cells", [])
    setup_cell = None
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", [])
        source_lines = source if isinstance(source, list) else [source]
        if any("Cell 1. Import packages" in str(line) for line in source_lines):
            setup_cell = cell
            break

    if setup_cell is None:
        return {
            "cell_count": len(cells),
            "setup_cell_found": False,
        }

    source = setup_cell.get("source", [])
    lines = [str(line).rstrip("\n") for line in source] if isinstance(source, list) else str(source).splitlines()
    return {
        "cell_count": len(cells),
        "setup_cell_found": True,
        "setup_line_count": len(lines),
        "setup_first_line": lines[0] if lines else "",
        "setup_line_50": lines[49] if len(lines) >= 50 else "",
        "contains_bootstrap_files": any("BOOTSTRAP_FILES" in line for line in lines),
        "contains_find_helper_dir": any("def _find_helper_dir" in line for line in lines),
        "contains_recreated_missing_asset": any(
            "Recreated missing bundled asset" in line for line in lines
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Overwrite an ArcGIS Online Notebook item with a local .ipynb file."
    )
    parser.add_argument("--item-id", default=DEFAULT_ITEM_ID, help="Notebook item ID to update.")
    parser.add_argument(
        "--file",
        default=DEFAULT_FILE,
        help="Local .ipynb file path to upload (default: portable notebook in repo root).",
    )
    parser.add_argument(
        "--org-short",
        default=DEFAULT_SHORT_ORG,
        help="ArcGIS Online org short name (default: www).",
    )
    parser.add_argument("--username", default="", help="ArcGIS Online username for auth.")
    parser.add_argument("--token", default="", help="Optional pre-generated token.")
    parser.add_argument(
        "--keyring-service",
        default=DEFAULT_KEYRING_SERVICE,
        help="Keyring service label (default: system).",
    )
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    item_id = (args.item_id or "").strip()
    if not item_id:
        parser.error("--item-id is required")

    local_file = Path(args.file).expanduser().resolve()
    if not local_file.exists() or not local_file.is_file():
        parser.error(f"Local file not found: {local_file}")

    org_url = short_org_to_url(args.org_short)
    token = (args.token or "").strip()

    if not token:
        username = (args.username or "").strip()
        if not username:
            username = input("ArcGIS Online username: ").strip()
        if not username:
            raise RuntimeError("Username is required.")

        password = get_password(args.keyring_service, username)
        token = generate_token(org_url, username, password, args.timeout)

    item = get_item_metadata(item_id, token, args.timeout)
    owner = (item.get("owner") or "").strip()
    if not owner:
        raise RuntimeError("Item metadata did not include owner.")

    local_notebook_data = json.loads(local_file.read_text(encoding="utf-8"))
    local_summary = summarize_notebook_data(local_notebook_data)
    result = update_item_data(owner, item_id, token, local_file, args.timeout)
    live_notebook_data = get_item_data(item_id, token, args.timeout)
    live_summary = summarize_notebook_data(live_notebook_data)

    print(
        json.dumps(
            {
                "item_id": item_id,
                "title": item.get("title"),
                "owner": owner,
                "uploaded_file": str(local_file),
                "update_result": result,
                "local_notebook_summary": local_summary,
                "live_notebook_summary": live_summary,
                "live_matches_local_summary": live_summary == local_summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
