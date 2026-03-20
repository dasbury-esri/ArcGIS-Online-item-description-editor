# ======================================================================
# Helper functions for AGO Item Description Editor notebook
# ======================================================================

import os, sys, re, uuid, json, math, tempfile, requests, traceback, base64, ast, csv, io
import ipywidgets as widgets # type: ignore
from IPython.display import display, HTML
from pathlib import Path
import arcgis, time, re
from arcgis.gis import GIS
import pandas as pd
from html import escape
from datetime import datetime
from urllib.parse import urlparse, quote

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

OUTPUT_DIR_NAME = "ago_item_description_editor_outputs"


def _default_output_root():
    if current_env == "arcgisnotebook" and Path("/arcgis/home").exists():
        return Path("/arcgis/home")
    return Path.cwd()


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


def build_notebook_file_link(path, label):
    resolved_path = Path(path).resolve()
    href = resolved_path.as_uri()

    try:
        relative_path = resolved_path.relative_to(Path.cwd())
    except ValueError:
        relative_path = None

    if current_env in {"arcgisnotebook", "jupyterlab", "classicjupyter"} and relative_path is not None:
        href = f"files/{quote(relative_path.as_posix())}"

    safe_href = escape(href, quote=True)
    safe_label = escape(label)
    return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_label}</a>'


def count_phrase(count, singular, plural=None):
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"

# ======================================================================
# Authentication for different environments
# ======================================================================

def authenticate_gis(context, portal_url="https://www.arcgis.com", client_id=None):
    """
    Authenticate to ArcGIS Online or Enterprise. Falls back to username/password
    """
    import ipywidgets as widgets # type: ignore
    from IPython.display import display
    from arcgis.gis import GIS # type: ignore

    def finish_auth(gis):
        context["gis"] = gis
        print(f"Authenticated as: {context['gis'].properties.user.username} (role: {context['gis'].properties.user.role} / userType: {context['gis'].properties.user.userLicenseTypeId})")
        print("\nStep 1 is complete. Continue to the next step when you are ready.")

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
        with output:
            output.clear_output()
            print("Logging in...")
            try:
                gis = GIS(portal_url, username_widget.value, password_widget.value)
                finish_auth(gis)
            except Exception as e:
                print(f"Login failed: {e}")

    login_button.on_click(handle_login)
    display(widgets.VBox([username_widget, password_widget, login_button, output]))

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
    
def setup_notebook_btn(button):
    context = _ctx()
    output1 = context.get("output1")
    if output1 is None:
        raise RuntimeError("context['output1'] is not configured.")

    with output1:
        output1.clear_output()
        print("Setting up the notebook environment...")
        print(f"\tPython version: {sys.version}")
        print(f"\tArcGIS for Python API version: {arcgis.__version__}")
        authenticate_gis(context=context)
        if context.get("gis") is not None:
            print("Authentication complete.")
    
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
    output2 = context.get("output2")
    input2 = context.get("input2")
    if output2 is None or input2 is None:
        raise RuntimeError("context['output2'] and context['input2'] must be configured.")

    with output2:
        output2.clear_output()
        if context.get("gis") is None:
            print("Please run Step 1: Setup and authenticate first.")
            return

        terms = parse_target_terms(input2.value)
        if not terms:
            print("No search terms provided.")
            return

        input2.value = normalize_target_terms_text(terms)

        print(f"Running scan with {count_phrase(len(terms), 'term')}...")
        matches_df, errors_df, all_items_df = scan_org_licenseinfo_without_10k_cap(
            context["gis"],
            target_strings=terms,
        )
        context["matches_df"] = matches_df
        context["errors_df"] = errors_df
        context["all_items_df"] = all_items_df
        context["TARGET_STRINGS"] = terms

        print(
            f"Scan results: {count_phrase(len(matches_df), 'match')} | "
            f"{count_phrase(len(errors_df), 'error')}"
        )
        sample_count = min(len(matches_df), 3)
        if sample_count:
            print(f"Showing {count_phrase(sample_count, 'sample match')}:")
            display(matches_df.head(sample_count))
        else:
            print("No sample matches to display.")


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


