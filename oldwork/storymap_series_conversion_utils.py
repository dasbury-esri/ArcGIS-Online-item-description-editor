"""
storymap_series_conversion_utils.py
Utilities to convert Classic Esri Story Map Series applications
into ArcGIS StoryMap Collections, compatible with ArcGIS Online Notebooks.

Dependencies:
  - arcgis.gis, arcgis.apps.storymap
  - requests, bs4, PIL, ipywidgets
"""

# ======================================================================
# Imports and Constants
# ======================================================================

from arcgis.gis import GIS, Item # type: ignore
from arcgis.apps.storymap import StoryMap, Collection, Themes, Text, TextStyles, Embed, Sidecar, Image, Video, Audio, Map # type: ignore
from arcgis.apps.storymap import * # type: ignore

import os, re, uuid, json, math, tempfile, requests, traceback
import ipywidgets as widgets # type: ignore
from IPython.display import display, HTML
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from PIL import Image as PILImage, ImageStat
from bs4 import BeautifulSoup # type: ignore

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
        print(f"Authenticated as: {context['gis'].properties.user.username} (role: {context['gis'].properties.user.role} / userType: {context['gis'].properties.user.userLicenseTypeId}")
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
# Generic Utility Functions to Prevent Exception Errors
# ======================================================================

def safe_get_json(item):
    """
    Safely get JSON data from an ArcGIS Item, returning {} if missing or corrupt.
    """
    try:
        data = item.get_data()
        if isinstance(data, dict):
            return data
        elif isinstance(data, str):
            return json.loads(data)
        else:
            return {}
    except Exception:
        return {}

def safe_get_rest_json(url, params=None):
    """
    Safely get JSON from a REST endpoint, returning {} if missing or corrupt.
    """
    try:
        resp = requests.get(url, params=params)
        return resp.json()
    except Exception:
        return {}

def safe_get_image(url: str, timeout: float = 20.0):
    """
    Fetches an image URL with production-safe headers and returns the response,
    or None on failure. Caller must check resp is not None and resp.ok.
    """
    if not url:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (ArcGIS StoryMaps Conversion Tool; ArcGIS Online Notebooks)",
        "Accept": "image/*,*/*;q=0.8",
        "Referer": "https://storymaps.arcgis.com/"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        # Some CDNs return 200 with non-image content; guard on content-type
        ctype = resp.headers.get("Content-Type", "")
        if resp.ok and ctype.startswith("image/"):
            return resp
    except requests.RequestException:
        pass
    return None
    
