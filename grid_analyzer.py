"""
Grid-based screenshot analysis.

Splits the screen into overlapping tiles, queries the AI on each tile in
parallel, then runs a three-stage post-processing pipeline to produce a
clean set of non-duplicate bounding boxes:

  Stage 0 – core-region filter   (in _query_tile)
  Stage 1 – label-aware merge    (_label_merge)
  Stage 2 – geometric dedup      (_geometric_dedup)

Why two detections of the address bar are expected and how they're resolved
---------------------------------------------------------------------------
The address bar spans the full screen width.  With a 2×2 grid, the left
tile captures physical columns [0, tile_w+overlap] and the right tile
captures [tile_w-overlap, full_w].  Each tile's AI sees its own slice of
the address bar, so each returns a detection.  Because each detection's
CENTRE is inside its own tile's core zone, both survive the core filter —
this is by design.

These two partial detections must be merged into one full-width box by the
post-processing stages:

  Stage 1 (label-aware merge): if both tiles report the same canonical
    label the boxes are unioned immediately.

  Stage 2 (geometric dedup): catches any surviving pair via the
    horizontal-strip test — same y-band + overlapping x-ranges —
    regardless of label.  Unlike the other geometric tests, this fires
    for side-by-side boxes that share a row, which is exactly the
    tile-split pattern.  Matched groups are UNIONED (not just deduplicated
    by discarding one), so the result is the correct full-width box.
"""

import concurrent.futures
import math
from collections import defaultdict
from typing import Callable

from ai_client import AIResponseError, query_ai
from logger import get_logger
from screenshot import capture_screen_tiles

log = get_logger(__name__)

# ── Duplicate-detection thresholds (geometric dedup stage) ────────────
_IOU_THRESHOLD         = 0.25
_CONTAINMENT_THRESHOLD = 0.55   # fraction of *smaller* box covered
_CENTRE_THRESHOLD      = 0.30   # centre-dist / avg-diagonal

# Horizontal-strip test: catches tile-split wide elements (e.g., address bar).
# Two boxes qualify if their y-bands overlap by >= this fraction of the shorter
# height AND their x-ranges overlap by >= this fraction of the WIDER box's width.
# Using max-width (not min-width) in the denominator keeps false-positive rate low
# when a small button's box barely clips a wide element's box.
_STRIP_Y_THRESHOLD     = 0.60   # y-overlap / min(height_a, height_b)
_STRIP_X_THRESHOLD     = 0.20   # x-overlap / max(width_a, width_b)

# ── Label-aware merge ─────────────────────────────────────────────────
# Synonyms are normalised to a canonical form before comparing labels.
_LABEL_SYNONYMS: dict[str, str] = {
    # Address bar / omnibox variants
    "omnibox":                    "address bar",
    "url bar":                    "address bar",
    "url input":                  "address bar",
    "url field":                  "address bar",
    "url box":                    "address bar",
    "chrome address bar":         "address bar",
    "browser address bar":        "address bar",
    "address field":              "address bar",
    "address bar / omnibox":      "address bar",
    "location bar":               "address bar",
    "navigation bar":             "address bar",
    "chrome omnibox":             "address bar",
    # Search bar variants
    "search input":               "search bar",
    "search field":               "search bar",
    "search box":                 "search bar",
    "search input field":         "search bar",
    "search text box":            "search bar",
    "google search":              "search bar",
    "google search bar":          "search bar",
    "google search input":        "search bar",
    "google searchbar":           "search bar",
    "ask google":                 "search bar",
    "search google":              "search bar",
    "google search field":        "search bar",
}

StatusCallback = Callable[[int], None]


# ======================================================================
# Public entry point
# ======================================================================

def analyze_grid(
    user_query: str,
    app_key: str,
    n_cols: int = 3,
    n_rows: int = 2,
    overlap_pct: float = 0.15,
    status_cb: StatusCallback | None = None,
) -> tuple[list[dict], int, int]:
    """
    Capture -> tile -> AI (parallel) -> post-process -> return.

    Returns (elements, full_physical_w, full_physical_h).
    """
    if status_cb:
        status_cb(0)

    tiles, full_w, full_h = capture_screen_tiles(n_cols, n_rows, overlap_pct)
    log.debug(f"Grid {n_cols}×{n_rows}: {len(tiles)} tiles, full {full_w}×{full_h}")

    if status_cb:
        status_cb(1)

    raw: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_cols * n_rows) as pool:
        futures = {pool.submit(_query_tile, t, user_query, app_key): t for t in tiles}
        for future in concurrent.futures.as_completed(futures):
            tile  = futures[future]
            label = f"({tile['offset_x']},{tile['offset_y']})"
            try:
                kept = future.result()
                raw.extend(kept)
                log.debug(f"Tile {label}: {len(kept)} elements after core filter")
            except AIResponseError as exc:
                log.warning(f"Tile {label} AIResponseError: {exc}")
            except Exception as exc:
                log.warning(f"Tile {label} failed: {exc}")

    if status_cb:
        status_cb(2)

    result = _postprocess(raw, full_w, full_h)
    log.debug(f"Grid done: {len(raw)} raw -> {len(result)} final")
    return result, full_w, full_h


