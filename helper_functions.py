# ======================================================================
# Helper functions for AGO Item Details Editor notebook
# ======================================================================

import os, sys, re, uuid, json, math, tempfile, requests, traceback, base64, ast, csv, io, threading
import ipywidgets as widgets # type: ignore
from IPython.display import display, HTML
from pathlib import Path
import arcgis, time, re
from arcgis.gis import GIS
import pandas as pd
from html import escape
from datetime import datetime
from urllib.parse import urlparse, quote
from contextlib import redirect_stdout

# ======================================================================
# Shared notebook runtime context configured from the notebook setup cell.
# ======================================================================

_RUNTIME_CONTEXT = None

def set_runtime_context(context):
    """Register the notebook context dictionary used by button callbacks."""
    global _RUNTIME_CONTEXT
    _RUNTIME_CONTEXT = context

def _ctx():
    if _RUNTIME_CONTEXT is None:
        raise RuntimeError("Runtime context is not configured. Run setup cell first.")
    return _RUNTIME_CONTEXT

# ======================================================================
# Environment and Paths
# ======================================================================

def detect_environment():
    """
    Prints the current running environment and returns a string identifier.
    """
    import os
    # VS Code
    if os.environ.get("VSCODE_PID"):
        DEV_ENV = os.environ.get("VSCODE_PID") is not None
        return "vscode", "VSCode Notebook environment"
    # ArcGIS Online Notebooks
    if "arcgis" in os.environ.get("NB_USER", ""):
        return "arcgisnotebook", "ArcGIS Notebook environment"
    # Jupyter Lab
    if os.environ.get("JPY_PARENT_PID"):
        return "jupyterlab", "Jupyter Lab Notebook environment"
    # Classic Jupyter Notebook
    return "classicjupyter", "classic Jupyter environment"

current_env, env_string = detect_environment()

OUTPUT_DIR_NAME = "notebook_outputs"


def _default_output_root():
    if current_env == "arcgisnotebook" and Path("/arcgis/home").exists():
        return Path("/arcgis/home")
    # Keep local test artifacts under a dedicated hidden folder.
    return Path.cwd() / ".local_testing"


DEFAULT_OUTPUT_DIR = (_default_output_root() / OUTPUT_DIR_NAME).resolve()
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Backward-compatible alias for older notebook code that referenced BASE_DIR.
BASE_DIR = DEFAULT_OUTPUT_DIR


def get_output_dir(context=None):
    active_context = context if context is not None else _RUNTIME_CONTEXT
    configured_dir = None
    if active_context:
        configured_dir = active_context.get("output_dir")

    output_dir = Path(configured_dir).expanduser() if configured_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir.resolve()


def default_output_dir_str():
    return str(get_output_dir())


def default_output_path_str(filename):
    return str((get_output_dir() / filename).resolve())


def resolve_output_path(filename_or_path, default_filename):
    raw_value = str(filename_or_path or "").strip()
    target_path = Path(raw_value if raw_value else default_filename).expanduser()
    if not target_path.is_absolute():
        target_path = get_output_dir() / target_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return target_path.resolve()


def resolve_existing_input_path(filename_or_path):
    raw_value = str(filename_or_path or "").strip()
    if not raw_value:
        return None

    candidate = Path(raw_value).expanduser()
    candidates = [candidate] if candidate.is_absolute() else [Path.cwd() / candidate, get_output_dir() / candidate]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return None


def build_notebook_file_link(path, label, as_button=False):
    resolved_path = Path(path).resolve()
    href = resolved_path.as_uri()

    try:
        relative_path = resolved_path.relative_to(Path.cwd())
    except ValueError:
        relative_path = None

    if current_env in {"arcgisnotebook", "jupyterlab", "classicjupyter"}:
        # Use an absolute files route to avoid cwd-dependent broken links like
        # /files/home/... when runtime cwd is /arcgis.
        href = f"/files{quote(resolved_path.as_posix(), safe='/')}"

    safe_href = escape(href, quote=True)
    safe_label = escape(label)

    if as_button:
        return (
            f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer" '
            'style="display:inline-block; padding:8px 12px; border-radius:6px; '
            'background:#e8f2ff; border:1px solid #bfd8ff; color:#1558a6; '
            'text-decoration:none; font-weight:600; font-size:13px;">'
            f'{safe_label}</a>'
        )

    return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_label}</a>'


def display_embedded_html_report(report_path, *, height_px=760, output_widget=None, max_inline_bytes=2 * 1024 * 1024):
    """Render a generated HTML report inline in the notebook output area.

    Falls back gracefully when the report file cannot be read.
    """
    resolved = Path(report_path).resolve()
    if not resolved.exists():
        if output_widget is not None:
            output_widget.append_stdout(f"Report file not found for embedding: {resolved}\n")
        else:
            print(f"Report file not found for embedding: {resolved}")
        return False

    try:
        report_html = resolved.read_text(encoding="utf-8")
    except Exception as exc:
        if output_widget is not None:
            output_widget.append_stdout(f"Could not read report for inline display: {exc}\n")
        else:
            print(f"Could not read report for inline display: {exc}")
        return False

    report_size_bytes = len(report_html.encode("utf-8"))
    if max_inline_bytes is not None and report_size_bytes > int(max_inline_bytes):
        if output_widget is not None:
            output_widget.append_stdout(
                "Inline preview skipped because the report is too large "
                f"({report_size_bytes / (1024 * 1024):.2f} MB > {int(max_inline_bytes) / (1024 * 1024):.2f} MB limit).\n"
            )
        else:
            print(
                "Inline preview skipped because the report is too large "
                f"({report_size_bytes / (1024 * 1024):.2f} MB > {int(max_inline_bytes) / (1024 * 1024):.2f} MB limit)."
            )
        return False

    encoded = base64.b64encode(report_html.encode("utf-8")).decode("ascii")
    iframe_markup = (
        f'<iframe src="data:text/html;charset=utf-8;base64,{encoded}" '
        f'style="width:100%; height:{int(height_px)}px; border:1px solid #d0d7de; border-radius:6px; '
        'background:#fff;" loading="lazy"></iframe>'
    )
    if output_widget is not None:
        output_widget.append_display_data(HTML(iframe_markup))
    else:
        display(HTML(iframe_markup))
    return True


def _build_inline_html_iframe(html_text, *, height_px=320):
    """Build an iframe that renders an arbitrary HTML fragment inline."""
    safe_html = html_text if html_text and str(html_text).strip() else "<div style='color:#6b7280;'>No HTML available.</div>"
    document_html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:Arial,sans-serif;margin:16px;line-height:1.5;word-break:break-word;}"
        "img{max-width:100%;height:auto;}table{max-width:100%;}</style>"
        "</head><body>"
        f"{safe_html}"
        "</body></html>"
    )
    encoded = base64.b64encode(document_html.encode("utf-8")).decode("ascii")
    return (
        f'<iframe src="data:text/html;charset=utf-8;base64,{encoded}" '
        f'style="width:100%; height:{int(height_px)}px; border:1px solid #d0d7de; border-radius:6px; '
        'background:#fff;" loading="lazy"></iframe>'
    )


def _extract_tou_match_fragment(html_text, *, strict_match=False):
    """Return the first ToU block matched by the current replacement regex."""
    source_html = "" if html_text is None else str(html_text)
    if not source_html:
        return ""

    matcher = STRICT_TOU_BLOCK_RE if strict_match else TOU_BLOCK_RE
    match = matcher.search(source_html)
    return match.group(0) if match else ""


def display_dry_run_iframe_preview(
    output_widget,
    *,
    matched_html,
    replacement_html,
    item_title="",
    item_id="",
    item_owner="",
    item_type="",
    matched_terms="",
    replacements_found="",
    strict_match=False,
):
    """Render a report-style dry-run preview card for the current matching mode."""
    if output_widget is None:
        raise RuntimeError("A notebook output widget is required for iframe preview rendering.")

    mode_label = "Strict" if strict_match else "Default semi-greedy"
    matched_iframe = _build_inline_html_iframe(matched_html, height_px=320)
    replacement_iframe = _build_inline_html_iframe(replacement_html, height_px=320)

    info_rows = []
    for label, value in [
        ("Preview mode", mode_label),
        ("Item", item_id),
        ("Title", item_title),
        ("Owner", item_owner),
        ("Type", item_type),
        ("Matched", matched_terms),
        ("Replacements", replacements_found),
    ]:
        if value is not None and str(value).strip():
            info_rows.append(f"<div><strong>{escape(label)}:</strong> {escape(str(value))}</div>")

    markup = f"""
    <div style="margin-top:12px; border:1px solid #d0d7de; border-radius:10px; background:#ffffff; overflow:hidden;">
        <div style="padding:14px 16px; background:#f6f8fa; border-bottom:1px solid #d0d7de;">
            <div style="font-weight:700; margin-bottom:6px;">Preview of the first updatable row</div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:6px 16px; font-size:13px; color:#374151;">
                {''.join(info_rows)}
            </div>
        </div>
        <div style="padding:16px; display:grid; grid-template-columns:repeat(auto-fit, minmax(340px, 1fr)); gap:16px; align-items:start;">
            <div style="border:1px solid #d0d7de; border-radius:8px; padding:12px; background:#fbfbfc;">
                <div style="font-weight:600; margin-bottom:8px;">Matched HTML block</div>
                {matched_iframe}
                <details style="margin-top:10px;">
                    <summary style="cursor:pointer; font-weight:600;">Matched source</summary>
                    <pre style="margin-top:8px; white-space:pre-wrap; word-break:break-word; max-height:220px; overflow:auto; background:#ffffff; border:1px solid #d0d7de; border-radius:6px; padding:10px;">{escape(matched_html or '')}</pre>
                </details>
            </div>
            <div style="border:1px solid #d0d7de; border-radius:8px; padding:12px; background:#fbfbfc;">
                <div style="font-weight:600; margin-bottom:8px;">Replacement HTML</div>
                {replacement_iframe}
                <details style="margin-top:10px;">
                    <summary style="cursor:pointer; font-weight:600;">Replacement source</summary>
                    <pre style="margin-top:8px; white-space:pre-wrap; word-break:break-word; max-height:220px; overflow:auto; background:#ffffff; border:1px solid #d0d7de; border-radius:6px; padding:10px;">{escape(replacement_html or '')}</pre>
                </details>
            </div>
        </div>
    </div>
    """
    output_widget.append_display_data(HTML(markup))


