#!/usr/bin/env python3
"""List and upload files to ArcGIS notebook workspace data access endpoints.

This utility targets notebook workspace data access endpoints that support:
- GET  {workspace_url}?restype=container&comp=list&f=pjson&token=...
- POST {workspace_url}/uploadFile (multipart form data)

Typical workspace URL pattern:
https://<org-host>/<context>/notebooks/admin/dataaccess/notebookworkspace
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

try:
	import keyring
except ImportError:  # Optional dependency for token generation.
	keyring = None

DEFAULT_SHORT_ORG = "www"
DEFAULT_KEYRING_SERVICE = "arcgis-online"


class HelpfulArgumentParser(argparse.ArgumentParser):
	"""Argparse parser that shows full help text before parse errors."""

	def error(self, message: str) -> None:
		self.print_help(sys.stderr)
		self.exit(2, f"\n{self.prog}: error: {message}\n")

def prompt_for_auth_context(
		default_short_org: str = DEFAULT_SHORT_ORG,
		default_username: str = "",
) -> Tuple[str, str]:
	short_org = input(
		f"Enter ArcGIS Online org name (default: {default_short_org}): "
	).strip()
	if not short_org:
		short_org = default_short_org

	username_prompt = "ArcGIS Online username"
	if default_username:
		username_prompt += f" [{default_username}]"
	username_prompt += ": "

	username = input(username_prompt).strip()
	if not username:
		username = default_username

	if not username:
		raise RuntimeError("Username is required.")
	
	return short_org, username


def prompt_for_item_id() -> str:
	item_id = input("Enter ArcGIS Online notebook item ID: ").strip()
	if not item_id:
		raise RuntimeError("Item ID is required.")
	return item_id


def get_default_username_from_keyring(service: str) -> str:
	if keyring is None:
		return ""

	get_credential = getattr(keyring, "get_credential", None)
	if callable(get_credential):
		try:
			credential = get_credential(service, None)
			username = getattr(credential, "username", None)
			if isinstance(username, str) and username:
				return username
		except Exception:
			return ""

	return ""

def short_org_to_url(short_org: str) -> str:
    short_org = short_org.strip().lower()
    if not short_org:
        raise RuntimeError("Short org name is required.")
    if short_org == "www":
        return "https://www.arcgis.com"
    return f"https://{short_org}.maps.arcgis.com"


def get_password_from_keyring(service: str, username: str) -> str:
	if keyring is None:
		raise RuntimeError("keyring is not installed. Install it with: pip install keyring")

	password = keyring.get_password(service, username)
	if not password:
		raise RuntimeError(
			f"No password found in keyring for service='{service}' username='{username}'"
		)
	return password


def _normalize_workspace_url(url: str) -> str:
	return url.rstrip("/")


def _normalize_org_url(url: str) -> str:
	return url.rstrip("/")


def _join_url(base: str, *parts: str) -> str:
	cleaned = [p.strip("/") for p in parts if p is not None and p.strip("/")]
	return "/".join([base.rstrip("/")] + cleaned)


def construct_workspace_url(
	org_url: str,
	item_id: str,
	route: str,
	context_path: str,
) -> str:
	base = _normalize_org_url(org_url)
	item = item_id.strip()
	context = context_path.strip("/")

	if route == "admin-dataaccess-item":
		if context:
			return _join_url(base, context, "notebooks/admin/dataaccess/items", item, "notebookworkspace")
		return _join_url(base, "notebooks/admin/dataaccess/items", item, "notebookworkspace")

	if route == "sharing-rest-item":
		return _join_url(base, "sharing/rest/content/items", item, "notebookworkspace")

	raise ValueError(f"Unsupported route: {route}")


def _candidate_workspace_urls(org_url: str, item_id: str, context_path: str) -> List[str]:
	base = _normalize_org_url(org_url)
	context = context_path.strip("/")
	item = item_id.strip()

	candidates: List[str] = []
	if context:
		candidates.append(
			_join_url(base, context, "notebooks/admin/dataaccess/items", item, "notebookworkspace")
		)
		candidates.append(_join_url(base, context, "notebooks/admin/dataaccess/notebookworkspace"))

	candidates.append(_join_url(base, "notebooks/admin/dataaccess/items", item, "notebookworkspace"))
	candidates.append(_join_url(base, "notebooks/admin/dataaccess/notebookworkspace"))
	candidates.append(_join_url(base, "sharing/rest/content/items", item, "notebookworkspace"))

	# Preserve order and remove accidental duplicates.
	seen = set()
	ordered: List[str] = []
	for url in candidates:
		if url not in seen:
			seen.add(url)
			ordered.append(url)
	return ordered


def resolve_workspace_url(
	org_url: str,
	item_id: str,
	token: str,
	timeout: int,
	route: str,
	context_path: str,
	probe: bool,
) -> str:
	if route in {"admin-dataaccess-item", "sharing-rest-item"}:
		return construct_workspace_url(org_url, item_id, route, context_path)

	if route != "auto":
		raise ValueError(f"Unsupported route: {route}")

	candidates = _candidate_workspace_urls(org_url, item_id, context_path)
	if not probe:
		return candidates[0]

	for candidate in candidates:
		try:
			list_workspace_blobs(candidate, token, timeout)
			return candidate
		except Exception:
			continue

	raise RuntimeError(
		"Unable to resolve a working notebookworkspace endpoint automatically. "
		"Use --workspace-url to provide the exact endpoint."
	)


def generate_arcgis_token(
	org_url: str,
	username: str,
	password: str,
	timeout: int,
	expiration_minutes: int,
) -> str:
	token_url = _join_url(_normalize_org_url(org_url), "sharing/rest/generateToken")
	payload = {
		"f": "pjson",
		"username": username,
		"password": password,
		"client": "referer",
		"referer": _normalize_org_url(org_url),
		"expiration": str(expiration_minutes),
	}

	response = requests.post(token_url, data=payload, timeout=timeout)
	response.raise_for_status()
	body: Dict[str, Any] = response.json()

	if "error" in body:
		raise RuntimeError(json.dumps(body["error"], indent=2))

	token = (body.get("token") or "").strip()
	if not token:
		raise RuntimeError("Token response did not include 'token'.")
	return token


def list_workspace_blobs(workspace_url: str, token: str, timeout: int) -> List[str]:
	params = {
		"restype": "container",
		"comp": "list",
		"f": "pjson",
		"token": token,
	}
	response = requests.get(workspace_url, params=params, timeout=timeout)
	response.raise_for_status()
	payload: Dict[str, Any] = response.json()

	if "error" in payload:
		raise RuntimeError(json.dumps(payload["error"], indent=2))

	blobs = payload.get("Blobs") or []
	names = [
		name
		for b in blobs
		for name in [b.get("Name") if isinstance(b, dict) else None]
		if isinstance(name, str) and name
	]
	return sorted(names)


def upload_file(
	workspace_url: str,
	token: str,
	local_file: Path,
	remote_name: str,
	timeout: int,
) -> Dict[str, Any]:
	upload_url = f"{workspace_url}/uploadFile"

	form_data = {
		"fileName": remote_name,
		"f": "pjson",
		"token": token,
	}

	# ArcGIS expects multipart form-data for file uploads.
	with local_file.open("rb") as handle:
		files = {
			"uploadFile": (local_file.name, handle, "application/x-ipynb+json"),
		}
		response = requests.post(upload_url, data=form_data, files=files, timeout=timeout)

	response.raise_for_status()
	payload: Dict[str, Any] = response.json()

	if "error" in payload:
		raise RuntimeError(json.dumps(payload["error"], indent=2))

	return payload


def build_parser() -> argparse.ArgumentParser:
	parser = HelpfulArgumentParser(
		description=(
			"List and upload notebook workspace files using ArcGIS data access API. "
			"Default UX is interactive: run this script with no auth flags and it will "
			"prompt for org name, username, and notebook item ID."
		),
		epilog=(
			"Examples:\n"
			"  python scripts/ago_sync_notebook.py list\n"
			"    Starts interactive prompts for missing org/user/item values.\n"
			"  python scripts/ago_sync_notebook.py --workspace-url <url> --token <token> list\n"
			"    Non-interactive mode for automation."
		),
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument(
		"--workspace-url",
		help=(
			"Base notebookworkspace endpoint, e.g. "
			"https://<host>/<context>/notebooks/admin/dataaccess/notebookworkspace"
		),
	)
	parser.add_argument(
		"--org-url",
		default="",
		help=(
			"ArcGIS org base URL used for auto endpoint construction. "
			"If omitted, interactive mode prompts for short org name."
		),
	)
	parser.add_argument(
		"--item-id",
		default="",
		help=(
			"ArcGIS notebook item ID used for auto endpoint construction. "
			"If omitted and --workspace-url is not set, interactive mode prompts for it."
		),
	)
	parser.add_argument(
		"--route",
		choices=["auto", "admin-dataaccess-item", "sharing-rest-item"],
		default="auto",
		help="Endpoint route strategy for auto construction (default: auto).",
	)
	parser.add_argument(
		"--context-path",
		default="arcgis",
		help="Context path segment for admin-dataaccess routes (default: arcgis).",
	)
	parser.add_argument(
		"--no-probe",
		action="store_true",
		help="Disable automatic endpoint probing and use first constructed candidate.",
	)
	parser.add_argument(
		"--token",
		default=os.environ.get("ARCGIS_TOKEN", ""),
		help=(
			"ArcGIS token. If omitted, reads ARCGIS_TOKEN env var. "
			"If still missing, interactive keyring-based token generation is used."
		),
	)
	parser.add_argument(
		"--use-keyring",
		action="store_true",
		help="Generate token via keyring-stored credentials when --token is not provided.",
	)
	parser.add_argument(
		"--keyring-service",
		default="arcgis-online",
		help="Keyring service name (default: arcgis-online).",
	)
	parser.add_argument(
		"--keyring-username",
		default="",
		help=(
			"Username to look up in keyring for token generation. "
			"If omitted, interactive mode prompts and pre-fills with a keyring default when available."
		),
	)
	parser.add_argument(
		"--token-expiration-minutes",
		type=int,
		default=60,
		help="Requested token lifetime in minutes for keyring-generated tokens.",
	)
	parser.add_argument(
		"--timeout",
		type=int,
		default=60,
		help="HTTP timeout in seconds (default: 60).",
	)

	subparsers = parser.add_subparsers(dest="command", required=True)
	subparsers.add_parser("resolve", help="Resolve and print notebookworkspace endpoint.")

	subparsers.add_parser("list", help="List files in notebook workspace.")

	upload_parser = subparsers.add_parser(
		"upload", help="Upload local file and overwrite when remote name already exists."
	)
	upload_parser.add_argument(
		"--local-file",
		required=True,
		help="Path to local file to upload.",
	)
	upload_parser.add_argument(
		"--remote-name",
		default="",
		help="Destination filename in notebook workspace. Defaults to local filename.",
	)
	upload_parser.add_argument(
		"--verify",
		action="store_true",
		help="List workspace after upload and verify remote filename exists.",
	)

	return parser


def main() -> int:
	parser = build_parser()
	if len(sys.argv) == 1:
		parser.print_help()
		return 0
	args = parser.parse_args()

	token = (args.token or "").strip()
	org_url = (args.org_url or "").strip()
	item_id = (args.item_id or "").strip()

	# Interactive auth mode: if token wasn't provided, prompt for org and username,
	# then read password from keyring and generate token.
	if not token:
		default_short_org = DEFAULT_SHORT_ORG
		if org_url:
			normalized_org = _normalize_org_url(org_url)
			if normalized_org == "https://www.arcgis.com":
				default_short_org = "www"
			elif normalized_org.endswith(".maps.arcgis.com"):
				host = normalized_org.split("//", 1)[-1]
				default_short_org = host.split(".", 1)[0]

		default_username = (args.keyring_username or "").strip() or get_default_username_from_keyring(
			args.keyring_service
		)

		short_org, username = prompt_for_auth_context(
			default_short_org=default_short_org,
			default_username=default_username,
		)
		org_url = short_org_to_url(short_org)

		password = get_password_from_keyring(args.keyring_service, username)
		token = generate_arcgis_token(
			org_url=org_url,
			username=username,
			password=password,
			timeout=args.timeout,
			expiration_minutes=args.token_expiration_minutes,
		)

	if not token:
		parser.error("Token is required via --token or ARCGIS_TOKEN environment variable.")

	if args.workspace_url:
		workspace_url = _normalize_workspace_url(args.workspace_url)
	else:
		if not item_id:
			item_id = prompt_for_item_id()

		if not org_url:
			parser.error("Org URL is required to resolve workspace URL.")

		workspace_url = resolve_workspace_url(
			org_url=org_url,
			item_id=item_id,
			token=token,
			timeout=args.timeout,
			route=args.route,
			context_path=args.context_path,
			probe=not args.no_probe,
		)

	try:
		if args.command == "resolve":
			print(json.dumps({"workspace_url": workspace_url}, indent=2))
			return 0

		if args.command == "list":
			names = list_workspace_blobs(workspace_url, token, args.timeout)
			print(
				json.dumps(
					{"workspace_url": workspace_url, "count": len(names), "files": names},
					indent=2,
				)
			)
			return 0

		if args.command == "upload":
			local_file = Path(args.local_file).expanduser().resolve()
			if not local_file.exists() or not local_file.is_file():
				parser.error(f"Local file not found: {local_file}")

			remote_name = (args.remote_name or local_file.name).strip()
			if not remote_name:
				parser.error("Remote name resolved to empty string.")

			result = upload_file(
				workspace_url=workspace_url,
				token=token,
				local_file=local_file,
				remote_name=remote_name,
				timeout=args.timeout,
			)
			output: Dict[str, Any] = {
				"workspace_url": workspace_url,
				"uploaded": str(local_file),
				"remote_name": remote_name,
				"response": result,
			}

			if args.verify:
				names = list_workspace_blobs(workspace_url, token, args.timeout)
				output["verify_exists"] = remote_name in names
				output["workspace_count"] = len(names)

			print(json.dumps(output, indent=2))
			return 0

		parser.error(f"Unsupported command: {args.command}")
		return 2

	except requests.HTTPError as exc:
		response = exc.response
		details = {
			"status_code": response.status_code if response is not None else None,
			"response_text": response.text[:2000] if response is not None else None,
		}
		print(json.dumps({"error": "HTTP request failed", "details": details}, indent=2), file=sys.stderr)
		return 1
	except Exception as exc:  # pragma: no cover - defensive for CLI runtime
		print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