def get_all_items_for_user(gis, username, user_idx=None, page_size=25, progress_every=25):
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
        folder_id = folder.get("id")
        if not folder_id:
            continue

        start = 1
        while True:
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

def scan_org_licenseinfo_without_10k_cap(gis, target_strings=None, pause_seconds=0.0, exclude_item_ids=None):
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

    usernames = get_all_org_usernames(gis)
    print(f"Users found: {count_phrase(len(usernames), 'user')}")

    matches = []
    errors = []
    all_seen = set()
    total_scanned = 0
    total_skipped_excluded = 0

    for u_idx, username in enumerate(usernames, start=1):
        try:
            items = get_all_items_for_user(
                gis,
                username,
                user_idx=u_idx,
                page_size=100,
                progress_every=25
            )

            for item in items:
                item_id = str(item.get("id") or "")
                if not item_id or item_id in all_seen:
                    continue
                all_seen.add(item_id)

                if item_id in exclude_set:
                    total_skipped_excluded += 1
                    continue

                license_info = item.get("licenseInfo") or ""
                li_lower = license_info.lower()
                access = (item.get("access") or "").lower()

                matched = [term for term in target_strings if term.lower() in li_lower]
                if matched:
                    public_url, portal_url = build_item_urls(gis, item_id, access)
                    matches.append({
                        "item_id": item_id,
                        "title": item.get("title"),
                        "owner": item.get("owner"),
                        "type": item.get("type"),
                        "access": access,
                        "public_url": public_url,
                        "portal_url": portal_url,
                        "thumbnail": item.get("thumbnail") or "",
                        "matched_terms": ", ".join(matched),
                        "licenseInfo": license_info
                    })

                total_scanned += 1
                if pause_seconds:
                    time.sleep(pause_seconds)

            if u_idx % 25 == 0:
                print(
                    f"Processed {u_idx} of {len(usernames)} users | "
                    f"{count_phrase(len(all_seen), 'unique item')} seen | "
                    f"{count_phrase(total_scanned, 'item')} scanned after exclusions | "
                    f"{count_phrase(total_skipped_excluded, 'item')} excluded"
                )

        except Exception as exc:
            errors.append({
                "username": username,
                "error": str(exc)
            })
    matches_df = pd.DataFrame(matches)
    errors_df = pd.DataFrame(errors, columns=["username", "error"])
    all_items_df = pd.DataFrame({"item_id": list(all_seen)})

    # Add a column to matches_df that uses the public_url if available, otherwise falls back to the portal_url
    if not matches_df.empty:
        matches_df["review_url"] = matches_df["public_url"].fillna(matches_df["portal_url"])
    else:
        matches_df = pd.DataFrame(columns=[
            "item_id","title","owner","type","access",
            "public_url","portal_url","review_url","thumbnail",
            "matched_terms","licenseInfo"
        ])

    print(f"\n*** Done! ***")
    print(f"Unique items found: {count_phrase(len(all_seen), 'item')}")
    print(f"Items excluded from previous run: {count_phrase(total_skipped_excluded, 'item')}")
    print(f"Items scanned: {count_phrase(total_scanned, 'item')}")

    return matches_df, errors_df, all_items_df