# ======================================================================
# Per-tile query + core-region filter  (Stage 0)
# ======================================================================

def _query_tile(tile: dict, user_query: str, app_key: str) -> list[dict]:
    """
    Query AI, remap bounding boxes to full-screen physical coordinates,
    then discard any element whose centre falls outside this tile's core zone.

    This is the primary duplicate-prevention mechanism.  Because every
    screen pixel belongs to exactly one tile's core, each UI element can
    only be claimed by one tile — no duplicates can enter the pipeline.
    """
    elements = query_ai(tile["b64"], user_query, app_key, mode="guide")

    ts = tile["tile_scale"]
    ox, oy = tile["offset_x"], tile["offset_y"]
    cx1, cy1 = tile["core_x1"], tile["core_y1"]
    cx2, cy2 = tile["core_x2"], tile["core_y2"]

    kept: list[dict] = []
    for el in elements:
        bb = el["bounding_box"]
        remapped = {
            "x":      round(bb["x"]      * ts + ox),
            "y":      round(bb["y"]      * ts + oy),
            "width":  round(bb["width"]  * ts),
            "height": round(bb["height"] * ts),
        }
        el = {**el, "bounding_box": remapped}

        centre_x = remapped["x"] + remapped["width"]  / 2
        centre_y = remapped["y"] + remapped["height"] / 2

        # Half-open intervals on interior edges ([cx1, cx2)) ensure every screen
        # pixel belongs to exactly one tile's core.  The last column/row closes
        # its far edge (<=) so elements at the screen boundary are never dropped.
        is_last_col = (cx2 == tile.get("_full_w", 0))
        is_last_row = (cy2 == tile.get("_full_h", 0))
        in_x = (cx1 <= centre_x <= cx2) if is_last_col else (cx1 <= centre_x < cx2)
        in_y = (cy1 <= centre_y <= cy2) if is_last_row else (cy1 <= centre_y < cy2)
        in_core = in_x and in_y

        if in_core:
            kept.append(el)
        else:
            log.debug(
                f"  core-filtered '{el.get('label','')}' "
                f"centre ({centre_x:.0f},{centre_y:.0f}) not in "
                f"core ({cx1},{cy1})–({cx2},{cy2})"
            )

    return kept


# ======================================================================
# Post-processing pipeline  (Stages 1 & 2)
# ======================================================================

def _postprocess(elements: list[dict], full_w: int, full_h: int) -> list[dict]:
    elements = _sanitize(elements, full_w, full_h)
    elements = _label_merge(elements)
    elements = _geometric_dedup(elements)
    return elements


# ── Stage 1a: sanitise ────────────────────────────────────────────────

def _sanitize(elements: list[dict], full_w: int, full_h: int) -> list[dict]:
    """Clamp boxes to screen bounds; drop zero-area results."""
    out: list[dict] = []
    for el in elements:
        bb = el["bounding_box"]
        x  = max(0, bb["x"])
        y  = max(0, bb["y"])
        x2 = min(full_w, bb["x"] + bb["width"])
        y2 = min(full_h, bb["y"] + bb["height"])
        w, h = x2 - x, y2 - y
        if w > 0 and h > 0:
            out.append({**el, "bounding_box": {"x": x, "y": y, "width": w, "height": h}})
    return out


# ── Stage 1b: label-aware merge ───────────────────────────────────────

def _normalise_label(label: str) -> str:
    key = label.lower().strip()
    return _LABEL_SYNONYMS.get(key, key)