def count_phrase(count, singular, plural=None):
    if count == 1:
        noun = singular
    elif plural:
        noun = plural
    elif singular.endswith(("s", "x", "z", "ch", "sh")):
        noun = f"{singular}es"
    elif len(singular) > 1 and singular.endswith("y") and singular[-2].lower() not in "aeiou":
        noun = f"{singular[:-1]}ies"
    else:
        noun = f"{singular}s"
    return f"{count} {noun}"


def _empty_output_message(label):
    messages = {
        "Matches CSV": "0 matches found.",
        "Errors CSV": "0 reported errors.",
        "All items CSV": "0 all-items rows available.",
        "Success CSV": "0 successful updates.",
    }
    return messages.get(label, f"{label}: 0 rows.")

# ======================================================================
# Authentication for different environments
# ======================================================================

def authenticate_gis(context, portal_url="https://www.arcgis.com", client_id=None, output_widget=None):
    """
    Authenticate to ArcGIS Online or Enterprise. Falls back to username/password
    """
    import ipywidgets as widgets # type: ignore
    from IPython.display import display
    from arcgis.gis import GIS # type: ignore

    def _emit(line):
        if output_widget is not None:
            output_widget.append_stdout(f"{line}\n")
        else:
            print(line)

    auth_container = context.get("auth_container")

    def _emit_widget(widget):
        if auth_container is not None:
            auth_container.children = (widget,)
        elif output_widget is not None:
            output_widget.append_display_data(widget)
        else:
            display(widget)

    def finish_auth(gis):
        context["gis"] = gis
        if auth_container is not None:
            auth_container.children = ()
        _emit(
            f"Authenticated as: {context['gis'].properties.user.username} "
            f"(role: {context['gis'].properties.user.role} / userType: {context['gis'].properties.user.userLicenseTypeId})"
        )
        _emit("")
        _emit("Step 1 is complete. Continue to the next step when you are ready.")

    # Try ArcGIS Notebook profile
    if current_env == "arcgisnotebook":
        try:
            gis = GIS("home")
            finish_auth(gis)
            return
        except Exception:
            pass

    # Try OAuth if client_id provided
    if client_id:
        try:
            gis = GIS(portal_url, client_id=client_id, authorize=True)
            finish_auth(gis)
            return
        except Exception:
            pass

    # Fallback to username/password widgets
    username_widget = widgets.Text(description="Username:")
    password_widget = widgets.Password(description="Password:")
    login_button = widgets.Button(description="Login")
    output = widgets.Output()

    def handle_login(button):
        output.clear_output()
        output.append_stdout("Logging in...\n")
        try:
            gis = GIS(portal_url, username_widget.value, password_widget.value)
            finish_auth(gis)
        except Exception as e:
            output.append_stdout(f"Login failed: {e}\n")

    login_button.on_click(handle_login)
    _emit("Complete authentication using the login form below.")
    _emit_widget(widgets.VBox([username_widget, password_widget, login_button, output]))

# ======================================================================
# ipywidgets Config
# ======================================================================

def initialize_ui(widget_type="text", description="", placeholder="", width="200px", height="40px", value=None, layout=None, elements=None):
    """
    Utility to create and return common ipywidgets for UI setup.
    """
    import ipywidgets as widgets # type: ignore

    if not layout:
        layout = widgets.Layout(width=width, height=height)

    if widget_type == "button":
        return widgets.Button(description=description, layout=layout)
    elif widget_type == "checkbox":
        # Checkboxes with long descriptions should not be constrained to narrow fixed widths.
        checkbox_layout = layout
        if checkbox_layout.width in (None, "", "200px"):
            checkbox_layout = widgets.Layout(width="auto", height=height)
        return widgets.Checkbox(
            value=value if value is not None else False, 
            description=description, 
            layout=checkbox_layout,
            style={"description_width": "initial"})
    elif widget_type == "text":
        return widgets.Text(
            value=value if value is not None else "", 
            placeholder=placeholder if placeholder is not None else "", 
            description=description, 
            layout=layout,
            style={"description_width": "initial"}
        )
    elif widget_type == "label":
        return widgets.Label(value=value if value is not None else "", layout=layout)
    elif widget_type == "output":
        return widgets.Output()
    elif widget_type == "hbox":
        # expects elements to be a list of widgets
        return widgets.HBox(elements if elements else [])
    elif widget_type == "textarea":
    # Support multi-line input
        return widgets.Textarea(
            value=value or "",
            description=description or "",
            placeholder=placeholder or "",
            layout=layout,
            style={"description_width": "initial"},
        )
    else:
        raise ValueError("Unsupported widget_type")

def _spinner_status_html(message):
    safe_message = escape(message)
    return (
        "<span style='display:inline-flex; align-items:center; gap:8px; color:#555;'>"
        "<span style='width:12px; height:12px; border:2px solid #c8c8c8; border-top-color:#2b7cd3; "
        "border-radius:50%; display:inline-block; animation: spin 0.9s linear infinite;'></span>"
        f"{safe_message}"
        "</span>"
        "<style>@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }</style>"
    )


def bind_button_with_status(
    button,
    action,
    status_key,
    start_message,
    success_message="Done.",
    failure_message="Action failed. See details below.",
    output_key=None,
):
    """Bind a button click to an action with spinner-style status updates."""
    context = _ctx()
    status_colors = {
        "success": "#2e7d32",
        "warning": "#8a6d3b",
        "info": "#555",
        "failure": "#b00020",
        "error": "#b00020",
    }

    def _wrapped(clicked_button):
        status_widget = context.get(status_key)
        active_button = button if button is not None else clicked_button

        if status_widget is not None:
            status_widget.value = _spinner_status_html(start_message)

        if active_button is not None:
            active_button.disabled = True

        try:
            action_result = action(clicked_button)
            if status_widget is not None:
                if isinstance(action_result, dict) and action_result.get("status"):
                    result_status = str(action_result.get("status")).lower()
                    result_message = str(action_result.get("message") or success_message)
                    color = status_colors.get(result_status, status_colors["info"])
                    status_widget.value = f"<span style='color:{color};'>{escape(result_message)}</span>"
                elif action_result is False:
                    status_widget.value = (
                        "<span style='color:#8a6d3b;'>"
                        "Setup initialized."
                        "</span>"
                    )
                else:
                    status_widget.value = f"<span style='color:#2e7d32;'>{escape(success_message)}</span>"
        except Exception as exc:
            if status_widget is not None:
                status_widget.value = f"<span style='color:#b00020;'>{escape(failure_message)}</span>"

            output_widget = context.get(output_key) if output_key else None
            if output_widget is not None:
                output_widget.append_stdout(f"Unexpected error: {exc}\n")
            raise
        finally:
            if active_button is not None:
                active_button.disabled = False

    # Remove previously-registered wrappers on this button.
    for wrapper_attr in ("_binding_status_wrapper",):
        existing_wrapper = getattr(button, wrapper_attr, None)
        if existing_wrapper is not None:
            try:
                button.on_click(existing_wrapper, remove=True)
            except Exception:
                pass
            try:
                delattr(button, wrapper_attr)
            except Exception:
                pass

    button.on_click(_wrapped)
    setattr(button, "_binding_status_wrapper", _wrapped)

class ScanCancelled(RuntimeError):
    """Raised when a scan is cancelled by the user."""


def _scan_cancel_requested(context):
    return bool(context.get("scan_cancel_requested"))


def _parse_optional_positive_int(raw_value, field_name):
    """Parse optional positive integer input; empty values return None."""
    entered = str(raw_value or "").strip()
    if not entered:
        return None
    try:
        parsed = int(entered)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a whole number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return parsed


class _OutputWidgetStdoutProxy:
    """File-like proxy to route stdout text into an ipywidgets Output widget."""

    def __init__(self, output_widget):
        self.output_widget = output_widget

    def write(self, text):
        if not text:
            return 0
        self.output_widget.append_stdout(text)
        return len(text)

    def flush(self):
        return None


def _invoke_context_callback(context, callback_key):
    callback = context.get(callback_key)
    if callable(callback):
        callback()