def run_secondary_scan_btn(button):
    context = _ctx()
    output5 = context.get("output5")
    checkbox5 = context.get("checkbox5")
    input5 = context.get("input5")
    if output5 is None or checkbox5 is None or input5 is None:
        raise RuntimeError("context['output5'], context['checkbox5'], and context['input5'] must be configured.")

    with output5:
        output5.clear_output()

        if not checkbox5.value:
            print("Secondary scan is disabled. Select the checkbox above to run it.")
            return

        if context.get("gis") is None:
            print("Please run Step 1: Setup and authenticate first.")
            return

        matches_df = context.get("matches_df")
        if matches_df is not None and not matches_df.empty:
            exclude_ids = set(matches_df["item_id"].dropna().astype(str))
        else:
            previous_matches_path = resolve_existing_input_path("scan_matches.csv")
            if previous_matches_path is not None:
                previous_matches_df = pd.read_csv(previous_matches_path, dtype={"item_id": str})
                exclude_ids = set(previous_matches_df["item_id"].dropna().astype(str))
            else:
                exclude_ids = set()

        new_terms = parse_target_terms(input5.value)
        if not new_terms:
            print("No new search terms provided.")
            return

        input5.value = normalize_target_terms_text(new_terms)

        print(f"Running secondary scan with {count_phrase(len(new_terms), 'term')}...")
        new_matches_df, new_errors_df, new_all_items_df = scan_org_licenseinfo_without_10k_cap(
            context["gis"],
            target_strings=new_terms,
            exclude_item_ids=exclude_ids,
        )

        if not new_matches_df.empty and exclude_ids:
            new_matches_df = new_matches_df[~new_matches_df["item_id"].isin(exclude_ids)].copy()

        secondary_output_path = resolve_output_path("secondary_scan_matches.csv", "secondary_scan_matches.csv")
        new_matches_df.to_csv(secondary_output_path, index=False)

        context["new_matches_df"] = new_matches_df
        context["new_errors_df"] = new_errors_df
        context["new_all_items_df"] = new_all_items_df

        print(
            f"Secondary scan results: {count_phrase(len(new_matches_df), 'new match')} | "
            f"{count_phrase(len(new_errors_df), 'error')}"
        )
        print(f"Saved secondary scan matches to: {secondary_output_path}")
        display(new_matches_df.head(20))

# =====================================================================
# File handling
# =====================================================================

def save_scan_outputs_btn(button):
    context = _ctx()
    output3 = context.get("output3")
    input3_matches = context.get("input3_matches")
    input3_errors = context.get("input3_errors")
    input3_all_items = context.get("input3_all_items")
    if output3 is None:
        raise RuntimeError("context['output3'] is not configured.")

    with output3:
        output3.clear_output()
        matches_df = context.get("matches_df")
        errors_df = context.get("errors_df")
        all_items_df = context.get("all_items_df")
        if matches_df is None or errors_df is None or all_items_df is None:
            print("Run Step 2 or load saved scan files first.")
            return

        matches_path = resolve_output_path(
            input3_matches.value if input3_matches is not None else None,
            "scan_matches.csv",
        )
        errors_path = resolve_output_path(
            input3_errors.value if input3_errors is not None else None,
            "scan_errors.csv",
        )
        all_items_path = resolve_output_path(
            input3_all_items.value if input3_all_items is not None else None,
            "scan_all_items.csv",
        )

        matches_df.to_csv(matches_path, index=False)
        errors_df.to_csv(errors_path, index=False)
        all_items_df.to_csv(all_items_path, index=False)
        print("Saved files:")
        print(f"- {matches_path}")
        print(f"- {errors_path}")
        print(f"- {all_items_path}")

def export_dry_run_btn(_button):
    context = _ctx()
    output8 = context.get("output8")
    if output8 is None:
        raise RuntimeError("context['output8'] is not configured.")

    with output8:
        output8.clear_output()
        plan_df = context.get("plan_df")
        if plan_df is None:
            print("Build the dry-run plan first.")
            return

        input8_csv_name = context.get("input8_csv_name")
        csv_name = "dry_run_results.csv"
        if input8_csv_name is not None:
            entered = (input8_csv_name.value or "").strip()
            if entered:
                csv_name = entered
        if not csv_name.lower().endswith(".csv"):
            csv_name = f"{csv_name}.csv"

        csv_path = resolve_output_path(csv_name, "dry_run_results.csv")
        plan_df.to_csv(csv_path, index=False)
        print(f"Saved file: {csv_path}")

