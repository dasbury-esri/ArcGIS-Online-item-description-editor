# ======================================================================
# Helper functions for AGO Item Description Editor notebook
# ======================================================================

import os, re, uuid, json, math, tempfile, requests, traceback
import ipywidgets as widgets # type: ignore
from IPython.display import display, HTML
from pathlib import Path
import arcgis, time, re
from arcgis.gis import GIS
import pandas as pd
from html import escape
from datetime import datetime

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

# Define base directory to store notebook data
BASE_DIR = Path.home() / "conversion_data"
# When debugging locally, 
if current_env == "vscode":
    BASE_DIR = Path.cwd() / "_local_testing"
# Ensure the directory exists
BASE_DIR.mkdir(parents=True, exist_ok=True)

# ======================================================================
# Authentification for different environments
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
        print("\nStep #1 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")


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
        return widgets.Checkbox(value=value if value is not None else False, description=description, layout=layout)
    elif widget_type == "text":
        return widgets.Text(value=value if value is not None else "", placeholder=placeholder if placeholder is not None else "", description=description, layout=layout)
    elif widget_type == "label":
        return widgets.Label(value=value if value is not None else "", layout=layout)
    elif widget_type == "output":
        return widgets.Output()
    elif widget_type == "hbox":
        # expects elements to be a list of widgets
        return widgets.HBox(elements if elements else [])
    elif widget_type == "textarea":
    # Support multi-line input
        return widgets.Textarea(value=value or "", description=description or "", placeholder=placeholder or "", layout=layout)
    else:
        raise ValueError("Unsupported widget_type")
    
# ======================================================================
# Org scanning functions that avoid 10k search cap by paging through users/folders/items
# ======================================================================

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
        line = f"{prefix} Found {found} items"
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
    print(f"Users found: {len(usernames)}")

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
                        "matched_terms": ", ".join(matched),
                        "licenseInfo": license_info
                    })

                total_scanned += 1
                if pause_seconds:
                    time.sleep(pause_seconds)

            if u_idx % 25 == 0:
                print(
                    f"Processed users: {u_idx}/{len(usernames)} | "
                    f"unique seen: {len(all_seen)} | "
                    f"scanned after exclusions: {total_scanned} | "
                    f"excluded: {total_skipped_excluded}"
                )

        except Exception as exc:
            errors.append({
                "username": username,
                "error": str(exc)
            })
    matches_df = pd.DataFrame(matches)
    errors_df = pd.DataFrame(errors)
    all_items_df = pd.DataFrame({"item_id": list(all_seen)})

    # Add a column to matches_df that uses the public_url if available, otherwise falls back to the portal_url
    if not matches_df.empty:
        matches_df["review_url"] = matches_df["public_url"].fillna(matches_df["portal_url"])
    else:
        matches_df = pd.DataFrame(columns=[
            "item_id","title","owner","type","access",
            "public_url","portal_url","review_url",
            "matched_terms","licenseInfo"
        ])

    print(f"Done. Unique items seen: {len(all_seen)}")
    print(f"Excluded from matching: {total_skipped_excluded}")
    print(f"Scanned after exclusions: {total_scanned}")
    print(f"Matches found: {len(matches_df)}")
    print(f"User-level errors: {len(errors_df)}")

    return matches_df, errors_df, all_items_df

# =====================================================================
# Dry run functions
# =====================================================================

