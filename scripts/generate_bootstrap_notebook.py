from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_NOTEBOOK = REPO_ROOT / "AGO_Item_Description_Editor.ipynb"
HELPER_FILE = REPO_ROOT / "helper_functions.py"
TOU_FILE = REPO_ROOT / "Esri_ToU.html"
OUTPUT_NOTEBOOK = REPO_ROOT / "Bulk editor for ArcGIS Online Item Description pages.ipynb"


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

    return [
        "# Bootstrap bundled assets for the portable notebook.",
        "import base64",
        "import sys",
        "from pathlib import Path",
        "",
        "OUTPUT_DIR_NAME = \"notebook_outputs\"",
        "RUNTIME_ROOT = Path(\"/arcgis/home\") if Path(\"/arcgis/home\").exists() else Path.cwd()",
        "RUNTIME_DIR = (RUNTIME_ROOT / OUTPUT_DIR_NAME).resolve()",
        "RUNTIME_DIR.mkdir(parents=True, exist_ok=True)",
        f"HELPER_FUNCTIONS_B64 = \"{helper_b64}\"",
        f"ESRI_TOU_HTML_B64 = \"{tou_b64}\"",
        "",
        "BOOTSTRAP_FILES = {",
        "    \"helper_functions.py\": base64.b64decode(HELPER_FUNCTIONS_B64).decode(\"utf-8\"),",
        "    \"Esri_ToU.html\": base64.b64decode(ESRI_TOU_HTML_B64).decode(\"utf-8\"),",
        "}",
        "",
        "for filename, file_text in BOOTSTRAP_FILES.items():",
        "    target_path = RUNTIME_DIR / filename",
        "    target_path.write_text(file_text, encoding=\"utf-8\")",
        "    print(f\"Bootstrapped asset: {target_path}\")",
        "",
        "if str(RUNTIME_DIR) not in sys.path:",
        "    sys.path.insert(0, str(RUNTIME_DIR))",
        "",
        "print(f\"Portable notebook assets are ready in: {RUNTIME_DIR}\")",
        "",
    ]


def _update_intro_markdown(cells: list[dict]) -> None:
    cells[0]["source"] = ["# Bulk editor for ArcGIS Online Item Description pages"]
    cells[1]["source"] = [
        "**Welcome!**  ",
        "This portable notebook helps you scan, review, and update ArcGIS Online items at scale. It focuses on the Terms of Use section, stored in the `licenseInfo` field, and looks for target text or HTML that you want to replace.",
        "",
        "This version bundles `helper_functions.py` and `Esri_ToU.html` into the notebook and writes them into the runtime automatically during Step 1.",
        "",
        "**Where this notebook can run**  ",
        "- ArcGIS Online Notebook (JupyterLab-style).",
        "- VS Code on macOS with a local Jupyter kernel.",
        "- VS Code on Windows with a local Jupyter kernel.",
        "",
        "**How to use this notebook**  ",
        "- Start with **1. Setup and authenticate** to write the bundled files and connect to your organization.",
        "- Run **2. Scan your content** to find matching terms.",
        "- Save the scan outputs, optionally run a secondary scan, and review exact matches if needed.",
        "- Build a **dry-run plan** to see exactly what would change before anything is updated.",
        "- Use the dry-run output to create an HTML review report for side-by-side comparison.",
        "- Commit updates only after you have reviewed the dry-run and report outputs.",
        "",
        "**Notes**  ",
        "- Organization-wide scans can take time, especially in large orgs, so progress messages are shown as users are processed.",
        "- The workflow is designed to be safe by default: review first, then update.",
        "- If you need to restart, restart the kernel and begin again at Step 1 so the bundled files are written again.",
        "- In ArcGIS Online, you can use **View > Collapse All Code** for a cleaner, more user-friendly layout.",
    ]
    cells[4]["source"] = [
        "## 1. Setup and authenticate",
        "Write the bundled helper files into the runtime, then initialize the notebook environment and connect to ArcGIS Online.",
    ]


def _update_setup_cell(cells: list[dict], helper_source: str, tou_source: str) -> None:
    setup_cell = cells[5]
    existing_source = setup_cell["source"]
    setup_cell["source"] = _build_bootstrap_lines(helper_source, tou_source) + existing_source


def build_portable_notebook(source_notebook: Path, output_notebook: Path) -> Path:
    notebook = _load_notebook(source_notebook)
    cells = notebook.get("cells", [])
    if len(cells) < 6:
        raise RuntimeError("Source notebook structure is not what the generator expects.")

    helper_source = _prepare_helper_source(HELPER_FILE)
    tou_source = TOU_FILE.read_text(encoding="utf-8")

    _update_intro_markdown(cells)
    _update_setup_cell(cells, helper_source, tou_source)

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