def download_image_to_path(url: str, dest_path: Path, timeout: float = 20.0) -> bool:
    """
    Downloads an image to dest_path with headers. Returns True on success.
    """
    resp = safe_get_image(url, timeout=timeout)
    if not resp:
        return False
    try:
        with dest_path.open("wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception:
        return False    

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
# StoryMap Data Extraction and Theme Mapping
# ======================================================================

def fetch_story_data_btn(button, output2, input2, context):
    """
    Fetch the classic StoryMap data and display status in the output widget.
    """
    print("input2.value:", input2.value)
    context['classic_id'] = input2.value
    with output2:
        output2.clear_output()
        try:
            print(f"Fetching data for '{context['classic_id']}'...")
            classic_storymap_id = context['classic_id']  # or set manually
            fetch_classic_storymap_data(classic_storymap_id, context)
            if context["classic_item"] is not None and context["classic_item_data"] is not None:
                print(f"Fetched classic StoryMap: '{context['classic_item'].title}' (ID: {context['classic_item'].itemid})")
                print("\nStep #2 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")
            else:
                print("Could not fetch classic StoryMap data. Check the item ID and try again.")
        except Exception as e:
            error_msg = traceback.format_exc()
            print("An error occurred:\n", error_msg)

def fetch_classic_storymap_data(classic_storymap_id, context):
    """
    Fetch the classic StoryMap item and its data.
    
    Returns
    -------
    tuple
        (classic_item, classic_item_data)
    """
    gis = context["gis"]
    classic_storymap_id = context['classic_id']
    # print(f"Fetching {classic_storymap_id}...")
    context['classic_item'] = Item(gis=gis, itemid=classic_storymap_id)
    # if context['classic_item']:
    #     print(f"Item returned {context['classic_item']}")
    # else:
    #     print(f"Failed fetch")
    context['classic_item_data'] = safe_get_json(context['classic_item'])
    # if context['classic_item_data']:
    #     print(f"Item data returned {context['classic_item_data']}")
    # else:
    #     print(f"Data fetch failed.")
    if context['classic_item_data'] == {}:
        raise ValueError("ERROR: StoryMap to be converted must be hosted on ArcGIS Online.")
    return context['classic_item'], context['classic_item_data']

def normalize_classic_title(classic_string):
    """Remove leading/trailing whitespace from the classic story's title."""
    return classic_string.strip()

def extract_story_settings(context):
    """
    Extract settings, theme, and entries from classic Story Map data.

    Parameters
    ----------
    classic_item_data : dict
        The classic Story Map JSON data.

    Returns
    -------
    tuple
        (title, subtitle, story_type, panel_position, theme, entries)
    """
    title = context['classic_item_data']["values"].get("title", "Untitled Classic StoryMap Series")
    context['classic_story_title'] = normalize_classic_title(title)
    context['classic_story_subtitle'] = context['classic_item_data']["values"].get("subtitle", "")
    if "values" in context['classic_item_data'] and "settings" in context['classic_item_data']["values"]:
        settings = context['classic_item_data']["values"]["settings"]
        context['classic_story_type'] = settings["layout"]["id"]
        context['classic_story_panel_position'] = settings["layoutOptions"]["panel"]["position"]
        context['classic_story_theme'] = settings["theme"]
    else:
        settings = {}
        context['classic_story_type'] = "Unknown or unsupported classic story"
        context['classic_story_panel_position'] = "Unknown"
        context['classic_story_theme'] = {}
    if "story" in context['classic_item_data']["values"] and "entries" in context['classic_item_data']["values"]["story"]:
        context['entries'] = context['classic_item_data']["values"]["story"]["entries"]
    else:
        context['entries'] = []
    return context

def extract_and_display_settings_btn(button, output3, context):
    """
    Extract and display settings, theme, and entries from the classic StoryMap data.
    """
    with output3:
        output3.clear_output()
        if context['classic_item_data'] is None:
            print("No classic StoryMap data found. Fetch the data first.")
            return
        context = extract_story_settings(context)
        if len(context['entries']) == 1:
            print("\nStory settings:")
            print(f"{'panel position:':>15} {context['classic_story_panel_position']}")
            print(f"{'series title:':>15} '{context['classic_story_title']}'")
            if context['classic_story_subtitle']:
                print(f"{'subtitle:':>15} {context['classic_story_subtitle']}")
            print(f"{'series type:':>15} {context['classic_story_type']}")
            print(f"\nFound {len(context['entries'])} entry in the Classic Map Series.")
        else:
            print("\nStory settings:")
            print(f"{'panel position:':>15} {context['classic_story_panel_position']}")
            print(f"{'series title:':>15} '{context['classic_story_title']}'")
            if context['classic_story_subtitle']:
                print(f"{'subtitle:':>15} {context['classic_story_subtitle']}")
            print(f"{'series type:':>15} {context['classic_story_type']}")
            print(f"\nFound {len(context['entries'])} entries in the Classic Map Series.")
        for i, e in enumerate(context['entries']):
            print(f"{i+1}. {e['title']}")
        classic_name, new_theme = determine_theme(context['classic_story_theme'])
        context['new_theme'] = new_theme
        print(f"\nClassic theme name: {classic_name}")
        print(f"{'New theme set to:':>19} {new_theme.name}")
        print("\nStep #3 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")

def determine_theme(theme):
    """Configure the new theme based on the classic theme."""
    classic_name = theme["colors"].get("name", "No classic theme name")
    group = theme["colors"]["group"]
    if group == "dark":
        return classic_name, Themes.OBSIDIAN
    elif group == "light":
        return classic_name, Themes.SUMMIT
    else:
        return classic_name, Themes.SUMMIT

# ======================================================================
# Main Stage (i.e. Media panel) Conversion
# ======================================================================

def convert_mainstage(entry, default_thumbnail_path: str | Path = ""):
    """
    Converts a single classic Story Map media panel into an AGSM object.

    Parameters
    ----------
    entry : dict
        The entry dictionary.
    entry_idx : int
        Index of the entry.
    entries : list
        List of all entries.
    story_settings : dict
        Story settings dictionary.
    gis : arcgis.gis.GIS
        The GIS connection.

    Returns
    -------
    tuple
        (entry_title, main_stage_content, invalid_webmap)
    """
    entry_title = entry.get("title")
    media_info = entry.get("media", {})
    media_type = media_info.get("type")
    main_stage_content = None
    invalid_webmap = False
    error_detail = None
    # Normalize default_thumbnail_path to str to avoid Path|str type issues
    default_thumbnail_path = str(default_thumbnail_path) if isinstance(default_thumbnail_path, Path) else default_thumbnail_path

    if media_type == "webmap":
        webmap_id = media_info.get('webmap', {}).get('id')
        if webmap_id and not invalid_webmap:
            try:
                main_stage_content = Map(webmap_id)
            except Exception as e:
                invalid_webmap = True
                 # Keep it short but informative; avoid full traceback unless needed
                error_detail = f"{e.__class__.__name__}: {e}"               
    elif media_type == "webpage":
        webpage_url = media_info.get("webpage", {}).get("url")
        if webpage_url:
            main_stage_content = Embed(webpage_url)
            if media_type == "image":
                image_url = select_image_thumbnail_url(media_info.get("url", ""), default_thumbnail_path)
                # Temporary special-case: switch Wikimedia URL to Embed for entry 1 of target classic story
                problematic_wiki = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Chartres.jpg/1280px-Chartres.jpg"
                force_embed = (
                    isinstance(context.get("classic_id"), str)
                    and context.get("classic_id") == "ed44254add784433bcbf0bacdc48e717"
                    and entry_index == 1
                    and isinstance(image_url, str)
                    and image_url.strip() == problematic_wiki
                )
                if image_url:
                    try:
                        if force_embed:
                            main_media = Embed(url=image_url)
                        else:
                            main_media = Image(path=image_url)
                    except Exception as e:
                        error_detail = f"Image media failed to initialize: {e}"
                        main_media = Embed(url=image_url)
            main_stage_content = Image(path=safe_url)
    return entry_title, main_stage_content, invalid_webmap, error_detail

def process_all_mainstages(context):
    """
    Loop though each main stage element in the classic StoryMap.

    Parameters
    ----------
    entries : list
        List of entry dictionaries.

    Returns
    -------
    None
    """
    # print(len(context['entry_titles']), len(context['main_stage_contents']), len(context['invalid_webmaps']), len(context['entries']))
    context['entry_titles'] = [None] * len(context['entries'])
    context['main_stage_contents'] = [None] * len(context['entries'])
    context['invalid_webmaps'] = [False] * len(context['entries'])
    context['webmap_errors'] = [None] * len(context['entries'])
    for i, entry in enumerate(context['entries']):
        (context['entry_titles'][i], 
         context['main_stage_contents'][i], 
         context['invalid_webmaps'][i],
         context['webmap_errors'][i]) = convert_mainstage(entry)
        if context['invalid_webmaps'][i]:
            err = context['webmap_errors'][i] or "Unknown error"
            print(f"WARNING: There is a problem with the webmap in entry [{i+1} of {len(context['entries'])}]: {context['entry_titles'][i]} -> {err}. Please fix before publishing the new StoryMap.")
        if type(context['main_stage_contents'][i]).__name__ == "Map":
            webmap_id = context['entries'][i].get("media", {}).get('webmap', {}).get('id')
            print(f"[{i+1} of {len(context['entries'])}]: {context['entry_titles'][i]:35} Media type: {type(context['main_stage_contents'][i]).__name__} (id: {webmap_id})")
        elif type(context['main_stage_contents'][i]).__name__ == "Embed":
            embed_url = context['entries'][i].get("media", {}).get('webpage', {}).get('url')
            print(f"[{i+1} of {len(context['entries'])}]: {context['entry_titles'][i]:35} Media type: {type(context['main_stage_contents'][i]).__name__} (link: {embed_url})")
        elif type(context['main_stage_contents'][i]).__name__ == "Image":
            image_name = context['entries'][i].get("media", {}).get('image', {}).get('title')
            print(f"[{i+1} of {len(context['entries'])}]: {context['entry_titles'][i]:35} Media type: {type(context['main_stage_contents'][i]).__name__} (title: {image_name})")
        else:
            print(f"[{i+1} of {len(context['entries'])}]: {context['entry_titles'][i]:35} Media type: {type(context['main_stage_contents'][i]).__name__}")

def process_entries_btn(button, output4, context):
    """
    Process all entries in the classic StoryMap and display status.
    """
    with output4:
        output4.clear_output()
        print(f"Processing {len(context['entries'])} entries...")
        fill_missing_extents(context['entries'], context['classic_item_data']['values']['settings'])
        process_all_mainstages(context)
        print("\nStep #4 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")

# ======================================================================
# HTML manipulation and Sidecar Conversion
# ======================================================================

def color_to_hex(color_value):
    """
    Convert a color value (hex, rgb/rgba string, named color, or tuple) to a 6-digit hex string
    without the leading '#'. Alpha, if present, is ignored.
    """
    import re
    try:
        import matplotlib.colors as mcolors
    except Exception:
        return None

    # Handle non-string inputs (e.g., tuples like (r, g, b) or (r, g, b, a))
    if isinstance(color_value, (tuple, list)):
        # Assume floats in 0..1 or ints in 0..255
        comps = list(color_value)
        if len(comps) not in (3, 4):
            return None
        # Drop alpha if present
        comps = comps[:3]
        # Normalize to 0..1 floats
        if all(isinstance(c, (int, float)) for c in comps):
            if any(c > 1.0 for c in comps):
                comps = [max(0, min(255, c)) / 255.0 for c in comps]
            else:
                comps = [max(0.0, min(1.0, c)) for c in comps]
            # Explicitly cast to fixed-length 3-tuple for type checker
            rgb_tuple = (float(comps[0]), float(comps[1]), float(comps[2]))
            hex_str = mcolors.to_hex(rgb_tuple, keep_alpha=False)
            return hex_str[1:].upper()
        return None

    if not isinstance(color_value, str):
        return None

    s = color_value.strip()

    # Hex strings: '#RRGGBB' or 'RRGGBB'
    hex_match = re.fullmatch(r'#?([0-9A-Fa-f]{6})', s)
    if hex_match:
        return hex_match.group(1).upper()

    # rgb(...) or rgba(...), integers 0-255
    rgb_match = re.fullmatch(
        r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d\.]+)?\s*\)',
        s,
        re.IGNORECASE,
    )
    if rgb_match:
        r, g, b = (int(x) for x in rgb_match.groups()[:3])
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return '{:02X}{:02X}{:02X}'.format(r, g, b)

    # Named colors or other formats parsable by matplotlib
    try:
        # mcolors.to_rgb returns a 3-tuple of floats 0..1
        rgb = mcolors.to_rgb(s)
        hex_str = mcolors.to_hex(rgb, keep_alpha=False)
        return hex_str[1:].upper()
    except Exception:
        return None