# Load canonical replacement block
OFFICIAL_TOU_HTML = Path("AGSM_Esri_ToU_official.html").read_text(encoding="utf-8").strip()

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
AROUND_CANONICAL_JUNK_RE = re.compile(
    rf"""(?isx)
    (?P<before>
        (?:<span\b[^>]*>|<div\b[^>]*>|<p\b[^>]*>|\s|&nbsp;|<br\s*/?>)*
    )
    (?P<canon>{re.escape(OFFICIAL_TOU_HTML)})
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
    html_text = AROUND_CANONICAL_JUNK_RE.sub(official_html, html_text, count=1)

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
    print(f"Dry-run summary: {len(plan_df)} matched rows, {len(to_update)} rows would be updated.")
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
    out_html="tou_side_by_side_report.html",
    only_updates=True,
    max_rows=200
):
    """Build a HTML report to visualize old vs new ToU side-by-side for review before actual updates.
    
    PARAMS
    plan_df: DataFrame with columns for item_id, title, owner, type, matched_terms, replacements_found, will_update, old_preview, new_preview, old_licenseInfo, new_licenseInfo
    out_html: output HTML file path (default "tou_side_by_side_report.html")
    only_updates: if True, include only rows that will be updated (default True)
    max_rows: maximum number of rows to include in the report (default 200)

    RETURNS
    out_html: the file path of the generated HTML report
    """    
    df = plan_df.copy()

    if only_updates:
        df = df[df["will_update"] == True]

    if max_rows is not None:
        df = df.head(max_rows)

    def safe_text(v):
        """ Convert a value to a string for HTML display, treating None as an empty string.
        This ensures that missing values don't show up as 'None' in the report.
        
        PARAMS
        v: the value to convert to string

        RETURNS
        str: the converted string value
        """
        return "" if v is None else str(v)

    rows_html = []
    # Iterate over the DataFrame rows and build HTML for each item, showing metadata and old/new licenseInfo side by side with iframes and details blocks for full text.
    for _, r in df.iterrows():
        item_id = safe_text(r.get("item_id"))
        title = safe_text(r.get("title"))
        owner = safe_text(r.get("owner"))
        item_type = safe_text(r.get("type"))
        review_url = safe_text(r.get("review_url"))
        matched_terms = safe_text(r.get("matched_terms"))
        repl = safe_text(r.get("replacements_found"))
        old_html = safe_text(r.get("old_licenseInfo"))
        new_html = safe_text(r.get("new_licenseInfo"))
        old_srcdoc = escape(old_html, quote=True)
        new_srcdoc = escape(new_html, quote=True)
        # Build a table row for this item with metadata in the first column, old licenseInfo in the second column, and new licenseInfo in the third column. 
        # Use iframes to show the old/new licenseInfo side by side, and an expandable details block to show the full HTML source for each.
        rows_html.append(f"""
        <tr>
          <td class="meta">
            <div><strong>Item:</strong> {escape(item_id)}</div>
            <div><strong>Title:</strong> {escape(title)}</div>
            <div><strong>Owner:</strong> {escape(owner)}</div>
            <div><strong>Type:</strong> {escape(item_type)}</div>
            <div><strong>Matched:</strong> {escape(matched_terms)}</div>
            <div><strong>Replacements:</strong> {escape(repl)}</div>
            <div><a href="{escape(review_url)}" target="_blank">Open item</a></div>
          </td>
          <td>
            <iframe class="pane" sandbox srcdoc="{old_srcdoc}"></iframe>
            <details><summary>Old source</summary><pre>{escape(old_html)}</pre></details>
          </td>
          <td>
            <iframe class="pane" sandbox srcdoc="{new_srcdoc}"></iframe>
            <details><summary>New source</summary><pre>{escape(new_html)}</pre></details>
          </td>
        </tr>
        """)
    # Create a date-time stamp for when the report was generated
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Build the full HTML page with a table containing all the rows, and include some basic styling for readability.
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
        table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
        th, td {{ border: 1px solid #ddd; vertical-align: top; padding: 8px; }}
        th {{ background: #f7f7f7; position: sticky; top: 0; z-index: 1; }}
        .meta {{ width: 25%; font-size: 13px; line-height: 1.4; }}
        .pane {{ width: 100%; height: 220px; border: 1px solid #ccc; background: white; }}
        pre {{ white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow: auto; background: #fafafa; border: 1px solid #eee; padding: 8px; }}
        details {{ margin-top: 6px; }}
        .wrap {{ overflow-x: auto; }}
      </style>
    </head>
    <body>
      <h1>LicenseInfo Side-by-Side Review</h1>
      <div class="note">Generated: {escape(ts)} | Rows: {len(df)} | only_updates={only_updates}</div>
      <div class="wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Old</th>
              <th>New</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows_html)}
          </tbody>
        </table>
      </div>
    </body>
    </html>
    """

    Path(out_html).write_text(page, encoding="utf-8")
    print(f"Wrote report: {out_html}")
    return out_html

# =====================================================================
# Update function
# =====================================================================

# Function to apply the updates to AGO items. Accidental execution of this function is protected by a required input phrase "APPLY UPDATES"
def apply_licenseinfo_updates(gis, plan_df, require_phrase="APPLY UPDATES", pause_seconds=0.0):
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

    if to_update.empty:
        print("Nothing to update.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"WARNING: You are about to update {len(to_update)} items.")
    print(f"IF you are sure you want to do so, type {require_phrase} to continue, anything else to cancel.")
    typed = input("Confirm: ").strip()

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
            print(f"Processed {i}/{len(to_update)}")

    success_df = pd.DataFrame(success_rows)
    errors_df = pd.DataFrame(error_rows)

    print(f"Done. Success: {len(success_df)}  Errors: {len(errors_df)}")
    return success_df, errors_df