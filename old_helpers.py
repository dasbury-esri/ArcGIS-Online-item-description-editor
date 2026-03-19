# Helper functions
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


def get_all_items_for_user(gis, username, page_size=100):
    """
    Get all items for one user, including root and all folders.
    
    PARAMS
    gis: authenticated GIS object
    username: string username to query
    page_size: number of items to request per page (default 100, max 10000)
    """
    print(f"  Scanning user: {username}",end="")
    user_items = []

    # Root folder items (paged)
    root_items = _paged_get(
        gis,
        path=f"content/users/{username}",
        params={},
        records_key="items",
        page_size=page_size
    )
    user_items.extend(root_items)

    # Need a call to read folder list
    root_resp = gis._con.get(f"content/users/{username}", {"f": "json"})
    folders = root_resp.get("folders", [])

    # Folder items (paged per folder)
    for folder in folders:
        folder_id = folder.get("id")
        if not folder_id:
            continue
        folder_items = _paged_get(
            gis,
            path=f"content/users/{username}/{folder_id}",
            params={},
            records_key="items",
            page_size=page_size
        )
        user_items.extend(folder_items)

    print(f" Found {len(user_items)} items")
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

def scan_org_licenseinfo_without_10k_cap(gis, target_strings=None, pause_seconds=0.0):
    """
    Exhaustive scan of org items (no 10k search cap) by traversing users/folders/items.

    PARAMS
    gis: authenticated GIS object
    target_strings: list of strings to search for in the licenseInfo field (case-insensitive)
    pause_seconds: number of seconds to pause between item metadata requests (default 0, can be used to avoid hitting rate limits)

    RETURNS 
    matches_df: DataFrame of items whose licenseInfo field contains any of the target strings, with columns for item_id, title, owner, type, url, matched_terms, and full licenseInfo text
    errors_df: DataFrame of any errors encountered at the user level, with columns for username and error message
    all_items_df: DataFrame of all unique item_ids scanned, with a single column "item_id"
    """
    if target_strings is None:
        target_strings = TARGET_STRINGS

    usernames = get_all_org_usernames(gis)
    print(f"Users found: {len(usernames)}")

    matches = []
    errors = []
    all_seen = set()
    total_scanned = 0

    for u_idx, username in enumerate(usernames, start=1):
        try:
            items = get_all_items_for_user(gis, username)
            for item in items:
                item_id = item.get("id")
                if not item_id or item_id in all_seen:
                    continue
                all_seen.add(item_id)

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
                print(f"Processed users: {u_idx}/{len(usernames)} | unique items scanned: {total_scanned}")

        except Exception as exc:
            errors.append({
                "username": username,
                "error": str(exc)
            })

    matches_df = pd.DataFrame(matches)
    errors_df = pd.DataFrame(errors)
    all_items_df = pd.DataFrame({"item_id": list(all_seen)})

    print(f"Done. Unique items scanned: {len(all_seen)}")
    print(f"Matches found: {len(matches_df)}")
    print(f"User-level errors: {len(errors_df)}")

    return matches_df, errors_df, all_items_df