def bind_primary_scan_with_cancel(
    button,
    status_key="scan_status",
    output_key="scan_output",
    input_key="scan_terms_input",
    limit_input_key="scan_limit_input",
):
    """Bind Step 2 button with Scan/Cancel toggle behavior."""
    context = _ctx()

    status_widget = context.get(status_key)
    output_widget = context.get(output_key)
    input_widget = context.get(input_key)
    limit_input_widget = context.get(limit_input_key) if limit_input_key else None

    if output_widget is None or input_widget is None:
        raise RuntimeError("Primary scan UI is not configured.")

    def set_button_idle():
        button.description = "Scan for items"
        button.button_style = ""
        button.icon = ""
        button.tooltip = "Start scan"

    def set_button_cancel_mode():
        button.description = "Cancel scan"
        button.button_style = "danger"
        button.icon = "stop"
        button.tooltip = "Cancel running scan"

    def _scan_worker(terms, max_matches):
        try:
            with redirect_stdout(_OutputWidgetStdoutProxy(output_widget)):
                matches_df, errors_df, all_items_df = scan_org_licenseinfo_without_10k_cap(
                    context["gis"],
                    target_strings=terms,
                    max_matches=max_matches,
                    cancel_check=lambda: _scan_cancel_requested(context),
                )

            context["matches_df"] = matches_df
            context["errors_df"] = errors_df
            context["all_items_df"] = all_items_df
            context["TARGET_STRINGS"] = terms

            output_widget.append_stdout(
                f"Scan results: {count_phrase(len(matches_df), 'match')} | "
                f"{count_phrase(len(errors_df), 'error')}\n"
            )
            sample_count = min(len(matches_df), 3)
            if sample_count:
                output_widget.append_stdout(f"Showing {count_phrase(sample_count, 'sample match')}:\n")
                output_widget.append_display_data(matches_df.head(sample_count))
            else:
                output_widget.append_stdout("No sample matches to display.\n")

            if status_widget is not None:
                status_widget.value = "<span style='color:#2e7d32;'>Scan complete.</span>"
            _invoke_context_callback(context, "refresh_scan_save_ui")
        except ScanCancelled:
            output_widget.append_stdout("\nScan canceled by user.\n")
            if status_widget is not None:
                status_widget.value = "<span style='color:#8a6d3b;'>Scan canceled.</span>"
        except Exception as exc:
            output_widget.append_stdout(f"\nUnexpected error: {exc}\n")
            if status_widget is not None:
                status_widget.value = "<span style='color:#b00020;'>Scan failed. See details below.</span>"
        finally:
            context["scan_running"] = False
            set_button_idle()
            button.disabled = False

    def _toggle_scan(_clicked_button):
        if context.get("scan_running"):
            context["scan_cancel_requested"] = True
            if status_widget is not None:
                status_widget.value = "<span style='color:#8a6d3b;'>Cancel requested... stopping scan.</span>"
            return

        output_widget.clear_output()

        if context.get("gis") is None:
            output_widget.append_stdout("Please run Step 1: Setup and authenticate first.\n")
            if status_widget is not None:
                status_widget.value = "<span style='color:#b00020;'>Scan failed. See details below.</span>"
            set_button_idle()
            return

        terms = parse_target_terms(input_widget.value)
        if not terms:
            output_widget.append_stdout("No search terms provided.\n")
            if status_widget is not None:
                status_widget.value = "<span style='color:#b00020;'>Scan failed. See details below.</span>"
            set_button_idle()
            return

        input_widget.value = normalize_target_terms_text(terms)

        try:
            max_matches = _parse_optional_positive_int(
                limit_input_widget.value if limit_input_widget is not None else None,
                "Optional match cap",
            )
        except ValueError as exc:
            output_widget.append_stdout(f"{exc}\n")
            if status_widget is not None:
                status_widget.value = "<span style='color:#b00020;'>Scan failed. See details below.</span>"
            set_button_idle()
            return

        if max_matches is None:
            output_widget.append_stdout(
                f"Running scan with {count_phrase(len(terms), 'term')} across the full organization...\n"
            )
        else:
            output_widget.append_stdout(
                f"Running scan with {count_phrase(len(terms), 'term')} and a match cap of {max_matches}...\n"
            )

        context["scan_cancel_requested"] = False
        context["scan_running"] = True
        set_button_cancel_mode()

        if status_widget is not None:
            status_widget.value = _spinner_status_html("Scan in progress... please wait.")

        worker = threading.Thread(target=_scan_worker, args=(terms, max_matches), daemon=True)
        context["scan_worker"] = worker
        worker.start()

    # Remove any previous wrappers that may have been attached in earlier notebook runs.
    for wrapper_attr in ("_scan_toggle_wrapper", "_binding_status_wrapper", "_copilot_status_wrapper"):
        existing_wrapper = getattr(button, wrapper_attr, None)
        if existing_wrapper is not None:
            try:
                button.on_click(existing_wrapper, remove=True)
            except Exception:
                pass
            try:
                delattr(button, wrapper_attr)
            except Exception:
                pass

    button.on_click(_toggle_scan)
    setattr(button, "_scan_toggle_wrapper", _toggle_scan)
    set_button_idle()
    context.setdefault("scan_running", False)
    context.setdefault("scan_cancel_requested", False)


def setup_notebook_btn(button):
    context = _ctx()
    setup_output = context.get("setup_output")
    if setup_output is None:
        raise RuntimeError("context['setup_output'] is not configured.")

    auth_container = context.get("auth_container")
    if auth_container is not None:
        auth_container.children = ()

    setup_output.clear_output()
    setup_output.append_stdout("Setting up the notebook environment...\n")
    setup_output.append_stdout(f"\tPython version: {sys.version}\n")
    setup_output.append_stdout(f"\tArcGIS for Python API version: {arcgis.__version__}\n")
    authenticate_gis(context=context, output_widget=setup_output)
    if context.get("gis") is not None:
        setup_output.append_stdout("Authentication complete.\n")
        return True
    return False


# ======================================================================
# Org scanning functions
# ======================================================================

