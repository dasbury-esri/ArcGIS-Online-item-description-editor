from __future__ import annotations

import argparse
import base64
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
    ])

    return lines


def _update_intro_markdown(cells: list[dict]) -> None:
    cells[0]["source"] = ["# Bulk editor for ArcGIS Online Item Details pages"]
    cells[1]["source"] = [
        "**Welcome!**  ",
        "",
        "This notebook helps you scan, review, and update ArcGIS Online items at scale. It focuses on the Terms of Use section, stored in the `licenseInfo` field, and looks for text or HTML that you may want to replace.",
        "",
        "This version bundles `helper_functions.py` and `Esri_ToU.html` template directly into the notebook, so when running Step 1 those files will be expanded into a new folder and saved into `/arcgis/home/notebook_outputs`. You will be able to modify both input and output files as you progress. A review webpage is produced that lets you see what will change before you make any edits, and you can selectively choose to edit items from the report.",
        "",
        "*** BE CAUTIOUS WITH ANY TOOL LIKE THIS THAT BULK EDITS ITEMS *** However, you will have plenty of chances to review the work before commiting any changes.",
        "",
        "**Where this notebook can run**  ",
        "- ArcGIS Online Notebook (JupyterLab-style).",
        "- VS Code on macOS with a local Jupyter kernel.",
        "- VS Code on Windows with a local Jupyter kernel.",
        "",
        "**How to use this notebook**  ",
        " - Click on the text \"Setup and authenticate\" below. ",
        " - There are two types of cells, Markdown (formatted notes) and Code.",
        " - An indicator -- typically a vertical blue line -- should highlight that you have selected the \"Setup and authenticate\" Markdown cell.",
        " - Once selected, click the \"Play\" button in the toolbar above to run the cell and advance to the next Code cell.",
        " - Click the \"Play\" button a second time to run the code cell.",
        " - After several seconds a \"Setup Notebook\" button should appear. Click the button to begin setup and authentication.",
        " - After each cell completes, click the text within the following Markdown cell.",
        " - Click the \"Play\" button to advance to the Code cell, then click the \"Play\" button a second time to make a button appear.",
        " - Click the button to run the code in the cell. ",
        "",
        "**Notes**  ",
        "- Organization-wide scans can take time, especially in large orgs, so progress messages are shown as users are processed.",
        "- You can monitor the status of long running cells by viewing the small circle in the top right of the page.",
        "- If you click on a code cell it will expand showing you the behind-the-scenes Python code.",
        "- For a cleaner interface select View > Collapse All Code in the menu bar above to hide the code .",
        "- If at any point you get stuck and want to start over, just click Kernel > Restart Kernel and Clear Outputs of All Cells... in the menu bar",
        "- The workflow is designed to be safe by default: review first, then update.",
    ]
    cells[4]["source"] = [
        "## 1. Setup and authenticate",
        "Write the bundled helper files into the runtime, then initialize the notebook environment and connect to ArcGIS Online.",
    ]


def _update_setup_cell(cells: list[dict], helper_source: str, tou_source: str) -> None:
    setup_cell = cells[5]
    existing_source = setup_cell["source"]
    setup_cell["source"] = _build_bootstrap_lines(helper_source, tou_source) + existing_source


def _normalize_markdown_cell_sources(cells: list[dict]) -> None:
    """Ensure markdown cells have explicit newlines between logical lines.

    ArcGIS notebook rendering can collapse list-of-string markdown sources when
    lines are not newline-terminated.
    """
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", [])
        if isinstance(source, str):
            lines = source.splitlines(keepends=True)
            if not lines:
                lines = ["\n"]
            elif not lines[-1].endswith("\n"):
                lines[-1] = f"{lines[-1]}\n"
            cell["source"] = lines
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
        cell["source"] = normalized_lines


def build_portable_notebook(source_notebook: Path, output_notebook: Path) -> Path:
    notebook = _load_notebook(source_notebook)
    cells = notebook.get("cells", [])
    if len(cells) < 6:
        raise RuntimeError("Source notebook structure is not what the generator expects.")

    helper_source = _prepare_helper_source(HELPER_FILE)
    tou_source = TOU_FILE.read_text(encoding="utf-8")

    _update_intro_markdown(cells)
    _update_setup_cell(cells, helper_source, tou_source)
    _normalize_markdown_cell_sources(cells)

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