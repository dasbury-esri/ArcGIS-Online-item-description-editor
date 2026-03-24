from __future__ import annotations

import argparse
import base64
import copy
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_NOTEBOOK = REPO_ROOT / "AGO_Item_Details_Editor.ipynb"
HELPER_FILE = REPO_ROOT / "helper_functions.py"
TOU_FILE = REPO_ROOT / "Esri_ToU.html"
OUTPUT_NOTEBOOK = REPO_ROOT / "Bulk editor for ArcGIS Online Item Details pages.ipynb"


def _load_notebook(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _prepare_helper_source(path: Path) -> str:
    helper_source = path.read_text(encoding="utf-8")
    helper_source, replacements = re.subn(
        r'^OFFICIAL_TOU_HTML_FILE\s*=\s*.+$',
        'OFFICIAL_TOU_HTML_FILE = str((((Path("/arcgis/home") if Path("/arcgis/home").exists() else Path.cwd()) / OUTPUT_DIR_NAME) / "Esri_ToU.html").resolve())',
        helper_source,
        count=1,
        flags=re.MULTILINE,
    )
    if replacements != 1:
        raise RuntimeError("Could not rewrite OFFICIAL_TOU_HTML_FILE in helper_functions.py")
    return helper_source


def _build_bootstrap_lines(helper_source: str, tou_source: str) -> list[str]:
    helper_b64 = base64.b64encode(helper_source.encode("utf-8")).decode("ascii")
    tou_b64 = base64.b64encode(tou_source.encode("utf-8")).decode("ascii")
    helper_chunks = [helper_b64[i:i + 120] for i in range(0, len(helper_b64), 120)]
    tou_chunks = [tou_b64[i:i + 120] for i in range(0, len(tou_b64), 120)]

    lines = [
        "# Bootstrap bundled assets for the portable notebook.",
        "import base64",
        "import sys",
        "from pathlib import Path",
        "",
        "OUTPUT_DIR_NAME = \"notebook_outputs\"",
        "RUNTIME_ROOT = Path(\"/arcgis/home\") if Path(\"/arcgis/home\").exists() else Path.cwd()",
        "RUNTIME_DIR = (RUNTIME_ROOT / OUTPUT_DIR_NAME).resolve()",
        "RUNTIME_DIR.mkdir(parents=True, exist_ok=True)",
        "HELPER_FUNCTIONS_B64 = (",
    ]

    lines.extend([f'    "{chunk}"' for chunk in helper_chunks])
    lines.extend([
        ")",
        "ESRI_TOU_HTML_B64 = (",
    ])
    lines.extend([f'    "{chunk}"' for chunk in tou_chunks])
    lines.extend([
        ")",
        "",
        "BOOTSTRAP_FILES = {",
        "    \"helper_functions.py\": base64.b64decode(HELPER_FUNCTIONS_B64).decode(\"utf-8\"),",
        "    \"Esri_ToU.html\": base64.b64decode(ESRI_TOU_HTML_B64).decode(\"utf-8\"),",
        "}",
        "",
        "for i, (filename, file_text) in enumerate(BOOTSTRAP_FILES.items()):",
        "    target_path = RUNTIME_DIR / filename",
        "    target_path.write_text(file_text, encoding=\"utf-8\")",
        "    print(f\"Bootstrapped asset[{i}]: {target_path}\")",
        "",
        "if str(RUNTIME_DIR) not in sys.path:",
        "    sys.path.insert(0, str(RUNTIME_DIR))",
        "",
        "print(f\"Portable notebook assets are ready in: {RUNTIME_DIR}\")",
        "",
    ])

    return lines


def _find_setup_code_cell_index(cells: list[dict]) -> int:
    """Locate the setup code cell immediately after the setup markdown heading."""
    for idx, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", [])
        source_text = "".join(source) if isinstance(source, list) else str(source)
        if "## 1. Setup and authenticate" not in source_text:
            continue

        for follow_idx in range(idx + 1, len(cells)):
            if cells[follow_idx].get("cell_type") == "code":
                return follow_idx
        break

    raise RuntimeError("Could not locate the setup code cell in the source notebook.")


def _update_setup_cell(cells: list[dict], helper_source: str, tou_source: str) -> None:
    setup_cell = cells[_find_setup_code_cell_index(cells)]
    existing_source = setup_cell["source"]
    bootstrap_lines = _build_bootstrap_lines(helper_source, tou_source)
    if existing_source[: len(bootstrap_lines)] == bootstrap_lines:
        return
    setup_cell["source"] = bootstrap_lines + existing_source


def _normalize_markdown_cell_sources(cells: list[dict]) -> None:
    """Serialize markdown cell sources as single strings with explicit newlines.

    ArcGIS Online notebooks handle markdown more reliably when `source` is a
    single string rather than a list of string fragments.
    """
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", [])
        if isinstance(source, str):
            text = source
            if text and not text.endswith("\n"):
                text = f"{text}\n"
            elif not text:
                text = "\n"
            cell["source"] = text
            continue

        normalized_lines: list[str] = []
        for entry in source:
            text = str(entry)
            if text.endswith("\n"):
                normalized_lines.append(text)
            elif text == "":
                normalized_lines.append("\n")
            else:
                normalized_lines.append(f"{text}\n")
        cell["source"] = "".join(normalized_lines)


def _normalize_code_cell_sources(cells: list[dict]) -> None:
    """Serialize code cell sources with explicit newlines.

    Some notebook runtimes concatenate list-based `source` entries directly.
    Normalizing to a single string with trailing newlines prevents accidental
    line merges (for example, comments and imports being combined).
    """
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", [])
        if isinstance(source, str):
            text = source
            if text and not text.endswith("\n"):
                text = f"{text}\n"
            elif not text:
                text = "\n"
            cell["source"] = text
            continue

        normalized_lines: list[str] = []
        for entry in source:
            text = str(entry)
            if text.endswith("\n"):
                normalized_lines.append(text)
            elif text == "":
                normalized_lines.append("\n")
            else:
                normalized_lines.append(f"{text}\n")
        cell["source"] = "".join(normalized_lines)


def _apply_portable_code_cell_metadata(cells: list[dict]) -> None:
    """Set code cell metadata expected by ArcGIS Online portable notebooks."""
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue

        metadata = cell.setdefault("metadata", {})
        metadata["trusted"] = False

        jupyter_metadata = metadata.get("jupyter")
        if not isinstance(jupyter_metadata, dict):
            jupyter_metadata = {}
            metadata["jupyter"] = jupyter_metadata
        jupyter_metadata["source_hidden"] = True


def _validate_markdown_parity(source_cells: list[dict], portable_cells: list[dict]) -> None:
    if len(source_cells) != len(portable_cells):
        raise RuntimeError("Portable notebook cell count differs from source notebook.")

    for idx, (source_cell, portable_cell) in enumerate(zip(source_cells, portable_cells), start=1):
        source_type = source_cell.get("cell_type")
        portable_type = portable_cell.get("cell_type")
        if source_type != portable_type:
            raise RuntimeError(
                f"Portable notebook cell {idx} type differs from source notebook: "
                f"{source_type!r} != {portable_type!r}"
            )

        if source_type != "markdown":
            continue

        if source_cell.get("source") != portable_cell.get("source"):
            raise RuntimeError(
                f"Portable notebook markdown cell {idx} differs from source notebook. "
                "Source notebook must remain the source of truth."
            )


def build_portable_notebook(source_notebook: Path, output_notebook: Path) -> Path:
    notebook = _load_notebook(source_notebook)
    cells = notebook.get("cells", [])
    if len(cells) < 2:
        raise RuntimeError("Source notebook structure is not what the generator expects.")

    source_reference_cells = copy.deepcopy(cells)

    helper_source = _prepare_helper_source(HELPER_FILE)
    tou_source = TOU_FILE.read_text(encoding="utf-8")

    _update_setup_cell(cells, helper_source, tou_source)
    _apply_portable_code_cell_metadata(cells)
    _normalize_code_cell_sources(cells)
    _normalize_markdown_cell_sources(source_reference_cells)
    _normalize_markdown_cell_sources(cells)
    _validate_markdown_parity(source_reference_cells, cells)

    output_notebook.write_text(json.dumps(notebook, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_notebook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a portable ArcGIS notebook with bundled assets.")
    parser.add_argument("--source", type=Path, default=SOURCE_NOTEBOOK, help="Path to the source notebook.")
    parser.add_argument("--output", type=Path, default=OUTPUT_NOTEBOOK, help="Path to the generated portable notebook.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = build_portable_notebook(args.source.resolve(), args.output.resolve())
    print(f"Generated portable notebook: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())