def _label_merge(elements: list[dict]) -> list[dict]:
    """
    Group elements with the same normalised label that share a vertical band
    (their Y-ranges overlap by ≥ 60 %).  Within each group, union all bounding
    boxes into one.  This repairs wide elements (address bar, toolbars) that a
    tile boundary split into two partial detections.
    """
    if len(elements) <= 1:
        return elements

    # Bucket by normalised label
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, el in enumerate(elements):
        buckets[_normalise_label(el.get("label", ""))].append(i)

    merged_indices: set[int] = set()
    result: list[dict] = []

    for key, indices in buckets.items():
        if len(indices) == 1:
            result.append(elements[indices[0]])
            merged_indices.add(indices[0])
            continue

        # Within this label group, cluster by vertical band
        bands: list[dict] = []    # each band: {"y1", "y2", "members": [idx]}
        for idx in indices:
            bb  = elements[idx]["bounding_box"]
            ey1 = bb["y"]
            ey2 = bb["y"] + bb["height"]

            placed = False
            for band in bands:
                overlap = min(band["y2"], ey2) - max(band["y1"], ey1)
                min_h   = min(band["y2"] - band["y1"], ey2 - ey1)
                if min_h > 0 and overlap / min_h >= 0.6:
                    band["members"].append(idx)
                    band["y1"] = min(band["y1"], ey1)
                    band["y2"] = max(band["y2"], ey2)
                    placed = True
                    break

            if not placed:
                bands.append({"y1": ey1, "y2": ey2, "members": [idx]})

        for band in bands:
            group = [elements[i] for i in band["members"]]
            result.append(_union_elements(group))
            for i in band["members"]:
                merged_indices.add(i)

    # Append anything that wasn't processed (safety net)
    for i, el in enumerate(elements):
        if i not in merged_indices:
            result.append(el)

    log.debug(f"Label-merge: {len(elements)} -> {len(result)}")
    return result


def _union_elements(group: list[dict]) -> dict:
    """Merge a list of same-element detections into one union bounding box."""
    bbs = [el["bounding_box"] for el in group]
    x1  = min(bb["x"]              for bb in bbs)
    y1  = min(bb["y"]              for bb in bbs)
    x2  = max(bb["x"] + bb["width"]  for bb in bbs)
    y2  = max(bb["y"] + bb["height"] for bb in bbs)
    # Keep the label/explanation from the largest detection (most context)
    best = max(group, key=lambda el: el["bounding_box"]["width"] * el["bounding_box"]["height"])
    return {
        "label":       best["label"],
        "bounding_box": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
        "explanation": best["explanation"],
    }


# ── Stage 2: geometric dedup ──────────────────────────────────────────

def _geometric_dedup(elements: list[dict]) -> list[dict]:
    """
    Final safety net: union-find over all remaining elements using a
    four-way similarity test (IoU + containment + centre proximity +
    horizontal-strip).  Each connected component is collapsed into one
    element by unioning all bounding boxes, so the result is always the
    tightest box that fully covers the detected element.
    """
    if not elements:
        return []

    n = len(elements)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            if _are_duplicates(elements[i]["bounding_box"],
                               elements[j]["bounding_box"]):
                union(i, j)

    # Group indices by component root, then union all boxes in each group.
    # Unioning (not selecting) ensures that two partial detections of the same
    # wide element (e.g., address bar split across tiles) produce one correct
    # full-width box rather than one half-width box.
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    result = [_union_elements([elements[i] for i in idxs])
              for idxs in groups.values()]
    log.debug(f"Geometric-dedup: {n} -> {len(result)}")
    return result


def _are_duplicates(a: dict, b: dict) -> bool:
    if _iou(a, b) >= _IOU_THRESHOLD:
        return True
    inter    = _intersection_area(a, b)
    min_area = min(a["width"] * a["height"], b["width"] * b["height"])
    if min_area > 0 and inter / min_area >= _CONTAINMENT_THRESHOLD:
        return True
    cx_a = a["x"] + a["width"]  / 2;  cy_a = a["y"] + a["height"] / 2
    cx_b = b["x"] + b["width"]  / 2;  cy_b = b["y"] + b["height"] / 2
    dist     = math.hypot(cx_a - cx_b, cy_a - cy_b)
    avg_diag = (math.hypot(a["width"], a["height"]) +
                math.hypot(b["width"], b["height"])) / 2
    if avg_diag > 0 and dist / avg_diag <= _CENTRE_THRESHOLD:
        return True
    # Horizontal-strip test: fires for wide elements split across a tile boundary.
    # Two partial detections of the same row element will share a y-band AND have
    # overlapping x-ranges (because tiles overlap).  Adjacent distinct elements
    # at the same y-level won't overlap in x, so false positives are rare.
    y_over = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    min_h  = min(a["height"], b["height"])
    x_over = min(a["x"] + a["width"],  b["x"] + b["width"])  - max(a["x"], b["x"])
    max_w  = max(a["width"], b["width"])
    return (min_h > 0 and y_over / min_h >= _STRIP_Y_THRESHOLD
            and max_w > 0 and x_over / max_w >= _STRIP_X_THRESHOLD)


def _iou(a: dict, b: dict) -> float:
    inter = _intersection_area(a, b)
    if not inter:
        return 0.0
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def _intersection_area(a: dict, b: dict) -> int:
    ix1 = max(a["x"],              b["x"])
    iy1 = max(a["y"],              b["y"])
    ix2 = min(a["x"] + a["width"], b["x"] + b["width"])
    iy2 = min(a["y"] + a["height"], b["y"] + b["height"])
    return max(0, ix2 - ix1) * max(0, iy2 - iy1)