def create_report_btn(_button):
    context = _ctx()
    output9 = context.get("output9")
    input9_report_name = context.get("input9_report_name")
    input9_selection_json = context.get("input9_selection_json")
    if output9 is None:
        raise RuntimeError("context['output9'] is not configured.")

    with output9:
        output9.clear_output()
        plan_df = context.get("plan_df")
        if plan_df is None:
            print("Build the dry-run plan before creating the report.")
            return

        report_filename = "dry_run_report.html"
        if input9_report_name is not None and (input9_report_name.value or "").strip():
            report_filename = input9_report_name.value.strip()
        if not report_filename.lower().endswith(".html"):
            report_filename = f"{report_filename}.html"

        selection_json_name = "selected_item_ids.json"
        if input9_selection_json is not None and (input9_selection_json.value or "").strip():
            selection_json_name = input9_selection_json.value.strip()
        if not selection_json_name.lower().endswith(".json"):
            selection_json_name = f"{selection_json_name}.json"

        report_path = build_side_by_side_report(
            plan_df,
            report_output_path=str(resolve_output_path(report_filename, "dry_run_report.html")),
            only_updates=True,
            gis=context.get("gis"),
            selection_out_json=Path(selection_json_name).name,
        )
        context["report_path"] = report_path
        print(f"Report saved to: {report_path}")
        display(HTML(f"<div>{build_notebook_file_link(report_path, 'Open report in browser')}</div>"))
        print(f"Selected item IDs will download from the report as: {Path(selection_json_name).name}")
        print("\nIn the report, choose rows with the checkboxes and click 'Download selected Item IDs (JSON)'.")
        print("Then upload or copy that file into the notebook environment before running Step 10.")

def export_final_results_btn(_button):
    context = _ctx()
    output11 = context.get("output11")
    input11_success_csv = context.get("input11_success_csv")
    input11_errors_csv = context.get("input11_errors_csv")
    if output11 is None:
        raise RuntimeError("context['output11'] is not configured.")

    with output11:
        output11.clear_output()
        success_df = context.get("success_df")
        update_errors_df = context.get("update_errors_df")
        if success_df is None or update_errors_df is None:
            print("Run Step 10 first to create the export data.")
            return

        success_path = resolve_output_path(
            input11_success_csv.value if input11_success_csv is not None else None,
            "update_successes.csv",
        )
        errors_path = resolve_output_path(
            input11_errors_csv.value if input11_errors_csv is not None else None,
            "update_errors.csv",
        )

        success_df.to_csv(success_path, index=False)
        update_errors_df.to_csv(errors_path, index=False)
        print("Saved files:")
        print(f"- {success_path}")
        print(f"- {errors_path}")

# =====================================================================
# Strict match filter
# =====================================================================

def run_strict_match_filter_btn(_button):
    context = _ctx()
    output6 = context.get("output6")
    input6 = context.get("input6")
    if output6 is None or input6 is None:
        raise RuntimeError("context['output6'] and context['input6'] must be configured.")

    with output6:
        output6.clear_output()
        matches_df = context.get("matches_df")
        if matches_df is None:
            print("Run Step 2 or load saved scan files first.")
            return

        exact_term = (input6.value or "").strip()
        if not exact_term:
            print("Enter exact text to filter the results.")
            return

        exact_url_df = matches_df[
            matches_df["matched_terms"].str.contains(
                exact_term,
                case=False,
                na=False,
            )
        ].copy()
        context["exact_url_df"] = exact_url_df

        print(f"Exact-match results: {count_phrase(len(exact_url_df), 'item')}")
        display(exact_url_df.head(50))

# =====================================================================
# Dry run functions
# =====================================================================

def dry_run_btn(_button):
    context = _ctx()
    output7 = context.get("output7")
    if output7 is None:
        raise RuntimeError("context['output7'] is not configured.")

    with output7:
        output7.clear_output()
        matches_df = context.get("matches_df")
        if matches_df is None:
            print("Run Step 2 or load saved scan files first.")
            return

        tou_path = context.get("official_tou_html_file", OFFICIAL_TOU_HTML_FILE)
        replacement_tou = load_official_tou_html(tou_path)
        plan_df = build_licenseinfo_update_plan(matches_df, replacement_tou)
        dry_run_table = show_dry_run(plan_df, max_rows=200)
        context["plan_df"] = plan_df
        context["dry_run_table"] = dry_run_table
        print("Showing up to 3 rows from the dry-run plan:")
        display(dry_run_table[:3])

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

# Core matcher:
# starts at a logo img and ends at the "View Terms of Use" link anchor.
# Keeps content before/after untouched.
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