def convert_color_style_to_class(tag):
    """
    Convert inline color styles to AGSM class names and remove inline styles.
    """
    # Check if tag has 'style' attribute with color
    style = tag.get('style', '')
    # Regex to find color property (hex, rgb, named colors)
    match = re.search(r'color\s*:\s*([^;]+)', style, re.IGNORECASE)
    if match:
        color_value = match.group(1).strip()
        hex_color = color_to_hex(color_value)
        if hex_color:
            class_color = f"sm-text-color-{hex_color}"
            # Remove color from style attribute
            new_style = re.sub(r'color\s*:\s*[^;]+;?', '', style, flags=re.IGNORECASE).strip()
            if new_style:
                tag['style'] = new_style
            else:
                if 'style' in tag.attrs:
                    del tag['style']
            # Add or append class attribute
            if 'class' in tag.attrs:
                tag['class'].append(class_color)
            else:
                tag['class'] = [class_color]

def process_html_colors_preserve_html(html_text):
    """
    Convert inline color styles in HTML text to class names while preserving other HTML tags.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    # Iterate over tags that can have styles: div, span, strong, em, p, etc.
    for tag in soup.find_all(True):
        convert_color_style_to_class(tag)
    return str(soup)

def convert_element_to_storymap_object(el):
    """
    Convert a BeautifulSoup element to a StoryMap object.

    Parameters
    ----------
    el : bs4.element.Tag
        BeautifulSoup element.

    Returns
    -------
    object or tuple
        StoryMap object or (StoryMap object, caption, alt text, link) for w
    """
    img_tag = el.find('img')
    if img_tag:
        src = img_tag.get("src")
        # Upgrade http to https if needed
        if src and src.startswith("http://"):
            src = "https://" + src[len("http://"):]
        alt = img_tag.get("alt", "")
        link = "" # TO DO handle occasions when image is intended to launch a link
        # Find figcaption in parent figure or div
        figcaption = ""
        # print("img_tag:", img_tag)
        parent_figure = img_tag.find_parent("figure")
        # print("parent_figure:", parent_figure)
        if parent_figure:
            caption_tag = parent_figure.find("figcaption")
            # print("caption_tag:", caption_tag)
            if caption_tag:
                figcaption = caption_tag.get_text(strip=True)
        else:
            # Try to find figcaption in the parent div
            parent_div = img_tag.find_parent("div")
            # print("parent_div:", parent_div)
            if parent_div:
                caption_tag = parent_div.find("figcaption")
                # print("caption_tag (div):", caption_tag)
                if caption_tag:
                    figcaption = caption_tag.get_text(strip=True)
        # print("Extracted figcaption:", figcaption, type(figcaption))
        img = Image(path=src)
        #img.link = link
        #img.image = src
        return img, figcaption, alt, link

    tag_name = el.name
    if tag_name == "p": # or tag_name in ["span", "strong", "em", "div"]:
        # Extract inner HTML preserving inline styles
        inner_html = ''.join(str(c) for c in el.contents)
        processed_html = process_html_colors_preserve_html(inner_html)
        return Text(text=processed_html, style=TextStyles.PARAGRAPH)

    elif tag_name == "video":
        src = el.get("src")
        alt = el.get("alt", "")
        vid = Video(path=src)
        vid.alt_text = alt
        vid.caption = "" # TO DO try to find Classic stories that have Videos with captions
        vid.video = src # Assign video property. TO DO fix this for hosted videos
        return vid
    
    elif tag_name == "audio":
        src = el.get("src")
        alt = el.get("alt", "")
        aud = Audio(path=src)
        aud.alt_text = alt
        aud.caption = "" # TO DO try to find Classic stories that have Audio with captions
        aud.audio = src # Assign Audio property. TO DO fix this for hosted videos
        return aud
    
    elif tag_name == "iframe" or tag_name == "embed":
        src = el.get("src") or el.get("data-src")
        alt = el.get("alt", "")
        if src:
            emb = Embed(path=src)
            emb.alt_text = alt
            emb.caption = "" # TO DO try to find Classic stories that have Embeds with captions
            emb.link = src
            return emb
        # Fallback to text if no src
        inner_html = ''.join(str(c) for c in el.contents)
        processed_html = process_html_colors_preserve_html(inner_html)
        return Text(text=processed_html, style=TextStyles.PARAGRAPH)   

    elif tag_name == "map":
        src = el.get("src")
        alt = el.get("alt", "")
        extent = "" #TO DO get extent
        layers = "" # TO DO get map layers
        mp = Map(item="")
        mp.alt_text = alt
        mp.caption = "" # TO DO try to find Classic stories that have Maps in Sidecar panel with captions
        mp.map = src
        mp.map_layers = layers 
        mp.set_viewpoint = extent
        return mp
    
    else:
        # Fallback for unsupported or unknown types - treat as text
        inner_html = ''.join(str(c) for c in el.contents)
        processed_html = process_html_colors_preserve_html(inner_html)
        return Text(text=processed_html, style=TextStyles.PARAGRAPH)

def parse_root_elements(html_snippet):
    """Parse an HTML snippet with BeautifulSoup and return a list of meaningful root-level elements."""
    soup = BeautifulSoup(html_snippet, "html.parser")
    html_elements = []
    for child in soup.contents:
        if not getattr(child, 'name', None):
            continue

        # If this is a <figure> with an <img>, add the whole figure
        if child.name == "figure" and child.find('img'):
            html_elements.append(child)
            continue

        # Check if the parent itself is meaningful
        has_text = child.get_text(strip=True) != ""
        has_img = child.find('img') is not None
        has_video = child.find('video') is not None
        has_audio = child.find('audio') is not None
        has_iframe = child.find('iframe') is not None
        has_embed = child.find('embed') is not None
        has_map = child.find('map') is not None
        is_meaningful = has_text or has_img or has_video or has_audio or has_iframe or has_embed or has_map

        # Check for meaningful children
        meaningful_children = []
        for c in child.children:
            if not getattr(c, 'name', None):
                continue
            c_has_text = c.get_text(strip=True) != ""
            c_has_img = c.find('img') is not None
            c_has_video = c.find('video') is not None
            c_has_audio = c.find('audio') is not None
            c_has_iframe = c.find('iframe') is not None
            c_has_embed = c.find('embed') is not None
            c_has_map = c.find('map') is not None
            if c_has_text or c_has_img or c_has_video or c_has_audio or c_has_iframe or c_has_embed or c_has_map:
                meaningful_children.append(c)

        # If there are meaningful children, add them
        if meaningful_children:
            html_elements.extend(meaningful_children)
            # Optionally, if the parent is also meaningful and not just a container, add it too
            # If you want to avoid duplicates, only add children
            continue

        # If no meaningful children, but parent is meaningful, add parent
        if is_meaningful:
            html_elements.append(child)

    return html_elements

# Troubleshooting Beautiful Soup parsing
# def parse_nested_elements(html_snippet):
#     soup = BeautifulSoup(html_snippet, "html.parser")
#     soup_list = [child for child in soup.contents if getattr(child, 'name', None)]
#     html_elements = []
#     for element in soup_list:
#         for c in element:
#             if getattr(c, 'name', None):
#                 html_elements.append(c)
#     return html_elements

def convert_html_elements_to_storymap_node(html_elements):
    """
    Convert a list of HTML elements to StoryMap nodes and collect image metadata.
    """
    content_nodes = []
    image_metadata = []  # To store (img, caption, alt, link) tuples
    for el in html_elements:
        node = convert_element_to_storymap_object(el)
        if isinstance(node, tuple):
            img, caption, alt, link = node
            content_nodes.append(img)
            image_metadata.append((img, caption, alt, link))
        elif node:
            content_nodes.append(node)
    return content_nodes, image_metadata

# ======================================================================
# Thumbnail utils
# ======================================================================

def download_thumbnail(webmap_item, default_thumbnail_path, context):
    """
    Download thumbnail from an ArcGIS Online Item to a local temp file and return the local path.
    If download fails, use the default thumbnail path.
    """
    # Normalize default_thumbnail_path to str to avoid Path|str type issues
    default_thumbnail_path = str(default_thumbnail_path) if isinstance(default_thumbnail_path, Path) else default_thumbnail_path
    gis = context['gis']
    try:
        url = f"{webmap_item._portal.resturl}content/items/{webmap_item.id}/info/{webmap_item.thumbnail}"
        token = gis._con.token if gis else None
        params = {'token': token} if token else {}
        # Fetch the image bytes, not JSON
        resp = requests.get(url, params=params, timeout=30)
        if not getattr(resp, "ok", False):
            raise RuntimeError("thumbnail request failed")

        img = PILImage.open(BytesIO(resp.content))
        temp_file_path = BASE_DIR / f"thumbnail_{uuid.uuid4().hex}.png"
        img.save(temp_file_path)
        return str(temp_file_path)
    except Exception:
        print("Thumbnail download failed; using default.")
        # Fallback: local/default image path or URL
        try:
            if default_thumbnail_path.startswith("http"):
                resp = requests.get(default_thumbnail_path, timeout=30)
                if not getattr(resp, "ok", False):
                    raise RuntimeError("default thumbnail request failed")
                img = PILImage.open(BytesIO(resp.content))
            else:
                img = PILImage.open(default_thumbnail_path)
        except Exception:
            # Last resort: blank thumbnail
            img = PILImage.new("RGB", (800, 600), color=(200, 200, 200))

        temp_file_path = BASE_DIR / f"thumbnail_{uuid.uuid4().hex}.png"
        img.save(temp_file_path)
        return str(temp_file_path)

def validate_image_url(url: str) -> bool:
    """
    Return True if a remote image URL is reachable and returns an image/* content-type.
    """
    resp = safe_get_image(url)
    return resp is not None

def select_image_thumbnail_url(image_url: str | Path, default_thumbnail_path: str | Path) -> str:
    """
    Pick a usable image URL (original if valid, otherwise default, otherwise blank fallback).
    No file I/O performed.
    """
    # Normalize to strings
    image_url_str = str(image_url) if isinstance(image_url, Path) else image_url
    default_str = str(default_thumbnail_path) if isinstance(default_thumbnail_path, Path) else default_thumbnail_path

    if image_url_str and validate_image_url(image_url_str):
        return image_url_str
    if default_str and validate_image_url(default_str):
        return default_str
    # Last resort: transparent 1x1 PNG data URL
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="


def is_blank_image(image_path, threshold=5):
    """
    Check if an image is blank or nearly uniform.
    """
    img = PILImage.open(image_path).convert('L')
    pixels = list(img.getdata())
    unique_values = set(pixels)
    # If only 1 or 2 unique values (e.g., all black, all white, or half black/half white), treat as blank
    if len(unique_values) <= 2:
        return True
    stat = ImageStat.Stat(img)
    return stat.stddev[0] < threshold  # fallback for nearly-uniform images

def create_webmap_thumbnail(webmap_json, default_thumbnail_path):
    """
    Create a thumbnail for a webmap using the ArcGIS print service.

    Parameters
    ----------
    webmap_json : dict
        The webmap JSON.
    default_thumbnail_path : str
        URL or path to the default thumbnail.

    Returns
    -------
    tuple
        (thumbnail_path, print_service_response, webmap_json)
    """
    # Normalize default_thumbnail_path to str to avoid Path|str type issues
    default_thumbnail_path = str(default_thumbnail_path) if isinstance(default_thumbnail_path, Path) else default_thumbnail_path

    url = "https://utility.arcgisonline.com/arcgis/rest/services/Utilities/PrintingTools/GPServer/Export%20Web%20Map%20Task/execute"
    webmap_json = webmap_json if isinstance(webmap_json, dict) else json.loads(webmap_json)
    webmap_json_copy = deepcopy(webmap_json)
    tried_urls = set()
    max_attempts = 10  # Prevent infinite loops

    # List to capture all print service responses for troubleshooting
    # print_service_response = []

    # Ensure exportOptions is set
    if 'exportOptions' not in webmap_json_copy:
        webmap_json_copy['exportOptions'] = {
            "outputSize": [800, 600],
            "dpi": 96
        }
    # Ensure mapOptions/extent is set
    if 'mapOptions' not in webmap_json_copy:
        webmap_json_copy['mapOptions'] = {}
    if 'extent' not in webmap_json_copy['mapOptions']:
        webmap_json_copy['mapOptions']['extent'] = webmap_json.get('mapOptions', {}).get('extent', webmap_json.get('initialState', {}).get('viewpoint', {}).get('targetGeometry'))

    for attempt in range(max_attempts):
        params = {
            "f": "json",
            "Web_Map_as_JSON": json.dumps(webmap_json_copy),
            "Format": "PNG32",
            "Layout_Template": "MAP_ONLY"
        }
        
        # Capture the final json sent to the print service for troubleshoorting
        # final_webmap_json = deepcopy(webmap_json_copy)
        
        response = requests.post(url, data=params)
        result = response.json()

        # Capture the print service response for troubleshooting
        # print_service_response.append({
        #     "attempt": attempt + 1,
        #     "params": params,
        #     "status_code": response.status_code,
        #     "result": result
        # })

        if 'results' in result:
            image_url = result['results'][0]['value']['url']
            img_response = safe_get_image(image_url)
            if img_response is not None and getattr(img_response, "status_code", 0) == 200:
                temp_file_path = BASE_DIR / f"thumbnail_{uuid.uuid4().hex}.png"
                with open(temp_file_path, "wb") as f:
                    f.write(img_response.content)
                img = PILImage.open(temp_file_path)
                is_blank = is_blank_image(temp_file_path)
                if is_blank:
                    print("Generated thumbnail is blank") #; scaling extent and retrying.")
                    # Try to scale the extent if possible
                    extent = webmap_json_copy.get('mapOptions', {}).get('extent')
                    # if extent:
                    #     new_extent = scale_extent(extent, scale_factor=1.1)
                    #     webmap_json_copy['mapOptions']['extent'] = new_extent
                    #     webmap_json_copy['extent'] = new_extent
                    #     continue  # Retry with new extent
                    # else:
                    if not extent:
                        print("No extent found to scale; using default image.")
                        temp_file_path = select_image_thumbnail_url(image_url=default_thumbnail_path, default_thumbnail_path=default_thumbnail_path)
                        return temp_file_path, webmap_json # , print_service_response
                return temp_file_path, webmap_json # , print_service_response
            else:
                break  # No valid image, break and use default

        elif 'error' in result and 'details' in result['error']:
            # Try to extract the failed service URL
            details_list = result['error']['details']
            failed_service_url: str | None = None            
            if details_list and len(details_list) > 0:
                failed_layer_detail = details_list[0]
                if ' at ' in failed_layer_detail:
                    failed_service_url = failed_layer_detail.split(' at ')[-1]

                if failed_service_url:
                    if failed_service_url in tried_urls:
                        break  # Prevent infinite loop if same URL keeps failing
                tried_urls.add(failed_service_url)
                webmap_json_copy = remove_failed_service(webmap_json_copy, failed_service_url)
                continue  # Try again with the updated JSON
            else:
                print("No details available in error response.")
                break  # Can't parse the failed URL, break and use default
        else:
            break  # No results and no error details, break and use default

    # If we reach here, fallback to the default thumbnail
    print("Thumbnail download failed; using default.")
    temp_file_path = select_image_thumbnail_url(image_url=default_thumbnail_path, default_thumbnail_path=default_thumbnail_path)
    return temp_file_path, webmap_json # , print_service_response

def remove_failed_service(webmap_json, failed_url):
    """
    Remove failed service URLs from operationalLayers and baseMapLayers in the webmap JSON.

    Parameters
    ----------
    webmap_json : dict
        The webmap JSON.
    failed_url : str
        The URL of the failed service.

    Returns
    -------
    dict
        Updated webmap JSON.
    """
    # Remove from operationalLayers
    if 'operationalLayers' in webmap_json:
        webmap_json['operationalLayers'] = [
            lyr for lyr in webmap_json['operationalLayers']
            if not lyr.get('url', '').startswith(failed_url)
        ]
    # Remove from baseMapLayers
    if 'baseMap' in webmap_json and 'baseMapLayers' in webmap_json['baseMap']:
        webmap_json['baseMap']['baseMapLayers'] = [
            lyr for lyr in webmap_json['baseMap']['baseMapLayers']
            if not lyr.get('url', '').startswith(failed_url)
        ]
    return webmap_json

def build_webmap_from_json(gis, media_info):
    """
    Build a minimal webmap JSON for the print service from a storymap entry's media property,
    using the basemap from the referenced webmap item if available.

    Parameters
    ----------
    gis : arcgis.gis.GIS
        The GIS connection.
    media_info : dict
        Media information from the storymap entry.

    Returns
    -------
    tuple
        (webmap_id, webmap_json)
    """
    # Get webmap json from entry
    webmap = media_info.get("webmap", {})

    # Fetch full webmap item data from AGO
    webmap_id = webmap.get("id")
    webmap_item_data = {}
    if webmap_id:
        try:
            webmap_item = gis.content.get(webmap_id)
            webmap_item_data = safe_get_json(webmap_item)
        except Exception as e:
            print(f"Could not fetch webmap item: {e}")

    # --- Extent ---
    # Get extent and spatial reference from the entry
    # Set default spatial reference to Web Mercator
    spatialRef = {"wkid": 102100}

    # Start with a default extent (whole world in Web Mercator)
    extent = {
        "xmin": -20037508.342789244,
        "ymin": -20037508.342789244,
        "xmax": 20037508.342789244,
        "ymax": 20037508.342789244,
        "spatialReference": spatialRef
    }

    webmap = media_info.get("webmap", {})
    webmap_extent = webmap.get("extent")

    if webmap_extent:
        # Normalize and use provided extent
        normalized = normalize_webmercator_extent(webmap_extent)
        extent = normalized
        spatialRef = normalized.get("spatialReference", spatialRef)
    else:
        # Try to derive from initialState.viewpoint.targetGeometry
        fallback_extent = (
            webmap.get("mapOptions", {}).get("extent")
            or webmap.get("initialState", {}).get("viewpoint", {}).get("targetGeometry")
        )
        if fallback_extent and all(k in fallback_extent for k in ("xmin", "ymin", "xmax", "ymax")):
            normalized = normalize_webmercator_extent(fallback_extent)
            extent = normalized
            spatialRef = normalized.get("spatialReference", spatialRef)

    mapOptions = {"extent": extent}

    # --- Operational Layers ---
    operationalLayers = []
    # Get full operationalLayers from AGO webmap item
    item_layers = webmap_item_data.get("operationalLayers", [])
    # Get overrides from entry (may be 'layers' or 'operationalLayers')
    entry_layers = webmap.get("layers", []) or webmap.get("operationalLayers", [])
    # Build a dict for quick lookup of overrides by id
    entry_layer_overrides = {lyr.get("id"): lyr for lyr in entry_layers if "id" in lyr}
    # Merge: start with item_layers, apply overrides from entry_layer_overrides
    for item_lyr in item_layers:
        lyr_id = item_lyr.get("id")
        merged_lyr = deepcopy(item_lyr)
        if lyr_id in entry_layer_overrides:
            for k, v in entry_layer_overrides[lyr_id].items():
                merged_lyr[k] = v  # override/add property
        operationalLayers.append(merged_lyr) 

    # --- Basemap ---
    # Default basemap (fallback)
    topo_basemap = {
        "baseMapLayers": [{
            "id": "World_Topo_Map",
            "layerType": "ArcGISTiledMapServiceLayer",
            "opacity": 1,
            "visibility": True,
            "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer"
        }],
        "title": "Topographic"
    }

    imagery_basemap = {
        "baseMapLayers": [{
            "id": "World_Imagery",
            "layerType": "ArcGISTiledMapServiceLayer",
            "opacity": 1,
            "visibility": True,
            "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
        }],
        "title": "Imagery"
    }
    baseMap = topo_basemap # Default if basemap not present

    if "baseMap" in webmap:
        # Use the baseMap as-is from the entry
        baseMap = deepcopy(webmap["baseMap"])
    else:
        # Try to get basemap from the referenced webmap item
        if "id" in media_info["webmap"]:
            try:
                webmap_item = gis.content.get(media_info["webmap"]["id"])
                webmap_item_data = safe_get_json(webmap_item)
                if "baseMap" in webmap_item_data and "baseMapLayers" in webmap_item_data["baseMap"]:
                    # Only keep required fields for each basemap layer
                    baseMapLayers = []
                    for lyr in webmap_item_data["baseMap"]["baseMapLayers"]:
                        baseMapLayers.append({
                            "id": lyr.get("id", "basemap"),
                            "layerType": lyr.get("layerType", "ArcGISTiledMapServiceLayer"),
                            "opacity": lyr.get("opacity", 1),
                            "visibility": lyr.get("visibility", True),
                            "url": lyr.get("url")
                        })
                    baseMap = {
                        "baseMapLayers": baseMapLayers,
                        "title": webmap_item_data["baseMap"].get("title", "Basemap")
                    }
            
            except Exception as e:
                print(f"Could not fetch basemap from webmap item: {e}. Using fallback basemap.")                      

    # Export options for print service
    export_options = {"outputSize": [800, 600], "dpi": 96}

    # Construct final webmap JSON
    webmap_json = {
        "baseMap": baseMap,
        "operationalLayers": operationalLayers,
        "spatialReference": spatialRef,
        "mapOptions": mapOptions,
        "exportOptions": export_options   
    }    
    
    # Invert the drawing order of operational layers
    if "operationalLayers" in webmap_json:
        webmap_json["operationalLayers"] = list(reversed(webmap_json["operationalLayers"]))

    return webmap['id'], webmap_json

def normalize_webmercator_extent(extent):
    """
    Normalize an extent dict for sending to the ArcGIS print service.

    Returns
    -------
    dict
        Normalized extent dictionary.
    """
    # Web Mercator maximum values
    min_x = -20037508.342789244
    max_x =  20037508.342789244

    def wrap_longitude(x):
        """
        Wrap longitude values (meters) into the valid Web Mercator range.
        """
        world_width = max_x - min_x
        while x < min_x:
            x += world_width
        while x > max_x:
            x -= world_width
        return x

    # Wrap x values
    xmin = wrap_longitude(extent['xmin'])
    xmax = wrap_longitude(extent['xmax'])
    # Clamp y values (no wrapping for y)
    ymin = max(min(extent['ymin'], max_x), min_x)
    ymax = max(min(extent['ymax'], max_x), min_x)
    return {
        'xmin': xmin,
        'ymin': ymin,
        'xmax': xmax,
        'ymax': ymax,
        'spatialReference': extent.get('spatialReference', {'wkid': 102100})
    }

def fill_missing_extents(entries, story_settings):
    """
    Fill missing extents in entries if mapsSync is enabled in the classic story.

    Parameters
    ----------
    entries : list
        List of entry dictionaries.
    story_settings : dict
        Story settings dictionary.

    Returns
    -------
    None
    """
    maps_sync = story_settings.get('mapOptions', {}).get('mapsSync', False)
    if not maps_sync:
        return  # Only fill if mapsSync is True

    for i, entry in enumerate(entries):
        media_info = entry.get('media', {})
        webmap_info = media_info.get('webmap', {})
        extent = webmap_info.get('extent')

        # If extent is missing, try to fill from previous or next entry
        if not extent:
            # Try previous entry
            if i > 0:
                prev_extent = entries[i - 1].get('media', {}).get('webmap', {}).get('extent')
                if prev_extent:
                    webmap_info['extent'] = prev_extent
                    continue
            # Try next entry
            if i < len(entries) - 1:
                next_extent = entries[i + 1].get('media', {}).get('webmap', {}).get('extent')
                if next_extent:
                    webmap_info['extent'] = next_extent
                    continue
            # If still missing, leave as is (will be handled by fallback logic)

# Fallback extent (probably unnecessary)
def fetch_extent_from_item(item, gis):
    """
    Fetch the WGS84 extent from an ArcGIS Online item. Depends on wgs84_to_webmercator() to convert degrees to meters.

    Returns
    -------
    dict or None
        Extent dictionary in Web Mercator or None if not found.
    """
    item_data = safe_get_json(item)
    if 'extent' in item_data and item_data['extent']:
        extent = item_data['extent']
        # If it's a list of lists, convert to dict
        if isinstance(extent, list) and len(extent) == 2 and all(isinstance(coord, list) for coord in extent):
            [[xmin, ymin], [xmax, ymax]] = extent
            # Assume WGS84 if not specified
            sr = item_data.get('spatialReference', {}).get('wkid', 4326)
            if sr == 4326:
                xmin_m, ymin_m = wgs84_to_webmercator(xmin, ymin)
                xmax_m, ymax_m = wgs84_to_webmercator(xmax, ymax)
                return {
                    'xmin': xmin_m,
                    'ymin': ymin_m,
                    'xmax': xmax_m,
                    'ymax': ymax_m,
                    'spatialReference': {'wkid': 102100},
                }
            else:
                return {
                    'xmin': xmin,
                    'ymin': ymin,
                    'xmax': xmax,
                    'ymax': ymax,
                    'spatialReference': {'wkid': sr},
                }
        # If it's already a dict, check spatialReference
        elif isinstance(extent, dict):
            sr = extent.get('spatialReference', {}).get('wkid', 4326)
            if sr == 4326:
                xmin_m, ymin_m = wgs84_to_webmercator(extent['xmin'], extent['ymin'])
                xmax_m, ymax_m = wgs84_to_webmercator(extent['xmax'], extent['ymax'])
                return {
                    'xmin': xmin_m,
                    'ymin': ymin_m,
                    'xmax': xmax_m,
                    'ymax': ymax_m,
                    'spatialReference': {'wkid': 102100},
                }
            else:
                return extent
        else:
            return extent

    # Try REST API for extent property
    url = f"{gis._portal.resturl}content/items/{item.itemid}?f=json"
    token = gis._con.token if gis else None
    params = {'f': 'json'}
    if token:
        params['token'] = token
    data = safe_get_rest_json(url, params)
    if 'extent' in data and data['extent']:
        # Convert to Web Mercator
        [[xmin, ymin], [xmax, ymax]] = data['extent']
        xmin_m, ymin_m = wgs84_to_webmercator(xmin, ymin)
        xmax_m, ymax_m = wgs84_to_webmercator(xmax, ymax)
        return {
            'xmin': xmin_m,
            'ymin': ymin_m,
            'xmax': xmax_m,
            'ymax': ymax_m,
            'spatialReference': {'wkid': 102100},
        }
    return None

def wgs84_to_webmercator(x, y):
    """
    Convert WGS84 coordinates to Web Mercator.

    Returns
    -------
    tuple
        (mx, my) in Web Mercator meters.
    """
    origin_shift = 20037508.342789244
    mx = x * origin_shift / 180.0
    my = math.log(math.tan((90 + y) * math.pi / 360.0)) * origin_shift / math.pi
    return mx, my

# (Removed _proxy_image_url; image URLs are validated directly without proxying.)

# ======================================================================
# StoryMap and Collection Assembly
# ======================================================================

def build_and_save_storymap(context, entry_index):
    """
    Build and save a single StoryMap from a classic storymap entry.
    """
    # global webmap_jsons
    # print_service_responses = None

    entry = context['entries'][entry_index]
    entry_title = context['entry_titles'][entry_index]
    main_stage_content = context['main_stage_contents'][entry_index]
    new_theme = context['new_theme']
    # Normalize default_thumbnail_path to str to avoid Path|str type issues
    default_thumbnail_path = str(context['default_thumbnail_path']) if isinstance(context['default_thumbnail_path'], Path) else context['default_thumbnail_path']
    gis = context['gis']

    # webmap_id_from_entry = None
    # webmap_json = None
    media_info = entry.get("media", {})
    media_type = media_info.get("type")

    story = StoryMap()
    story.theme(context['new_theme'])
    sidecar = Sidecar(style="docked-panel")
    story.add(sidecar)

    description_html = entry.get("description", "")
    # Parse HTML and convert to StoryMap nodes
    content_nodes, content_image_metadata = convert_html_elements_to_storymap_node(parse_root_elements(description_html))

    # Guard main stage Image before adding slide
    safe_media = main_stage_content
    if isinstance(main_stage_content, Image):
        # If the URL is not a reachable image, swap to a validated URL (no proxy)
        orig_url = getattr(main_stage_content, "_path", "") or media_info.get("image", {}).get("url")
        orig_url_str = str(orig_url)
        safe_url = select_image_thumbnail_url(
            image_url=orig_url_str,
            default_thumbnail_path=context['default_thumbnail_path']
        )
        safe_media = Image(path=safe_url)
    
    # Add main stage content and text content to sidecar
    sidecar.add_slide(contents=content_nodes, media=safe_media)

    # Assign metadata to each image in Side Panel contents
    for img, caption, alt, link in content_image_metadata:
        try:
            img.caption = caption
            img.alt_text = alt
            img.link = link
        except Exception as e:
            print(f"Error setting image metadata: {e}")

    # Set media properties
    if isinstance(safe_media, Map):
        # Set webmap properties. Map must be added to the story before setting viewpoint
        if media_type == "webmap":
            # Set the extent for the map stage
            extent_json = media_info.get('webmap', {}).get('extent')
            if extent_json:
                main_stage_content.set_viewpoint(extent=extent_json)  # Extent dict per docs
            # Set layer visibility 
            old_layers = media_info.get('webmap', {}).get('layers', [])
            if old_layers and hasattr(main_stage_content, "map_layers"):
                for new_lyr in main_stage_content.map_layers:
                    for old_lyr in old_layers:
                        if new_lyr['id'] == old_lyr['id']:
                            new_lyr['visible'] = old_lyr['visibility']
            elif "operationalLayers" in media_info.get('webmap', {}):
                old_layers = media_info.get('webmap', {}).get('operationalLayers', [])
                if hasattr(main_stage_content, "map_layers"):
                    for new_lyr in main_stage_content.map_layers:
                        for old_lyr in old_layers:
                            if 'id' in new_lyr and 'id' in old_lyr and new_lyr['id'] == old_lyr['id']:
                                new_lyr['visible'] = old_lyr['visibility']

        # Build a webmap from JSON to create thumbnail
        webmap_id_from_entry, webmap_json = build_webmap_from_json(context['gis'], media_info)
        ## Store webmap json for troubleshooting
        # webmap_jsons.append({
        #     "entry_index": entry_index,
        #     "entry_title": entry_title,
        #     "webmap_id": webmap_id_from_entry,
        #     "webmap_json": webmap_json
        # })
        thumbnail_path, webmap_json = create_webmap_thumbnail(webmap_json=webmap_json, default_thumbnail_path=default_thumbnail_path)
        # thumbnail_path, webmap_json, print_service_response = create_webmap_thumbnail(webmap_json=webmap_json, default_thumbnail_path=default_thumbnail_path)
    elif isinstance(safe_media, Image):
        image_url = media_info.get("image", {}).get("url")
        thumbnail_path = select_image_thumbnail_url(image_url=image_url, default_thumbnail_path=default_thumbnail_path)
    # Create a default thumbnail for any unrecongized types
    else:
        thumbnail_path = select_image_thumbnail_url(image_url=default_thumbnail_path, default_thumbnail_path=default_thumbnail_path)
    # Assign metadata to main stage Images
    if isinstance(safe_media, Image):
        caption = media_info.get("image", {}).get("caption", "")
        alt = media_info.get("image", {}).get("alt", "")
        link = media_info.get("image", {}).get("link", "")        
        if caption:
            safe_media.caption = media_info.get("image", {}).get("caption", "")
        if alt:
            safe_media.alt_text = media_info.get("image", {}).get("alt", "")
        if link:
            safe_media.link = media_info.get("image", {}).get("link", "")
        # if display: # https://developers.arcgis.com/python/latest/api-reference/arcgis.apps.storymap.html#arcgis.apps.storymap.story_content.Image.display
        #    main_stage_content.display = display
        # if properties:
        #    main_stage_content.properties = properties

    # Set cover properties
    cover_properties = story.content_list[0]
    cover_properties.title = entry_title
    cover_properties.byline = ""
    cover_properties.date = "none"
    # Safe cover URL
    cover_url = thumbnail_path
    cover_url = select_image_thumbnail_url(
        image_url=str(cover_url),
        default_thumbnail_path=default_thumbnail_path
    )
    cover_properties.media = Image(path=cover_url)

    # Hide cover. Since the StoryMap cover has no property to hide it, we hide the node using JSON properties
    for k, v in story.properties['nodes'].items():
        if v['type'] == 'storycover':
            v['config'] = {'isHidden': 'true'}

    # Save and publish
    published_story_item = None
    story.save(title=entry_title, tags=["Classic Story Map to AGSM Conversion", "Story Map Series"], publish=True)
    if hasattr(story, '_item'):
        published_story_item = story._item
        published_story_item.update(thumbnail=str(thumbnail_path))
        published_story_item_url = "https://storymaps.arcgis.com/stories/" + published_story_item.id
        display(HTML(f'<a href="{published_story_item_url}" target="_blank">{entry_title}</a> is staged for publishing. Click the link to complete.'))
        return published_story_item, thumbnail_path
    else:
        print("Could not find item for story:", story.title)
        return published_story_item, thumbnail_path

def create_and_save_storymaps(context):
    """Loop to create and save StoryMaps from a list"""
    entries = context['entries']

    # Initialize context lists
    context['published_storymap_items'] = [None] * len(entries)
    context['thumbnail_paths'] = [None] * len(entries)

    print("\n***NOTICE*** You MUST click each link below to open the story in a browser tab. ***NOTICE***\n***NOTICE*** Check for errors, edit and continue publishing if necessary.       ***NOTICE***\n\nIf you see an error message -- before troubleshooting further -- try just clicking the 'Publish' button. Doing so can fix many common issues.\n")

    for i in range (len(context['entries'])): # , entry in enumerate(entries):
        print(f"Converting [{i+1} of {len(context['entries'])}]... ",end="")
        # display(HTML(f'Converting [{i+1} of {len(context["entries"])}]... <a href="{published_story_item_url}" target="_blank">{entry_title}</a> is staged for publishing. Click the link to complete.'))
        published_storymap_item, thumbnail_path = build_and_save_storymap(context, i)
        if published_storymap_item:
            context['published_storymap_items'][i] = published_storymap_item
        context['thumbnail_paths'][i] = thumbnail_path

def create_storymaps_btn(button, output5, context):
    """
    Create and save StoryMaps for each entry and display status.
    """
    with output5:
        output5.clear_output()
        print(f"Creating and saving {len(context['entries'])} StoryMaps...")
        create_and_save_storymaps(context)
        print("\nStep #5 complete. Ensure you have opened each story and checked for errors before continuing. \nOnce all stories have been successfully published, Click the Markdown text below and then click the 'Play' button twice to proceed.")

def build_collection(context):
    """
    Build a StoryMap Collection from published StoryMaps.

    Returns
    -------
    tuple
        (collection_title, collection_url)
    """
    gis = context['gis']
    classic_item = context['classic_item']
    classic_story_type = context['classic_story_type']
    thumbnail_paths = context['thumbnail_paths']
    default_thumbnail_path = context['default_thumbnail_path']
    published_storymap_items = context['published_storymap_items']
    new_theme = context['new_theme']
    collection = Collection()
    collection_title = context['classic_story_title']
    for i, story in enumerate(published_storymap_items):
        if story is None:
            print(f"Story {i+1} is None. Skipping.")
            continue
        try:
            item = Item(gis=gis, itemid=story.itemid)
            resources = item.resources.list()
            published_time = None
            draft_times = []
            for resource in resources:
                if resource['resource'].endswith('published_data.json'):
                    published_time = resource.get('modified')
                elif resource['resource'].startswith('draft_') and resource['resource'].endswith('.json'):
                    modified_time = resource.get('modified')
                    draft_times.append(modified_time)
            if draft_times and published_time and max(draft_times) > published_time:
                print(f"WARNING: There is an issue with '{story.title}'. Click the link to open the story builder and check for errors --> https://storymaps.arcgis.com/stories/{story.itemid}/edit")
            if safe_get_json(item):
                collection.add(item=story, title=story.title, thumbnail=str(thumbnail_paths[i]))
            else:
                print(f"There was a problem publishing '{story.title}'. Open the link {story.url} and try again.")
        except Exception as e:
            print(f"Error adding story '{story.title}' to Collection: {e}")
    # Set collection properties
    collection.content[0].title = collection_title
    collection.content[0].byline = ""
    collection.theme(new_theme)
    if classic_story_type == "accordion":
        collection.content[1].type = "tab"
    else:
        collection.content[1].type = classic_story_type
    # Set the Collection thumbnail to be the same as the classic story
    classic_thumbnail_path = download_thumbnail(Item(gis=gis, itemid=context['classic_id']), default_thumbnail_path, context)
    collection.content[1].media = Image(path=str(classic_thumbnail_path))
    # Publish
    published_collection = collection.save(title=collection_title, tags=["Classic Story Map to AGSM Conversion", "Story Map Series"], publish=True)
    context['collection_id'] = published_collection.id
    return collection_title, collection._url

def create_collection_btn(button, output6, context):
    """
    Create a StoryMap Collection from published StoryMaps and display status.
    """
    with output6:
        output6.clear_output()
        print(f"Creating Collection '{context['classic_story_title']}'...")
        context['collection_title'], context['collection_url'] = build_collection(context)
        display(HTML(f'Collection staged: <a href="{context["collection_url"]}" target="_blank">{context["collection_title"]}</a>.'))
        # print(f"Collection staged: '{context['collection_title']}' {context['collection_url']} 
        print(f"Click the link to open the Collection builder. Make any desired edits and then complete the publication of your converted StoryMap.")
        print("\nStep #6 complete. Once you've published the Collection, click the Markdown text below and then click the 'Play' button twice to proceed.")

# ======================================================================
# Content Management
# ======================================================================

def check_folder_btn(button, input7, output7, btn7_1, context):
    """
    Check if the output folder exists and prompt user to create it if not.
    """    
    gis = context['gis']
    classic_story_title = context['classic_story_title']
    output7.clear_output()
    output7.append_stdout("Checking...\n") 
    with output7:
        # output7.clear_output()
        # print("Checking...")
        if not classic_story_title:
            print("No classic StoryMap title found. Extract the story settings first.")
            return
        folder_name = "Collection-" + classic_story_title if classic_story_title else "Collection-Conversion"
        input7.value = folder_name
        context["folder_name"] = folder_name
        user_line7 = widgets.HBox([widgets.Label(value="Edit the folder name if desired -->"), input7])
        # Check if folder exists
        user = gis.users.me
        existing_folders = gis.content.folders.list(user.username)
        folder_names = [f.name for f in existing_folders]
        if folder_name in folder_names:
            print(f"Folder '{folder_name}' already exists. Saving results there.")
            print("\nStep #7 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")
        else:
            display(widgets.VBox([user_line7, btn7_1]))

def create_folder_btn(button, input7, output7, context):
    """
    Create a new folder in the user's ArcGIS Online content.
    """    
    gis = context['gis']
    folder_name = context['folder_name']
    with output7:
        output7.clear_output()
        folder_name = input7.value.strip() if input7.value.strip() else folder_name
        context['folder_name'] = folder_name
        try:
            gis.content.folders.create(folder=folder_name, owner=gis.users.me.username)
            print(f"Created folder '{folder_name}' to save entries and Collection.")
        except Exception as e:
            print(f"Error creating folder '{folder_name}': {e}")
        print("\nStep #7 complete. Click the Markdown text below and then click the 'Play' button twice to proceed.")

def move_item_to_folder(gis, item, folder_name):
    """
    Moves an ArcGIS Online item to a specified folder.
    """    
    try:
        if item.owner == gis.users.me.username:
            item.move(folder_name)
            print(f"Moved item '{item.title}' (ID: {item.itemid}) to folder '{folder_name}'.")
    except Exception as e:
        if "Item already exists" in str(e):
            print(f"Item '{item.title}' (ID: {item.itemid}) already exists in target folder")
        else:
            print(f"Error moving item '{item.title}' (ID: {item.itemid}): {e}")

def move_items_to_folder_btn(button, output8, context):
    """
    Moves a list of ArcGIS Online items into a specified folder.
    """
    gis = context['gis']
    folder_name = context['folder_name']
    classic_item = context['classic_item']
    published_storymap_items = context['published_storymap_items']
    collection_title = context['collection_title']
    collection_id = context['collection_id']
    with output8:
        output8.clear_output()
        if folder_name is None:
            print("No folder name found. Check for or create a folder first.")
            return
        if classic_item is None:
            print("No classic StoryMap item found. Fetch the story data first.")
            return
        if published_storymap_items is None or len(published_storymap_items) == 0:
            print("No published StoryMap items found. Create the StoryMaps first.")
            return
        if collection_title is None:
            print("No collection found. Create the collection first.")
            return
        print(f"Moving items to folder '{folder_name}'...")
        # Move the new stories
        for story_item in published_storymap_items:
            if story_item:
                move_item_to_folder(gis, story_item, folder_name)
        # Move the collection item
        try:
            #collection_search = gis.content.search(query=f'title:"{collection_title}" AND owner:{gis.users.me.username}', item_type="Collection", max_items=1)
            if collection_id:
                collection_item = gis.content.get(collection_id)
                move_item_to_folder(gis, collection_item, folder_name)
                # print(f"Moved collection '{collection_title}' to folder '{folder_name}'.")
            else:
                print(f"Could not find the collection item '{collection_title}' to move.")
        except Exception as e:
            print(f"Error moving collection item: {e}")
        print("\nStep #8 complete. Conversion complete!")