def parse_target_terms(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return []

    # Backward compatibility: accept legacy Python-list input format.
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

    # Preferred format: CSV-like text. Terms with spaces can be wrapped in double quotes.
    # Example: foo, "bar baz", https://example.com
    terms = []
    reader = csv.reader(io.StringIO(text), skipinitialspace=True)
    for row in reader:
        for value in row:
            cleaned = str(value).strip()
            if cleaned:
                terms.append(cleaned)
    return terms


def normalize_target_terms_text(terms):
    """Return a canonical string form like ["term1", "term2"]."""
    return json.dumps(list(terms), ensure_ascii=False)

def run_primary_scan_btn(button):
    context = _ctx()
    scan_output = context.get("scan_output")
    scan_terms_input = context.get("scan_terms_input")
    scan_limit_input = context.get("scan_limit_input")
    if scan_output is None or scan_terms_input is None:
        raise RuntimeError("context['scan_output'] and context['scan_terms_input'] must be configured.")

    scan_output.clear_output()
    if context.get("gis") is None:
        scan_output.append_stdout("Please run Step 1: Setup and authenticate first.\n")
        return

    terms = parse_target_terms(scan_terms_input.value)
    if not terms:
        scan_output.append_stdout("No search terms provided.\n")
        return

    scan_terms_input.value = normalize_target_terms_text(terms)

    try:
        max_matches = _parse_optional_positive_int(
            scan_limit_input.value if scan_limit_input is not None else None,
            "Optional match cap",
        )
    except ValueError as exc:
        scan_output.append_stdout(f"{exc}\n")
        return

    if max_matches is None:
        scan_output.append_stdout(f"Running scan with {count_phrase(len(terms), 'term')} across the full organization...\n")
    else:
        scan_output.append_stdout(
            f"Running scan with {count_phrase(len(terms), 'term')} and a match cap of {max_matches}...\n"
        )
    with redirect_stdout(_OutputWidgetStdoutProxy(scan_output)):
        matches_df, errors_df, all_items_df = scan_org_licenseinfo_without_10k_cap(
            context["gis"],
            target_strings=terms,
            max_matches=max_matches,
        )
    context["matches_df"] = matches_df
    context["errors_df"] = errors_df
    context["all_items_df"] = all_items_df
    context["TARGET_STRINGS"] = terms

    scan_output.append_stdout(
        f"Scan results: {count_phrase(len(matches_df), 'match')} | "
        f"{count_phrase(len(errors_df), 'error')}\n"
    )
    sample_count = min(len(matches_df), 3)
    if sample_count:
        scan_output.append_stdout(f"Showing {count_phrase(sample_count, 'sample match')}:\n")
        scan_output.append_display_data(matches_df.head(sample_count))
    else:
        scan_output.append_stdout("No sample matches to display.\n")


def _paged_get(gis, path, params=None, records_key="items", page_size=100):
    """Generic paginator for REST endpoints that use start/num/nextStart.
    
    PARAMS
    gis: authenticated GIS object
    path: REST endpoint path
    params: dictionary of additional parameters to include in the request
    records_key: key in the response JSON that contains the records (default "items")
    page_size: number of records to request per page (default 100, max 10000)
    """
    if params is None:
        params = {}
    start = 1
    all_rows = []

    while True:
        payload = {"f": "json", "start": start, "num": page_size, **params}
        resp = gis._con.get(path, payload)

        rows = resp.get(records_key, [])
        all_rows.extend(rows)

        next_start = resp.get("nextStart", -1)
        if next_start in (-1, None):
            break
        start = next_start

    return all_rows


def get_all_org_usernames(gis, page_size=100):
    """
    Get every username in the org by paging portal users.
    Avoids user-search caps.

    PARAMS
    gis: authenticated GIS object
    page_size: number of users to request per page (default 100, max 10000)
    """
    users = _paged_get(
        gis,
        path="portals/self/users",
        params={},
        records_key="users",
        page_size=page_size
    )
    usernames = [u["username"] for u in users if "username" in u]
    return usernames


def get_all_items_for_user(gis, username, user_idx=None, page_size=25, progress_every=25, cancel_check=None):
    """
    Get all items for one user, including root and all folders.
    
    PARAMS
    gis: authenticated GIS object
    username: string username to query
    page_size: number of items to request per page (default 25, max 10000)
    """
    prefix = f"Scanning user[{user_idx}]: {username}" if user_idx is not None else f"Scanning user: {username}"
    user_items = []
    next_tick = progress_every

    def show_progress(found, done=False):
        line = f"{prefix} Found {count_phrase(found, 'item')}"
        print(line, end="\n" if done else "\r", flush=True)

    def add_and_report(rows):
        nonlocal next_tick
        user_items.extend(rows)
        found = len(user_items)

        while found >= next_tick:
            show_progress(next_tick, done=False)
            next_tick += progress_every

    # Root items (paged)
    start = 1
    while True:
        if cancel_check and cancel_check():
            raise ScanCancelled("Canceled during user item scan.")
        resp = gis._con.get(
            f"content/users/{username}",
            {"f": "json", "start": start, "num": page_size}
        )
        rows = resp.get("items", [])
        add_and_report(rows)

        next_start = resp.get("nextStart", -1)
        if next_start in (-1, None):
            break
        start = next_start

    # Need a call to read folder list
    root_resp = gis._con.get(f"content/users/{username}", {"f": "json"})
    folders = root_resp.get("folders", [])

    # Folder items (paged per folder)
    for folder in folders:
        if cancel_check and cancel_check():
            raise ScanCancelled("Canceled during folder scan.")
        folder_id = folder.get("id")
        if not folder_id:
            continue

        start = 1
        while True:
            if cancel_check and cancel_check():
                raise ScanCancelled("Canceled during folder item scan.")
            resp = gis._con.get(
                f"content/users/{username}/{folder_id}",
                {"f": "json", "start": start, "num": page_size}
            )
            rows = resp.get("items", [])
            add_and_report(rows)

            next_start = resp.get("nextStart", -1)
            if next_start in (-1, None):
                break
            start = next_start

    show_progress(len(user_items), done=True)
    return user_items

def build_item_urls(gis, item_id, access):
    """
    Build public and portal URLs for an item.

    public_url is only returned for publicly shared items.
    portal_url always points at the org's signed-in item page.
    """
    url_key = gis.properties.get("urlKey")
    custom_base_url = gis.properties.get("customBaseUrl", "maps.arcgis.com")

    if url_key and custom_base_url:
        portal_url = f"https://{url_key}.{custom_base_url}/home/item.html?id={item_id}"
    else:
        portal_url = f"https://www.arcgis.com/home/item.html?id={item_id}"

    public_url = None
    if (access or "").lower() == "public":
        public_url = f"https://www.arcgis.com/home/item.html?id={item_id}"

    return public_url, portal_url


def build_item_thumbnail_data_uri(gis, item_id, thumbnail_name):
    """Fetch item thumbnail and return as a data URI; returns empty string on failure."""
    if not thumbnail_name:
        return ""

    try:
        rest_base = str(gis._portal.resturl).rstrip("/")
        thumb_url = f"{rest_base}/content/items/{item_id}/info/{thumbnail_name}"
        token = getattr(gis._con, "token", None)
        params = {"token": token} if token else {}
        resp = requests.get(thumb_url, params=params, timeout=20)
        if not resp.ok:
            return ""
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            return ""
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return ""


def build_item_thumbnail_url(review_url, item_id, thumbnail_name):
    """Construct a thumbnail URL as fallback when inlining is unavailable."""
    if not thumbnail_name:
        return ""

    try:
        host = urlparse(review_url).netloc
        scheme = urlparse(review_url).scheme or "https"
        if not host:
            host = "www.arcgis.com"
        return f"{scheme}://{host}/sharing/rest/content/items/{item_id}/info/{thumbnail_name}"
    except Exception:
        return ""

def scan_org_licenseinfo_without_10k_cap(
    gis,
    target_strings=None,
    pause_seconds=0.0,
    exclude_item_ids=None,
    cancel_check=None,
    max_matches=None,
):
    """
    Exhaustive scan of org items (no 10k search cap) by traversing users/folders/items.

    PARAMS
    gis: authenticated GIS object
    target_strings: list of strings to search for in the licenseInfo field (case-insensitive)
    pause_seconds: number of seconds to pause between item metadata requests (default 0, can be used to avoid hitting rate limits)

    RETURNS 
    matches_df: DataFrame of items whose licenseInfo field contains any of the target strings
    errors_df: DataFrame of any errors encountered at the user level
    all_items_df: DataFrame of all unique item_ids scanned
    exclude_item_ids: optional list of item IDs to exclude from scanning (e.g. items from previous run or known false positives)
    """
    if target_strings is None:
        target_strings = ["https://downloads.esri.com/blogs/arcgisonline/esrilogo_new.png"]

    exclude_set = {str(x) for x in (exclude_item_ids or [])}
    has_exclusions = bool(exclude_set)

    usernames = get_all_org_usernames(gis)
    print(f"Users found: {count_phrase(len(usernames), 'user')}")

    matches = []
    errors = []
    all_seen = set()
    all_items_rows = []
    total_scanned = 0
    total_skipped_excluded = 0

    max_matches = int(max_matches) if max_matches is not None else None
    stop_early = False

    for u_idx, username in enumerate(usernames, start=1):
        if cancel_check and cancel_check():
            raise ScanCancelled("Canceled before user iteration.")
        try:
            items = get_all_items_for_user(
                gis,
                username,
                user_idx=u_idx,
                page_size=100,
                progress_every=25,
                cancel_check=cancel_check,
            )

            for item in items:
                if cancel_check and cancel_check():
                    raise ScanCancelled("Canceled during item iteration.")
                item_id = str(item.get("id") or "")
                if not item_id or item_id in all_seen:
                    continue
                all_seen.add(item_id)

                license_info = item.get("licenseInfo") or ""
                li_lower = license_info.lower()
                access = (item.get("access") or "").lower()

                public_url, portal_url = build_item_urls(gis, item_id, access)
                all_items_rows.append({
                    "item_id": item_id,
                    "title": item.get("title"),
                    "owner": item.get("owner"),
                    "type": item.get("type"),
                    "access": access,
                    "licenseInfo": license_info,
                    "public_url": public_url,
                    "portal_url": portal_url,
                    "thumbnail": item.get("thumbnail") or "",
                })

                if item_id in exclude_set:
                    total_skipped_excluded += 1
                    continue

                matched = [term for term in target_strings if term.lower() in li_lower]
                if matched:
                    matches.append({
                        "item_id": item_id,
                        "title": item.get("title"),
                        "owner": item.get("owner"),
                        "type": item.get("type"),
                        "access": access,
                        "licenseInfo": license_info,
                        "matched_terms": ", ".join(matched),                        
                        "public_url": public_url,
                        "portal_url": portal_url,
                        "thumbnail": item.get("thumbnail") or "",
                    })
                    if max_matches is not None and len(matches) >= max_matches:
                        stop_early = True
                        total_scanned += 1
                        if pause_seconds:
                            time.sleep(pause_seconds)
                        break

                total_scanned += 1
                if pause_seconds:
                    time.sleep(pause_seconds)

            if u_idx % 25 == 0:
                if has_exclusions:
                    print(
                        f"Processed {u_idx} of {len(usernames)} users | "
                        f"{count_phrase(len(all_seen), 'unique item')} seen | "
                        f"{count_phrase(total_scanned, 'item')} scanned after exclusions | "
                        f"{count_phrase(total_skipped_excluded, 'item')} excluded"
                    )
                else:
                    print("*********************************")
                    print(
                        f"Processed {u_idx} of {len(usernames)} users | "
                        f"{count_phrase(len(all_seen), 'unique item')} found"
                    )
                    print("*********************************")

            if stop_early:
                break

        except Exception as exc:
            errors.append({
                "username": username,
                "error": str(exc)
            })
        if stop_early:
            break
    matches_df = pd.DataFrame(matches)
    errors_df = pd.DataFrame(errors, columns=["username", "error"])
    all_items_df = pd.DataFrame(all_items_rows)
    if all_items_df.empty:
        all_items_df = pd.DataFrame(
            columns=[
                "item_id",
                "title",
                "owner",
                "type",
                "access",
                "licenseInfo",
                "public_url",
                "portal_url",
                "thumbnail",
            ]
        )
    else:
        all_items_df = all_items_df.drop_duplicates(subset=["item_id"], keep="first").reset_index(drop=True)

    # Add a column to matches_df that uses the public_url if available, otherwise falls back to the portal_url
    if not matches_df.empty:
        matches_df["review_url"] = matches_df["public_url"].fillna(matches_df["portal_url"])
    else:
        matches_df = pd.DataFrame(columns=[
            "item_id",
            "title",
            "owner",
            "type",
            "access",
            "licenseInfo",
            "matched_terms",
            "public_url",
            "portal_url",
            "thumbnail",
            "review_url",
        ])

    print(f"\n*** Done! ***")
    print(f"Unique items found: {count_phrase(len(all_seen), 'item')}")
    if has_exclusions:
        print(f"Items excluded from previous run: {count_phrase(total_skipped_excluded, 'item')}")
    print(f"Items scanned: {count_phrase(total_scanned, 'item')}")
    if max_matches is not None and stop_early:
        print(f"Scan stopped after reaching match cap: {max_matches}")

    return matches_df, errors_df, all_items_df

# =====================================================================
# File handling
# =====================================================================

def save_scan_outputs_btn(button):
    context = _ctx()
    save_scan_output = context.get("save_scan_output")
    scan_matches_path_input = context.get("scan_matches_path_input")
    scan_errors_path_input = context.get("scan_errors_path_input")
    scan_all_items_path_input = context.get("scan_all_items_path_input")
    if save_scan_output is None:
        raise RuntimeError("context['save_scan_output'] is not configured.")

    save_scan_output.clear_output()
    matches_df = context.get("matches_df")
    errors_df = context.get("errors_df")
    all_items_df = context.get("all_items_df")
    if matches_df is None or errors_df is None or all_items_df is None:
        save_scan_output.append_stdout("Run Step 2 or Step 3 to load saved scan files first.\n")
        return

    export_targets = []
    skipped_targets = []

    if not matches_df.empty:
        matches_path = resolve_output_path(
            scan_matches_path_input.value if scan_matches_path_input is not None else None,
            "scan_matches.csv",
        )
        export_targets.append(("Matches CSV", matches_df, matches_path))
    else:
        skipped_targets.append("Matches CSV")

    if not errors_df.empty:
        errors_path = resolve_output_path(
            scan_errors_path_input.value if scan_errors_path_input is not None else None,
            "scan_errors.csv",
        )
        export_targets.append(("Errors CSV", errors_df, errors_path))
    else:
        skipped_targets.append("Errors CSV")

    if not all_items_df.empty:
        all_items_path = resolve_output_path(
            scan_all_items_path_input.value if scan_all_items_path_input is not None else None,
            "scan_all_items.csv",
        )
        export_targets.append(("All items CSV", all_items_df, all_items_path))
    else:
        skipped_targets.append("All items CSV")

    if not export_targets:
        save_scan_output.append_stdout("Nothing to export. All scan output tables are empty.\n")
        return

    save_scan_output.append_stdout("Saved files:\n")
    for _label, dataframe, target_path in export_targets:
        dataframe.to_csv(target_path, index=False)
        save_scan_output.append_stdout(f"- {target_path}\n")

    if skipped_targets:
        for label in skipped_targets:
            save_scan_output.append_stdout(f"{_empty_output_message(label)}\n")


def export_dry_run_btn(_button):
    context = _ctx()
    dry_run_export_output = context.get("dry_run_export_output")
    if dry_run_export_output is None:
        raise RuntimeError("context['dry_run_export_output'] is not configured.")

    dry_run_export_output.clear_output()
    plan_df = context.get("plan_df")
    if plan_df is None:
        dry_run_export_output.append_stdout("Do a dry-run first.\n")
        return

    dry_run_export_path_input = context.get("dry_run_export_path_input")
    csv_name = "dry_run_results.csv"
    if dry_run_export_path_input is not None:
        entered = (dry_run_export_path_input.value or "").strip()
        if entered:
            csv_name = entered
    if not csv_name.lower().endswith(".csv"):
        csv_name = f"{csv_name}.csv"

    csv_path = resolve_output_path(csv_name, "dry_run_results.csv")
    plan_df.to_csv(csv_path, index=False)
    dry_run_export_output.append_stdout(f"Saved file: {csv_path}\n")

def create_report_btn(_button):
    context = _ctx()
    create_report_output = context.get("create_report_output")
    report_path_input = context.get("report_path_input")
    selection_json_name_input = context.get("selection_json_name_input")
    report_limit_input = context.get("report_limit_input")
    if create_report_output is None:
        raise RuntimeError("context['create_report_output'] is not configured.")

    create_report_output.clear_output()
    plan_df = context.get("plan_df")
    if plan_df is None:
        create_report_output.append_stdout("Do a dry-run before creating the report.\n")
        return

    try:
        max_rows = _parse_optional_positive_int(
            report_limit_input.value if report_limit_input is not None else None,
            "Optional match cap",
        )
    except ValueError as exc:
        create_report_output.append_stdout(f"{exc}\n")
        return

    report_filename = "dry_run_report.html"
    if report_path_input is not None and (report_path_input.value or "").strip():
        report_filename = report_path_input.value.strip()
    if not report_filename.lower().endswith(".html"):
        report_filename = f"{report_filename}.html"

    selection_json_name = "selected_item_ids.json"
    if selection_json_name_input is not None and (selection_json_name_input.value or "").strip():
        selection_json_name = selection_json_name_input.value.strip()
    if not selection_json_name.lower().endswith(".json"):
        selection_json_name = f"{selection_json_name}.json"

    plan_for_report = plan_df.copy()
    if max_rows is None:
        create_report_output.append_stdout("Creating report for all planned updates...\n")
    else:
        plan_for_report = plan_for_report[plan_for_report["will_update"] == True].head(max_rows).copy()
        create_report_output.append_stdout(f"Creating report with a match cap of {max_rows} planned update rows...\n")

    report_path = build_side_by_side_report(
        plan_for_report,
        report_output_path=str(resolve_output_path(report_filename, "dry_run_report.html")),
        only_updates=max_rows is None,
        gis=context.get("gis"),
        selection_out_json=Path(selection_json_name).name,
    )
    context["report_path"] = report_path
    create_report_output.append_stdout(f"Report saved to: {report_path}\n")
    embedded = display_embedded_html_report(
        report_path,
        height_px=760,
        output_widget=create_report_output,
        max_inline_bytes=2 * 1024 * 1024,
    )
    if not embedded:
        create_report_output.append_stdout("Inline report preview unavailable.\n")

    if current_env != "arcgisnotebook":
        create_report_output.append_display_data(HTML(f"<div style=\"margin-top:8px;\">{build_notebook_file_link(report_path, 'Open report', as_button=True)}</div>"))
    else:
        create_report_output.append_stdout(
            "In ArcGIS Online, open the saved HTML report from the Files panel rather than from an output-cell button.\n"
        )
    create_report_output.append_stdout("\nIn the report, choose rows with the checkboxes and click 'Download selected Item IDs (JSON)'.\n")
    create_report_output.append_stdout(f"Then upload or copy that file into /{OUTPUT_DIR_NAME} before running Step 6.\n")
    create_report_output.append_stdout(f"When downloading item IDs from the report, the output file name will be: {Path(selection_json_name).name}\n")

def load_previous_scan_btn(_button):
    context = _ctx()
    reload_scan_output = context.get("reload_scan_output")
    reload_matches_path_input = context.get("reload_matches_path_input")
    reload_errors_path_input = context.get("reload_errors_path_input")
    reload_all_items_path_input = context.get("reload_all_items_path_input")
    if (
        reload_scan_output is None
        or reload_matches_path_input is None
        or reload_errors_path_input is None
        or reload_all_items_path_input is None
    ):
        raise RuntimeError("Step 3 inputs and output must be configured.")

    reload_scan_output.clear_output()

    matches_path = (reload_matches_path_input.value or "").strip()
    errors_path = (reload_errors_path_input.value or "").strip()
    all_items_path = (reload_all_items_path_input.value or "").strip()

    if not matches_path or not Path(matches_path).exists():
        reload_scan_output.append_stdout(f"Matches file not found: {matches_path}\n")
        return
    if not all_items_path or not Path(all_items_path).exists():
        reload_scan_output.append_stdout(f"All-items file not found: {all_items_path}\n")
        return

    context["matches_df"] = pd.read_csv(matches_path, dtype={"item_id": str})

    if errors_path and Path(errors_path).exists():
        try:
            context["errors_df"] = pd.read_csv(errors_path)
        except pd.errors.EmptyDataError:
            context["errors_df"] = pd.DataFrame(columns=["username", "error"])
    else:
        context["errors_df"] = pd.DataFrame(columns=["username", "error"])
        reload_scan_output.append_stdout(f"Errors file not found or blank, using empty table: {errors_path}\n")

    context["all_items_df"] = pd.read_csv(all_items_path, dtype={"item_id": str})

    reload_scan_output.append_stdout(
        f"Reloaded: matches={len(context['matches_df'])}, "
        f"errors={len(context['errors_df'])}, "
        f"all_items={len(context['all_items_df'])}\n"
    )
    _invoke_context_callback(context, "refresh_scan_save_ui")


def run_dry_run_with_file_btn(_button):
    context = _ctx()
    dry_run_template_path_input = context.get("dry_run_template_path_input")
    if dry_run_template_path_input is None:
        raise RuntimeError("context['dry_run_template_path_input'] is not configured.")

    entered = (dry_run_template_path_input.value or "").strip()
    context["official_tou_html_file"] = entered or OFFICIAL_TOU_HTML_FILE
    dry_run_btn(_button)


def preview_dry_run_match_btn(_button):
    context = _ctx()
    dry_run_preview_output = context.get("dry_run_preview_output")
    if dry_run_preview_output is None:
        raise RuntimeError("context['dry_run_preview_output'] is not configured.")

    dry_run_preview_output.clear_output()

    matches_df = context.get("matches_df")
    if matches_df is None:
        dry_run_preview_output.append_stdout("Run Step 2 or load saved scan files first.\n")
        return

    dry_run_template_path_input = context.get("dry_run_template_path_input")
    entered = (dry_run_template_path_input.value or "").strip() if dry_run_template_path_input is not None else ""
    context["official_tou_html_file"] = entered or OFFICIAL_TOU_HTML_FILE

    checkbox8 = context.get("checkbox8")
    strict_match = bool(checkbox8.value) if checkbox8 is not None else False

    replacement_tou = load_official_tou_html(context.get("official_tou_html_file", OFFICIAL_TOU_HTML_FILE))
    plan_df = build_licenseinfo_update_plan(matches_df, replacement_tou, strict_match=strict_match)
    to_update = plan_df[plan_df["will_update"] == True].copy()

    if to_update.empty:
        mode_label = "strict" if strict_match else "default"
        dry_run_preview_output.append_stdout(
            f"No updatable rows were found for the current {mode_label} matching mode, so there is nothing to preview.\n"
        )
        return

    first_row = to_update.iloc[0]
    matched_html = _extract_tou_match_fragment(first_row.get("old_licenseInfo"), strict_match=strict_match)
    if not matched_html:
        matched_html = first_row.get("old_licenseInfo") or ""
        dry_run_preview_output.append_stdout(
            "Could not isolate the matched block exactly, so the preview is showing the full existing Terms of Use HTML for the first updatable row.\n"
        )
    else:
        dry_run_preview_output.append_stdout(
            "Previewing the first updatable row using the current matching mode.\n"
        )

    display_dry_run_iframe_preview(
        dry_run_preview_output,
        matched_html=matched_html,
        replacement_html=replacement_tou,
        item_title=first_row.get("title") or "",
        item_id=first_row.get("item_id") or "",
        item_owner=first_row.get("owner") or "",
        item_type=first_row.get("type") or "",
        matched_terms=first_row.get("matched_terms") or "",
        replacements_found=first_row.get("replacements_found") or "",
        strict_match=strict_match,
    )

def export_final_results_btn(_button):
    context = _ctx()
    export_final_results_output = context.get("export_final_results_output")
    edit_successes_path_input = context.get("edit_successes_path_input")
    edit_errors_path_input = context.get("edit_errors_path_input")
    if export_final_results_output is None:
        raise RuntimeError("context['export_final_results_output'] is not configured.")

    export_final_results_output.clear_output()
    success_df = context.get("success_df")
    update_errors_df = context.get("update_errors_df")
    if success_df is None or update_errors_df is None:
        export_final_results_output.append_stdout("Run Step 6 first to create the export data.\n")
        return

    export_targets = []
    skipped_targets = []

    if not success_df.empty:
        success_path = resolve_output_path(
            edit_successes_path_input.value if edit_successes_path_input is not None else None,
            "update_successes.csv",
        )
        export_targets.append(("Success CSV", success_df, success_path))
    else:
        skipped_targets.append("Success CSV")

    if not update_errors_df.empty:
        errors_path = resolve_output_path(
            edit_errors_path_input.value if edit_errors_path_input is not None else None,
            "update_errors.csv",
        )
        export_targets.append(("Errors CSV", update_errors_df, errors_path))
    else:
        skipped_targets.append("Errors CSV")

    if not export_targets:
        export_final_results_output.append_stdout("Nothing to export. Both final result tables are empty.\n")
        return

    export_final_results_output.append_stdout("Saved files:\n")
    for _label, dataframe, target_path in export_targets:
        dataframe.to_csv(target_path, index=False)
        export_final_results_output.append_stdout(f"- {target_path}\n")

    if skipped_targets:
        for label in skipped_targets:
            export_final_results_output.append_stdout(f"{_empty_output_message(label)}\n")

# =====================================================================
# Dry run functions
# =====================================================================

def dry_run_btn(_button):
    context = _ctx()
    dry_run_output = context.get("dry_run_output")
    if dry_run_output is None:
        raise RuntimeError("context['dry_run_output'] is not configured.")

    dry_run_output.clear_output()
    matches_df = context.get("matches_df")
    if matches_df is None:
        dry_run_output.append_stdout("Run Step 2 or load saved scan files first.\n")
        return

    checkbox8 = context.get("checkbox8")
    strict_match = bool(checkbox8.value) if checkbox8 is not None else False
    context["strict_match_updates"] = strict_match

    tou_path = context.get("official_tou_html_file", OFFICIAL_TOU_HTML_FILE)
    replacement_tou = load_official_tou_html(tou_path)
    plan_df = build_licenseinfo_update_plan(matches_df, replacement_tou, strict_match=strict_match)
    dry_run_table = show_dry_run(plan_df)
    rows_would_update = int((plan_df["will_update"] == True).sum())
    context["plan_df"] = plan_df
    context["dry_run_table"] = dry_run_table
    if strict_match:
        dry_run_output.append_stdout(
            "Dry-run mode: strict matching enabled. Only canonical Esri Terms of Use blocks with summary and terms links in the expected order will be replaced.\n"
        )
    else:
        dry_run_output.append_stdout(
            "Dry-run mode: default semi-greedy matching enabled. The matcher can bridge across bounded formatting differences between the logo, license text, and links.\n"
        )
    dry_run_output.append_stdout(
        f"Dry-run summary: {count_phrase(len(plan_df), 'matched row')}, "
        f"{count_phrase(rows_would_update, 'row')} would be updated.\n"
    )
    sample_count = min(len(dry_run_table), 3)
    if sample_count:
        dry_run_output.append_stdout(f"Showing {count_phrase(sample_count, 'sample dry-run row')}:\n")
        dry_run_output.append_display_data(dry_run_table.head(sample_count))
    else:
        dry_run_output.append_stdout("No dry-run rows to display.\n")
    _invoke_context_callback(context, "refresh_dry_run_export_ui")

# Canonical replacement block source file (overridable from notebook UI).
OFFICIAL_TOU_HTML_FILE = "/Users/davi6569/Documents/GitHub/AGO-item-description-editor/Esri_ToU.html"


def load_official_tou_html(file_path=None):
    """Load canonical ToU HTML text from a file path."""
    path = Path(file_path or OFFICIAL_TOU_HTML_FILE)
    return path.read_text(encoding="utf-8").strip()

# Optional: small direct text/url cleanups as a fallback. Replace the defunct image URL with the approved image URL.
# Add other pairs as needed {target text : replacement text}, but be cautious as this is a blunt replacement that replaces every instance of the target text.
# This is not a comprehensive fix and is only intended to catch the known broken image that might be missed by the main regex-based replacement logic below. 
REPLACEMENT_MAP = {
    "https://downloads.esri.com/blogs/arcgisonline/esrilogo_new.png":"https://www.esri.com/content/dam/esrisites/en-us/common/logos/esri-logo.jpg"
}
# Regex patterns to identify the ToU block and its components for replacement. 
# The main pattern (TOU_BLOCK_RE) looks for a block of HTML that starts with an Esri logo image and contains license text, optionally followed by summary and terms links. 
# The other patterns are used for cleaning up the HTML after replacement to ensure we preserve surrounding content and formatting as much as possible.
SUMMARY_URL_RE = r"(?:goto\.arcgis\.com/termsofuse/viewsummary|links\.esri\.com/e800-summary|links\.esri\.com/tou_summary|downloads2\.esri\.com/ArcGISOnline/docs/tou_summary\.pdf)"
TERMS_URL_RE = r"(?:goto\.arcgis\.com/termsofuse/viewtermsofuse|links\.esri\.com/agol_tou|www\.esri\.com/legal/pdfs/e-800-termsofuse\.pdf|www\.esri\.com/en-us/legal/terms/full-master-agreement|www\.esri\.com/en-us/legal/terms/master-agreement-product)"
LICENSE_TEXT_RE = (
    r"(?:This\s+work\s+is\s+licensed\s+under(?:\s+the)?\s+"
    r"[^<]{0,160}?"
    r"(?:Terms\s+of\s+Use|Master\s+License\s+Agreement)\.?)"
)
LOGO_RE = r"(?:esrilogo_new\.png|esri-logo\.jpg)"

# Default semi-greedy matcher:
# starts at a logo img and scans forward within bounded distance to the
# license text and optional summary/terms links.
# Keeps content before/after untouched while tolerating formatting drift.
TOU_BLOCK_RE = re.compile(
    rf"""(?isx)
    <img\b[^>]*src=['"][^'"]*{LOGO_RE}[^'"]*['"][^>]*>
    [\s\S]{{0,5000}}?
    {LICENSE_TEXT_RE}
    (?:
        [\s\S]{{0,4000}}?
        <a\b[^>]*href=['"][^'"]*{SUMMARY_URL_RE}[^'"]*['"][^>]*>[\s\S]*?</a>
        [\s\S]{{0,2000}}?
        <a\b[^>]*href=['"][^'"]*{TERMS_URL_RE}[^'"]*['"][^>]*>[\s\S]*?</a>
    )?
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# Strict matcher:
# requires the recognized logo, license text, summary link, and terms link
# in the expected order with tighter bounds between segments.
STRICT_TOU_BLOCK_RE = re.compile(
    rf"""(?isx)
    <img\b[^>]*src=['"][^'"]*{LOGO_RE}[^'"]*['"][^>]*>
    [\s\S]{{0,2000}}?
    {LICENSE_TEXT_RE}
    [\s\S]{{0,1500}}?
    <a\b[^>]*href=['"][^'"]*{SUMMARY_URL_RE}[^'"]*['"][^>]*>[\s\S]*?</a>
    [\s\S]{{0,1200}}?
    <a\b[^>]*href=['"][^'"]*{TERMS_URL_RE}[^'"]*['"][^>]*>[\s\S]*?</a>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)
# Patterns for cleaning up around the replacement to preserve surrounding content and formatting
LEADING_EMPTY_WRAPPER_RE = re.compile(
    r"""(?isx)
    ^
    (?:
        \s|
        &nbsp;|
        <br\s*/?>|
        <span\b[^>]*>\s*</span>|
        <span\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</span>|
        <div\b[^>]*>\s*</div>|
        <p\b[^>]*>\s*</p>
    )+
    """
)
# Same as above but for the end of the document
TRAILING_EMPTY_WRAPPER_RE = re.compile(
    r"""(?isx)
    (?:
        \s|
        &nbsp;|
        <br\s*/?>|
        <span\b[^>]*>\s*</span>|
        <span\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</span>|
        <div\b[^>]*>\s*</div>|
        <p\b[^>]*>\s*</p>
    )+
    $
    """
)
# If the canonical block is wrapped only by generic formatting junk, unwrap it and preserve the true surrounding content.
def _build_around_canonical_junk_re(official_html: str):
    return re.compile(
        rf"""(?isx)
        (?P<before>
            (?:<span\b[^>]*>|<div\b[^>]*>|<p\b[^>]*>|\s|&nbsp;|<br\s*/?>)*
        )
        (?P<canon>{re.escape(official_html)})
        (?P<after>
            (?:</span>|</div>|</p>|\s|&nbsp;|<br\s*/?>)*
        )
        """
    )

def cleanup_after_replacement(html_text: str, official_html: str) -> str:
    """Clean up the HTML after replacement to preserve surrounding content and formatting as much as possible.
    This function performs several regex-based cleanups to remove trivial wrappers and preserve true surrounding content around the replaced block.
    
    PARAMS
    html_text: the full HTML text after replacement
    official_html: the canonical replacement block HTML (used to identify the replaced section for cleanup)
    
    RETURNS
    cleaned_html: the cleaned HTML text with preserved surrounding content and formatting
    """
    html_text = html_text.strip()

    # Remove trivial empty wrappers at document edges
    html_text = LEADING_EMPTY_WRAPPER_RE.sub("", html_text)
    html_text = TRAILING_EMPTY_WRAPPER_RE.sub("", html_text)

    # If the canonical block is wrapped only by generic formatting junk,
    # unwrap it and preserve the true surrounding content.
    around_canonical_junk_re = _build_around_canonical_junk_re(official_html)
    html_text = around_canonical_junk_re.sub(official_html, html_text, count=1)

    # Clean a few common leftovers from observed outputs
    html_text = re.sub(r"(?is)</p>\s*</p>", "</p>", html_text)
    html_text = re.sub(r"(?is)(<p>\s*)" + re.escape(official_html), official_html, html_text)
    html_text = re.sub(r"(?is)" + re.escape(official_html) + r"(\s*</div>\s*<div><br\s*/?></div>)", official_html + r"\1", html_text)

    return html_text.strip()

def replace_tou_block(license_html: str, official_html: str, strict_match: bool = False):
    """Replace one or more ToU blocks while preserving surrounding text/html.
    
    PARAMS
    license_html: the original licenseInfo HTML text to search within
    official_html: the canonical ToU block HTML to replace with
    strict_match: if True, require the stricter canonical link structure before replacing
    
    RETURNS
    updated_html: the HTML text after replacement
    n_block: the number of ToU blocks replaced
    """
    if not license_html:
        return license_html, 0

    matcher = STRICT_TOU_BLOCK_RE if strict_match else TOU_BLOCK_RE
    updated, n_block = matcher.subn(official_html, license_html)

    if n_block:
        updated = cleanup_after_replacement(updated, official_html)

    return updated, n_block

def build_licenseinfo_update_plan(matches_df, replacement_tou, max_preview_len=140, strict_match=False):
    """
    Build a dry-run table with old/new licenseInfo and update flags.
    No AGO updates happen here.

    PARAMS
    matches_df: DataFrame of items to consider for update, must contain columns for item_id, title, owner, type, matched_terms, and licenseInfo
    replacement_tou: the new block of HTML that will replace the matching block 
    max_preview_len: maximum number of characters to include in the old/new preview columns (default 140)
    strict_match: if True, only replace canonical Esri ToU blocks that satisfy the stricter matcher

    RETURNS
    plan_df: DataFrame with columns for item_id, title, owner, type, matched_terms, replacements_found, will_update, old_preview, new_preview, old_licenseInfo, new_licenseInfo
    """
    required_cols = {"item_id", "title", "owner", "type", "review_url", "matched_terms", "licenseInfo"}
    missing = required_cols - set(matches_df.columns)
    if missing:
        raise ValueError(f"matches_df is missing columns: {sorted(missing)}")

    rows = []
    for _, row in matches_df.iterrows():
        old_license = row.get("licenseInfo") or ""
        new_license, replacements_found = replace_tou_block(old_license, replacement_tou, strict_match=strict_match)
        will_update = (old_license != new_license)

        rows.append({
            "item_id": row.get("item_id"),
            "title": row.get("title"),
            "owner": row.get("owner"),
            "type": row.get("type"),
            "review_url": row.get("review_url"),
            "thumbnail": row.get("thumbnail") or "",
            "matched_terms": row.get("matched_terms"),
            "replacements_found": replacements_found,
            "will_update": will_update,
            "old_preview": old_license[:max_preview_len].replace("\n", " "),
            "new_preview": new_license[:max_preview_len].replace("\n", " "),
            "old_licenseInfo": old_license,
            "new_licenseInfo": new_license
        })

    return pd.DataFrame(rows)


def show_dry_run(plan_df):
    """
    Display review list only (no updates).

    PARAMS
    plan_df: DataFrame with columns for item_id, title, owner, type, matched_terms, replacements_found, will_update, old_preview, new_preview, old_licenseInfo, new_licenseInfo

    RETURNS
    to_update[display_cols]: a DataFrame filtered to the rows that would be updated.
    """
    to_update = plan_df[plan_df["will_update"] == True].copy()
    display_cols = [
        "item_id", "title", "owner", "type",
        "matched_terms", "replacements_found", "old_preview", "new_preview"
    ]
    return to_update[display_cols]

# =====================================================================
# Report generation functions for item review
# =====================================================================

# Helper function to build a side-by-side HTML report for old vs new ToU for review before actual updates.
def build_side_by_side_report(
    plan_df,
    report_output_path="dry_run_report.html",
    only_updates=True,
    gis=None,
    selection_out_json="selected_item_ids.json"
):
        """Build a HTML report to visualize old vs new ToU side-by-side for review before actual updates.
        
        PARAMS
        plan_df: DataFrame with x columns
        report_output_path: filename for the output HTML report (default "dry_run_report.html")
        only_updates: if True, include only rows where will_update is True (default True)
        gis: optional authenticated GIS object, used to fetch thumbnails as data URIs for inlining; if not provided, thumbnail URLs will be constructed but may not display if authentication is required
        selection_out_json: filename for the output JSON file that will contain the list of selected item IDs

        RETURNS
        report_path: the file path to the generated HTML report
        """
        df = plan_df.copy()

        if only_updates:
                df = df[df["will_update"] == True]

        def safe_text(v):
                return "" if v is None else str(v)

        rows_html = []
        for _, r in df.iterrows():
                item_id = safe_text(r.get("item_id"))
                title = safe_text(r.get("title"))
                owner = safe_text(r.get("owner"))
                item_type = safe_text(r.get("type"))
                review_url = safe_text(r.get("review_url"))
                thumbnail_name = safe_text(r.get("thumbnail"))
                matched_terms = safe_text(r.get("matched_terms"))
                repl = safe_text(r.get("replacements_found"))
                old_html = safe_text(r.get("old_licenseInfo"))
                new_html = safe_text(r.get("new_licenseInfo"))
                old_srcdoc = escape(old_html, quote=True)
                new_srcdoc = escape(new_html, quote=True)

                thumbnail_data_uri = ""
                thumbnail_url = ""
                if gis is not None:
                        thumbnail_data_uri = build_item_thumbnail_data_uri(gis, item_id, thumbnail_name)
                if not thumbnail_data_uri:
                        thumbnail_url = build_item_thumbnail_url(review_url, item_id, thumbnail_name)

                thumb_html = ""
                if thumbnail_data_uri:
                        thumb_html = f'<img class="thumb" src="{escape(thumbnail_data_uri)}" alt="thumbnail" />'
                elif thumbnail_url:
                        thumb_html = f'<img class="thumb" src="{escape(thumbnail_url)}" alt="thumbnail" />'

                searchable = " ".join([item_id, title, owner, item_type, matched_terms]).lower()

                rows_html.append(f"""
                <tr class="review-row" data-search="{escape(searchable, quote=True)}">
                    <td class="meta">
                        <div class="meta-inner">
                            <div class="meta-text">
                                <div><strong>Item:</strong> {escape(item_id)}</div>
                                <div><strong>Title:</strong> {escape(title)}</div>
                                <div><strong>Owner:</strong> {escape(owner)}</div>
                                <div><strong>Type:</strong> {escape(item_type)}</div>
                                <div><strong>Matched:</strong> {escape(matched_terms)}</div>
                                <div><strong>Replacements:</strong> {escape(repl)}</div>
                                <div><a href="{escape(review_url)}" target="_blank">Open item</a></div>
                            </div>
                            <div class="thumb-wrap">{thumb_html}</div>
                        </div>
                    </td>
                    <td>
                        <iframe class="pane" sandbox srcdoc="{old_srcdoc}"></iframe>
                        <details><summary>Old source</summary><pre>{escape(old_html)}</pre></details>
                    </td>
                    <td class="select-cell">
                        <input type="checkbox" class="row-check" data-item-id="{escape(item_id)}">
                    </td>
                    <td>
                        <iframe class="pane" sandbox srcdoc="{new_srcdoc}"></iframe>
                        <details><summary>New source</summary><pre>{escape(new_html)}</pre></details>
                    </td>
                </tr>
                """)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        page = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>LicenseInfo Old vs New</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; margin: 16px; }}
                h1 {{ margin: 0 0 8px 0; }}
                .note {{ color: #555; margin-bottom: 12px; }}
                table {{ width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; }}
                th, td {{ border: 1px solid #ddd; vertical-align: top; padding: 8px; }}
                thead th {{ background: #f7f7f7; position: sticky; top: 0; z-index: 3; }}
                .meta {{ width: 25%; font-size: 13px; line-height: 1.4; position: sticky; left: 0; background: #fff; z-index: 2; }}
                .select-cell {{ width: 85px; text-align: center; position: sticky; left: 25%; background: #fff; z-index: 2; }}
                .select-head {{ width: 85px; text-align: center; position: sticky; left: 25%; z-index: 4; }}
                .meta-inner {{ display: flex; align-items: center; gap: 8px; min-height: 88px; }}
                .meta-text {{ flex: 1 1 auto; min-width: 0; }}
                .thumb-wrap {{ flex: 0 0 auto; margin-left: auto; display: flex; align-items: center; justify-content: flex-end; }}
                .thumb {{ width: 88px; height: 56px; object-fit: cover; border: 1px solid #ddd; border-radius: 4px; background: #fafafa; }}
                .pane {{ width: 100%; height: 220px; border: 1px solid #ccc; background: white; }}
                pre {{ white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow: auto; background: #fafafa; border: 1px solid #eee; padding: 8px; }}
                details {{ margin-top: 6px; }}
                .actions {{ display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap; }}
                .actions button {{ padding: 6px 10px; border: 1px solid #ccc; background: #f7f7f7; border-radius: 4px; cursor: pointer; }}
                .wrap {{ overflow: auto; max-height: calc(100vh - 180px); border: 1px solid #ddd; }}
                @media (max-width: 1400px) {{
                    .meta-inner {{ display: block; min-height: 0; }}
                    .thumb-wrap {{ float: right; margin: 0 0 8px 8px; display: block; }}
                    .meta::after {{ content: ""; display: block; clear: both; }}
                }}
            </style>
        </head>
        <body>
            <h1>LicenseInfo Side-by-Side Review</h1>
            <div class="note">Generated: {escape(ts)} | {escape(count_phrase(len(df), 'row'))}</div>
            <div class="actions">
                <button type="button" onclick="downloadSelectedIdsJson()">Download selected Item IDs (JSON): Upload to Notebook to use</button>
                <button type="button" onclick="downloadSelectedIdsCsv()">Download selected Item IDs (CSV): For review/archive</button>
                <span id="selectedCount">Selected: 0 items</span>
            </div>
            <div class="actions">
                <label>Filter rows: <input id="filterInput" type="text" placeholder="Type item ID, title, owner, or matched term"></label>
                <label>Rows/page:
                    <select id="rowsPerPage">
                        <option value="25">25</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                        <option value="200">200</option>
                    </select>
                </label>
                <button type="button" id="prevPageBtn">Prev</button>
                <button type="button" id="nextPageBtn">Next</button>
                <span id="pageStatus">Page 1 of 1</span>
            </div>
            <div class="wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Old</th>
                            <th class="select-head"><input type="checkbox" id="toggleAll"></th>
                            <th>New</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
            <script>
                const CHECK_CLASS = '.row-check';
                const toggleAllEl = document.getElementById('toggleAll');
                const countEl = document.getElementById('selectedCount');
                const filterEl = document.getElementById('filterInput');
                const rowsPerPageEl = document.getElementById('rowsPerPage');
                const prevPageBtn = document.getElementById('prevPageBtn');
                const nextPageBtn = document.getElementById('nextPageBtn');
                const pageStatusEl = document.getElementById('pageStatus');

                let currentPage = 1;

                function allRows() {{
                    return Array.from(document.querySelectorAll('tr.review-row'));
                }}

                function visibleRows() {{
                    const needle = (filterEl.value || '').trim().toLowerCase();
                    if (!needle) return allRows();
                    return allRows().filter(row => (row.dataset.search || '').includes(needle));
                }}

                function renderPage() {{
                    const rows = allRows();
                    const filtered = visibleRows();
                    const rowsPerPage = Math.max(1, parseInt(rowsPerPageEl.value, 10) || 50);
                    const pageCount = Math.max(1, Math.ceil(filtered.length / rowsPerPage));
                    currentPage = Math.min(Math.max(1, currentPage), pageCount);

                    rows.forEach(row => {{ row.style.display = 'none'; }});
                    const start = (currentPage - 1) * rowsPerPage;
                    const end = start + rowsPerPage;
                    filtered.slice(start, end).forEach(row => {{ row.style.display = ''; }});

                    pageStatusEl.textContent = 'Page ' + currentPage + ' of ' + pageCount + ' (' + filtered.length + ' filtered rows)';
                    prevPageBtn.disabled = currentPage <= 1;
                    nextPageBtn.disabled = currentPage >= pageCount;
                }}

                function getSelectedIds() {{
                    return Array.from(document.querySelectorAll(CHECK_CLASS))
                        .filter(cb => cb.checked)
                        .map(cb => cb.dataset.itemId);
                }}

                function updateSelectedCount() {{
                    const selected = getSelectedIds();
                    countEl.textContent = 'Selected: ' + selected.length + ' ' + (selected.length === 1 ? 'item' : 'items');
                }}

                function syncToggleState() {{
                    const checks = Array.from(document.querySelectorAll(CHECK_CLASS));
                    const checkedCount = checks.filter(cb => cb.checked).length;
                    if (checkedCount === 0) {{
                        toggleAllEl.checked = false;
                        toggleAllEl.indeterminate = false;
                    }} else if (checkedCount === checks.length) {{
                        toggleAllEl.checked = true;
                        toggleAllEl.indeterminate = false;
                    }} else {{
                        toggleAllEl.indeterminate = true;
                    }}
                    updateSelectedCount();
                }}

                function triggerDownload(filename, content, mimeType) {{
                    const blob = new Blob([content], {{ type: mimeType }});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                }}

                function downloadSelectedIdsJson() {{
                    const selected = getSelectedIds();
                    triggerDownload('{escape(selection_out_json)}', JSON.stringify(selected, null, 2), 'application/json');
                }}

                function downloadSelectedIdsCsv() {{
                    const selected = getSelectedIds();
                    const csv = ['item_id', ...selected].join('\\n');
                    triggerDownload('selected_item_ids.csv', csv, 'text/csv;charset=utf-8');
                }}

                toggleAllEl.addEventListener('change', () => {{
                    document.querySelectorAll(CHECK_CLASS).forEach(cb => cb.checked = toggleAllEl.checked);
                    syncToggleState();
                }});

                filterEl.addEventListener('input', () => {{
                    currentPage = 1;
                    renderPage();
                }});

                rowsPerPageEl.addEventListener('change', () => {{
                    currentPage = 1;
                    renderPage();
                }});

                prevPageBtn.addEventListener('click', () => {{
                    currentPage -= 1;
                    renderPage();
                }});

                nextPageBtn.addEventListener('click', () => {{
                    currentPage += 1;
                    renderPage();
                }});

                document.querySelectorAll(CHECK_CLASS).forEach(cb => {{
                    cb.addEventListener('change', syncToggleState);
                }});

                syncToggleState();
                renderPage();
            </script>
        </body>
        </html>
        """

        Path(report_output_path).write_text(page, encoding="utf-8")
        return report_output_path

# =====================================================================
# Update function
# =====================================================================

def apply_updates_btn(_button):
    context = _ctx()
    apply_edits_output = context.get("apply_edits_output")
    selected_ids_to_edit_path_input = context.get("selected_ids_to_edit_path_input")
    apply_edits_confirmation_input = context.get("apply_edits_confirmation_input")
    if apply_edits_output is None or selected_ids_to_edit_path_input is None:
        raise RuntimeError("Filename.json and path must be configured before running the update.")

    apply_edits_output.clear_output()
    if context.get("gis") is None:
        with apply_edits_output:
            print("Please run Step 1: Setup and authenticate first.")
        return

    plan_df = context.get("plan_df")
    if plan_df is None:
        with apply_edits_output:
            print("Build the dry-run plan first.")
        return

    messages = []
    selected_item_ids = context.get("selected_item_ids_for_update")
    selected_path = context.get("selected_item_ids_for_update_path")

    # Backward-compatible behavior: if user did not run the precheck button,
    # load the selection file on demand before executing updates.
    if selected_item_ids is None:
        selected_path = resolve_existing_input_path(selected_ids_to_edit_path_input.value)
        if selected_path is not None:
            try:
                if selected_path.suffix.lower() == ".json":
                    selected_item_ids = json.loads(selected_path.read_text(encoding="utf-8"))
                elif selected_path.suffix.lower() == ".csv":
                    selected_df = pd.read_csv(selected_path, dtype=str)
                    if "item_id" in selected_df.columns:
                        selected_item_ids = selected_df["item_id"].dropna().astype(str).tolist()
                if selected_item_ids is not None:
                    messages.append(
                        f"Loaded {count_phrase(len(selected_item_ids), 'item ID', 'item IDs')} "
                        f"from {selected_path}"
                    )
            except Exception as exc:
                messages.append(f"Could not load selected IDs file ({selected_path}): {exc}")
                messages.append("Continuing without a selection filter.")
                selected_item_ids = None
        else:
            messages.append("No selected IDs file was found. Applying updates to all rows where will_update=True.")
    elif selected_path is not None:
        messages.append(
            f"Using preloaded selection from {selected_path} "
            f"({count_phrase(len(selected_item_ids), 'item ID', 'item IDs')})."
        )

    with apply_edits_output:
        print("Execute update summary")
        for line in messages:
            print(f"- {line}")
        print("Applying updates now...")

    with redirect_stdout(_OutputWidgetStdoutProxy(apply_edits_output)):
        success_df, update_errors_df = apply_licenseinfo_updates(
            context["gis"],
            plan_df,
            require_phrase="APPLY UPDATES",
            pause_seconds=0.0,
            selected_item_ids=selected_item_ids,
            confirmation_text=(apply_edits_confirmation_input.value if apply_edits_confirmation_input is not None else None),
        )
    context["success_df"] = success_df
    context["update_errors_df"] = update_errors_df
    with apply_edits_output:
        print(
            f"Update attempt complete: {count_phrase(len(success_df), 'success')} | "
            f"{count_phrase(len(update_errors_df), 'error')}"
        )
        if not success_df.empty:
            sample_count = min(len(success_df), 3)
            print(f"Showing {count_phrase(sample_count, 'sample edit result')}:")
            display(success_df.head(sample_count))
        else:
            print("No successful updates to display.")


def load_update_selection_btn(_button):
    """Step 6 precheck: load selection file and preview update count before execute."""
    context = _ctx()
    apply_edits_output = context.get("apply_edits_output")
    selected_ids_to_edit_path_input = context.get("selected_ids_to_edit_path_input")
    if apply_edits_output is None or selected_ids_to_edit_path_input is None:
        raise RuntimeError("Step 6 selection input and output must be configured.")

    apply_edits_output.clear_output()
    if context.get("gis") is None:
        with apply_edits_output:
            print("Please run Step 1: Setup and authenticate first.")
        return

    plan_df = context.get("plan_df")
    if plan_df is None:
        with apply_edits_output:
            print("Build the dry-run plan first.")
        return

    messages = []
    selected_item_ids = None
    selected_path = resolve_existing_input_path(selected_ids_to_edit_path_input.value)
    if selected_path is not None:
        try:
            if selected_path.suffix.lower() == ".json":
                selected_item_ids = json.loads(selected_path.read_text(encoding="utf-8"))
            elif selected_path.suffix.lower() == ".csv":
                selected_df = pd.read_csv(selected_path, dtype=str)
                if "item_id" in selected_df.columns:
                    selected_item_ids = selected_df["item_id"].dropna().astype(str).tolist()

            if selected_item_ids is not None:
                messages.append(
                    f"Loaded {count_phrase(len(selected_item_ids), 'item ID', 'item IDs')} "
                    f"from {selected_path}"
                )
        except Exception as exc:
            messages.append(f"Could not load selected IDs file ({selected_path}): {exc}")
            messages.append("Continuing without a selection filter.")
            selected_item_ids = None
    else:
        messages.append("No selected IDs file was found. Applying updates to all candidate items.")

    to_update = plan_df[plan_df["will_update"] == True].copy()
    initial_count = len(to_update)
    if selected_item_ids is not None:
        selected_set = {str(x) for x in selected_item_ids if str(x).strip()}
        to_update = to_update[to_update["item_id"].astype(str).isin(selected_set)].copy()
        messages.append(f"Selection filter applied. {count_phrase(len(to_update), 'row')} selected for update.")

    context["selected_item_ids_for_update"] = selected_item_ids
    context["selected_item_ids_for_update_path"] = str(selected_path) if selected_path is not None else None

    with apply_edits_output:
        print("Precheck summary")
        for line in messages:
            print(f"- {line}")

        if to_update.empty:
            print("Nothing to update.")
            return

        print(f"WARNING: You are about to edit {count_phrase(len(to_update), 'item')}.")
        print("Type APPLY UPDATES in the confirmation field, then click Execute update.")
        print("Basic details of the first several rows to be updated:")
        preview = to_update[["item_id", "title", "owner", "type"]].head(3).reset_index(drop=True)
        preview.index += 1
        display(preview)

# Function to apply the updates to AGO items. Accidental execution of this function is protected by a required input phrase "APPLY UPDATES"
def apply_licenseinfo_updates(
    gis,
    plan_df,
    require_phrase="APPLY UPDATES",
    pause_seconds=0.0,
    selected_item_ids=None,
    confirmation_text=None,
):
    """
    Apply updates to AGO items, but only after explicit confirmation input.

    PARAMS
    gis: authenticated GIS object
    plan_df: input DataFrame
    require_phrase: the exact phrase that the user must type to confirm updates (default "APPLY UPDATES")
    pause_seconds: number of seconds to pause between item update requests (default 0, can be used to avoid hitting rate limits)

    RETURNS
    success_df: DataFrame of successfully updated items with columns for item_id, title, owner, and type
    errors_df: DataFrame of any errors encountered during updates with columns for item_id, title, and error message
    """
    to_update = plan_df[plan_df["will_update"] == True].copy()

    if selected_item_ids is not None:
        selected_set = {str(x) for x in selected_item_ids if str(x).strip()}
        to_update = to_update[to_update["item_id"].astype(str).isin(selected_set)].copy()
        print(f"Selection filter applied. {count_phrase(len(to_update), 'row')} selected for update.")

    if to_update.empty:
        print("Nothing to update.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"WARNING: You are about to update {count_phrase(len(to_update), 'item')}.")
    print(f"If you want to continue, type {require_phrase}. Type anything else to cancel.")

    if confirmation_text is not None:
        typed = str(confirmation_text).strip()
    else:
        try:
            typed = input("Confirm: ").strip()
        except EOFError:
            print("Update canceled: this notebook runtime does not support interactive input() from button callbacks.")
            print(f"Use the confirmation input field and type exactly: {require_phrase}")
            return pd.DataFrame(), pd.DataFrame()

    if typed != require_phrase:
        print("Update canceled.")
        return pd.DataFrame(), pd.DataFrame()

    success_rows = []
    error_rows = []

    for i, row in enumerate(to_update.itertuples(index=False), start=1):
        item_id = row.item_id
        try:
            item = gis.content.get(item_id)
            if item is None:
                raise ValueError("Item not found")

            ok = item.update(item_properties={"licenseInfo": row.new_licenseInfo})
            if not ok:
                raise RuntimeError("item.update returned False")

            success_rows.append({
                "item_id": item_id,
                "title": row.title,
                "owner": row.owner,
                "type": row.type
            })

        except Exception as exc:
            error_rows.append({
                "item_id": item_id,
                "title": getattr(row, "title", None),
                "error": str(exc)
            })

        if pause_seconds:
            time.sleep(pause_seconds)

        if i % 50 == 0:
            print(f"Processed {i} of {len(to_update)} updates")

    success_df = pd.DataFrame(success_rows)
    errors_df = pd.DataFrame(error_rows)

    print(
        f"Update results: {count_phrase(len(success_df), 'success')} | "
        f"{count_phrase(len(errors_df), 'error')}"
    )
    return success_df, errors_df