def replace_tou_block(license_html: str, official_html: str):
    """Replace one or more ToU blocks while preserving surrounding text/html.
    
    PARAMS
    license_html: the original licenseInfo HTML text to search within
    official_html: the canonical ToU block HTML to replace with
    
    RETURNS
    updated_html: the HTML text after replacement
    n_block: the number of ToU blocks replaced
    """
    if not license_html:
        return license_html, 0

    updated, n_block = TOU_BLOCK_RE.subn(official_html, license_html)

    if n_block:
        updated = cleanup_after_replacement(updated, official_html)

    return updated, n_block

def build_licenseinfo_update_plan(matches_df, replacement_tou, max_preview_len=140):
    """
    Build a dry-run table with old/new licenseInfo and update flags.
    No AGO updates happen here.

    PARAMS
    matches_df: DataFrame of items to consider for update, must contain columns for item_id, title, owner, type, matched_terms, and licenseInfo
    replacement_tou: the new block of HTML that will replace the matching block 
    max_preview_len: maximum number of characters to include in the old/new preview columns (default 140)

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
        new_license, replacements_found = replace_tou_block(old_license, replacement_tou)
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


def show_dry_run(plan_df, max_rows=50):
    """
    Display review list only (no updates).

    PARAMS
    plan_df: DataFrame with columns for item_id, title, owner, type, matched_terms, replacements_found, will_update, old_preview, new_preview, old_licenseInfo, new_licenseInfo
    max_rows: maximum number of rows to display in the review table (default 50)

    RETURNS
    to_update[display_cols]: a DataFrame filtered to the rows that would be updated.
    """
    to_update = plan_df[plan_df["will_update"] == True].copy()
    print(
        f"Dry-run summary: {count_phrase(len(plan_df), 'matched row')}, "
        f"{count_phrase(len(to_update), 'row')} would be updated."
    )
    display_cols = [
        "item_id", "title", "owner", "type",
        "matched_terms", "replacements_found", "old_preview", "new_preview"
    ]
    return to_update[display_cols].head(max_rows)

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

                rows_html.append(f"""
                <tr>
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
                        <input type="checkbox" class="row-check" data-item-id="{escape(item_id)}" checked>
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
            <div class="wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Old</th>
                            <th class="select-head"><input type="checkbox" id="toggleAll" checked></th>
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

                document.querySelectorAll(CHECK_CLASS).forEach(cb => {{
                    cb.addEventListener('change', syncToggleState);
                }});

                syncToggleState();
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
    output10 = context.get("output10")
    input10_ids = context.get("input10_ids")
    input10_confirm = context.get("input10_confirm")
    if output10 is None or input10_ids is None:
        raise RuntimeError("Filename.json and path must be configured before running the update.")

    with output10:
        output10.clear_output()
        if context.get("gis") is None:
            print("Please run Step 1: Setup and authenticate first.")
            return

        plan_df = context.get("plan_df")
        if plan_df is None:
            print("Build the dry-run plan first.")
            return

        selected_item_ids = None
        selected_path = resolve_existing_input_path(input10_ids.value)
        if selected_path is not None:
            try:
                if selected_path.suffix.lower() == ".json":
                    selected_item_ids = json.loads(selected_path.read_text(encoding="utf-8"))
                elif selected_path.suffix.lower() == ".csv":
                    selected_df = pd.read_csv(selected_path, dtype=str)
                    if "item_id" in selected_df.columns:
                        selected_item_ids = selected_df["item_id"].dropna().astype(str).tolist()
                if selected_item_ids is not None:
                    print(
                        f"Loaded {count_phrase(len(selected_item_ids), 'item ID', 'item IDs')} "
                        f"from {selected_path}"
                    )
            except Exception as exc:
                print(f"Could not load selected IDs file ({selected_path}): {exc}")
                print("Continuing without a selection filter.")
                selected_item_ids = None
        else:
            print("No selected IDs file was found. Applying updates to all rows where will_update=True.")

        success_df, update_errors_df = apply_licenseinfo_updates(
            context["gis"],
            plan_df,
            require_phrase="APPLY UPDATES",
            pause_seconds=0.0,
            selected_item_ids=selected_item_ids,
            confirmation_text=(input10_confirm.value if input10_confirm is not None else None),
        )
        context["success_df"] = success_df
        context["update_errors_df"] = update_errors_df
        if not success_df.empty:
            display(success_df.head(20))
        else:
            print("No successful updates to display.")

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