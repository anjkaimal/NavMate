"""
Unit tests for NavMate bounding-box pipeline.

Covers:
  - AI response normalisation (new bbox format, legacy bounding_box format)
  - Coordinate remapping (tile_scale + offset)
  - Horizontal-strip duplicate detection
  - Union / merge operations
  - Election logic (single best element)
  - Voice instruction field unification
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ai_client import _normalise_element, AIResponseError
from grid_analyzer import (
    _are_duplicates,
    _union_elements,
    _elect_best,
    _geometric_dedup,
    _label_merge,
    _sanitize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _el(x, y, w, h, label="btn", voice="Click it"):
    return {
        "label": label,
        "bounding_box": {"x": x, "y": y, "width": w, "height": h},
        "voice_instruction": voice,
    }


# ===========================================================================
# 1. AI response normalisation
# ===========================================================================

class TestNormaliseElement:
    def test_new_bbox_format_converts_correctly(self):
        raw = {
            "bbox": {"x_min": 10, "y_min": 20, "x_max": 50, "y_max": 60},
            "label": "Zoom In",
            "voice_instruction": "Click plus to zoom",
        }
        el = _normalise_element(raw)
        bb = el["bounding_box"]
        assert bb["x"] == 10
        assert bb["y"] == 20
        assert bb["width"] == 40   # x_max - x_min
        assert bb["height"] == 40  # y_max - y_min

    def test_legacy_bounding_box_accepted(self):
        raw = {
            "label": "Zoom In",
            "bounding_box": {"x": 10, "y": 20, "width": 40, "height": 40},
            "explanation": "Click plus",
        }
        el = _normalise_element(raw)
        assert el["bounding_box"]["width"] == 40

    def test_voice_instruction_field_unification(self):
        # voice_instruction takes priority
        el = _normalise_element({
            "label": "X",
            "bounding_box": {"x": 0, "y": 0, "width": 10, "height": 10},
            "voice_instruction": "primary",
            "instruction": "secondary",
            "explanation": "tertiary",
        })
        assert el["voice_instruction"] == "primary"

    def test_instruction_fallback(self):
        el = _normalise_element({
            "label": "X",
            "bounding_box": {"x": 0, "y": 0, "width": 10, "height": 10},
            "instruction": "secondary",
        })
        assert el["voice_instruction"] == "secondary"

    def test_explanation_fallback(self):
        el = _normalise_element({
            "label": "X",
            "bounding_box": {"x": 0, "y": 0, "width": 10, "height": 10},
            "explanation": "tertiary",
        })
        assert el["voice_instruction"] == "tertiary"

    def test_rejects_missing_label(self):
        with pytest.raises(AIResponseError, match="missing 'label'"):
            _normalise_element({
                "bbox": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10},
                "voice_instruction": "x",
            })

    def test_rejects_zero_area_bbox(self):
        with pytest.raises(AIResponseError, match="zero/negative area"):
            _normalise_element({
                "label": "X",
                "bbox": {"x_min": 10, "y_min": 10, "x_max": 10, "y_max": 50},
                "voice_instruction": "x",
            })

    def test_rejects_missing_bounding_info(self):
        with pytest.raises(AIResponseError, match="missing 'bbox'"):
            _normalise_element({"label": "X", "voice_instruction": "x"})

    def test_bbox_float_values_rounded(self):
        raw = {
            "bbox": {"x_min": 10.4, "y_min": 20.6, "x_max": 50.3, "y_max": 60.7},
            "label": "X",
            "voice_instruction": "x",
        }
        el = _normalise_element(raw)
        bb = el["bounding_box"]
        assert bb["x"] == 10     # round(10.4)
        assert bb["y"] == 21     # round(20.6)
        assert bb["width"] == 40  # round(50.3 - 10.4) = round(39.9)
        assert bb["height"] == 40 # round(60.7 - 20.6) = round(40.1)


# ===========================================================================
# 2. Coordinate remapping (tile_scale + offset)
# ===========================================================================

class TestCoordinateRemapping:
    """
    Simulate _query_tile's remap step independently to verify the math.
    physical_x = round(ai_x * tile_scale + offset_x)
    """

    def _remap(self, ai_x, ai_y, ai_w, ai_h, tile_scale, offset_x, offset_y):
        return {
            "x":      round(ai_x * tile_scale + offset_x),
            "y":      round(ai_y * tile_scale + offset_y),
            "width":  round(ai_w * tile_scale),
            "height": round(ai_h * tile_scale),
        }

    def test_no_scale_no_offset(self):
        bb = self._remap(100, 50, 80, 30, 1.0, 0, 0)
        assert bb == {"x": 100, "y": 50, "width": 80, "height": 30}

    def test_offset_only(self):
        # Tile starts at physical (816, 0) — right tile on 1920-wide screen
        bb = self._remap(0, 35, 1104, 30, 1.0, 816, 0)
        assert bb["x"] == 816
        assert bb["y"] == 35
        assert bb["width"] == 1104

    def test_scale_and_offset(self):
        # 4K tile: phys_w=2208, ai_w=1920 → scale=2208/1920≈1.15
        scale = 2208 / 1920
        bb = self._remap(960, 50, 100, 30, scale, 0, 0)
        # centre of 1920-wide image → centre of 2208-wide physical tile
        assert bb["x"] == round(960 * scale)
        assert bb["width"] == round(100 * scale)

    def test_rounding_uses_nearest_not_floor(self):
        # AI says x=10.7 with scale=1, offset=0 → should round to 11, not floor to 10
        bb = self._remap(10.7, 0, 5, 5, 1.0, 0, 0)
        assert bb["x"] == 11

    def test_address_bar_left_tile_remapped_correctly(self):
        # 1920x1080 screen, tile(0,0): offset=(0,0), scale=1.0
        # Address bar visible at ai_x=0, ai_w=1104
        bb = self._remap(0, 35, 1104, 30, 1.0, 0, 0)
        assert bb["x"] == 0
        assert bb["width"] == 1104

    def test_address_bar_right_tile_remapped_correctly(self):
        # 1920x1080 screen, tile(1,0): offset=(816,0), scale=1.0
        # Address bar appears at ai_x=0 (tile's left edge) and spans full tile
        bb = self._remap(0, 35, 1104, 30, 1.0, 816, 0)
        assert bb["x"] == 816
        assert bb["x"] + bb["width"] == 1920  # reaches right edge of screen


# ===========================================================================
# 3. Horizontal-strip duplicate detection
# ===========================================================================

class TestHorizontalStripDedup:
    """
    The address bar appears as two side-by-side partial detections from
    adjacent tiles.  They must be identified as duplicates.
    """

    def test_address_bar_halves_are_duplicates(self):
        # 1920x1080, tile_w=960, overlap=15%
        a = {"x": 0,   "y": 35, "width": 1104, "height": 30}
        b = {"x": 816, "y": 35, "width": 1104, "height": 30}
        assert _are_duplicates(a, b), "Side-by-side address bar halves must be duplicates"

    def test_adjacent_toolbar_buttons_are_not_duplicates(self):
        # Back button and reload button sit next to each other — no x-overlap
        back   = {"x": 100, "y": 35, "width": 40, "height": 35}
        reload = {"x": 145, "y": 35, "width": 40, "height": 35}
        assert not _are_duplicates(back, reload), "Adjacent distinct buttons must not be merged"

    def test_completely_separate_elements_not_duplicates(self):
        address_bar = {"x": 180, "y": 35, "width": 900, "height": 30}
        search_box  = {"x": 660, "y": 580, "width": 600, "height": 44}
        assert not _are_duplicates(address_bar, search_box)

    def test_same_element_exact_overlap_is_duplicate(self):
        el = {"x": 100, "y": 100, "width": 50, "height": 50}
        assert _are_duplicates(el, dict(el))

    def test_iou_duplicate(self):
        a = {"x": 0,  "y": 0, "width": 100, "height": 100}
        b = {"x": 30, "y": 0, "width": 100, "height": 100}  # 70% x-overlap → IoU > 0.25
        assert _are_duplicates(a, b)

    def test_toolbar_button_left_of_address_bar_not_duplicate(self):
        # Reload button (x=140, w=38) ends at x=178.
        # Address bar starts at x=180 → zero x-overlap → not duplicates.
        address_bar = {"x": 180, "y": 35, "width": 900, "height": 30}
        reload_btn  = {"x": 140, "y": 35, "width": 38,  "height": 30}
        assert not _are_duplicates(address_bar, reload_btn)

    def test_button_mostly_inside_large_element_is_duplicate(self):
        # A 30x30 button that is 83% inside a wide bar IS correctly a duplicate
        # (containment threshold: 55% of smaller area covered → same element).
        big_bar  = {"x": 160, "y": 35, "width": 900, "height": 30}
        tiny_btn = {"x": 155, "y": 35, "width":  30, "height": 30}
        # overlap_area=750, min_area=900, ratio=0.83 > 0.55 → containment fires
        assert _are_duplicates(big_bar, tiny_btn)


# ===========================================================================
# 4. Union / merge
# ===========================================================================

class TestUnionElements:
    def test_union_spans_full_address_bar(self):
        left  = _el(0,   35, 1104, 30, "address bar")
        right = _el(816, 35, 1104, 30, "address bar")
        result = _union_elements([left, right])
        bb = result["bounding_box"]
        assert bb["x"] == 0
        assert bb["y"] == 35
        assert bb["width"] == 1920   # 0 to 816+1104
        assert bb["height"] == 30

    def test_union_preserves_voice_instruction_from_largest(self):
        small = _el(0, 0, 10, 10, voice="small")
        large = _el(0, 0, 100, 100, voice="large")
        result = _union_elements([small, large])
        assert result["voice_instruction"] == "large"

    def test_single_element_union_is_identity(self):
        el = _el(50, 80, 200, 40)
        result = _union_elements([el])
        assert result["bounding_box"] == el["bounding_box"]

    def test_union_three_partial_detections(self):
        a = _el(0,    0, 600, 30)
        b = _el(500,  0, 600, 30)
        c = _el(1000, 0, 500, 30)
        result = _union_elements([a, b, c])
        bb = result["bounding_box"]
        assert bb["x"] == 0
        assert bb["width"] == 1500   # 0 + 1000+500


# ===========================================================================
# 5. Election logic  (_elect_best)
# ===========================================================================

class TestElectBest:
    def test_prefers_square_button_over_address_bar(self):
        btn = _el(500, 133, 24, 24, label="Zoom In Button")
        bar = _el(155,  63, 560, 30, label="Chrome Address Bar")
        assert _elect_best([btn, bar])[0]["label"] == "Zoom In Button"

    def test_prefers_square_button_over_scrollbar(self):
        btn       = _el(50, 50, 28, 28, label="Zoom In")
        scrollbar = _el(720, 75, 14, 570, label="Vertical Scrollbar")
        assert _elect_best([btn, scrollbar])[0]["label"] == "Zoom In"

    def test_prefers_smaller_among_equally_square(self):
        # Both square, but one is larger
        small = _el(10, 10, 20, 20, label="Small")
        large = _el(20, 20, 60, 60, label="Large")
        assert _elect_best([small, large])[0]["label"] == "Small"

    def test_single_element_returned_unchanged(self):
        el = _el(0, 0, 30, 30, label="Only")
        result = _elect_best([el])
        assert result[0]["label"] == "Only"

    def test_empty_list_returns_empty(self):
        assert _elect_best([]) == []

    def test_real_log_candidates_elects_pdf_options_not_bars(self):
        """Reproduces the exact candidates from the error log."""
        candidates = [
            _el(697, 133,  28,  28, label="PDF More Options"),
            _el(155,  63, 560,  30, label="Chrome Address Bar"),
            _el(559, 645, 175,  40, label="Windows Search Bar"),
            _el(723,  75,  14, 570, label="Vertical Scrollbar"),
        ]
        winner = _elect_best(candidates)[0]
        # Square 28x28 button wins over bars
        assert winner["label"] == "PDF More Options"

    def test_zoom_in_button_beats_all_log_candidates(self):
        candidates = [
            _el(500, 133,  24,  24, label="Zoom In Button"),
            _el(697, 133,  28,  28, label="PDF More Options"),
            _el(155,  63, 560,  30, label="Chrome Address Bar"),
            _el(723,  75,  14, 570, label="Vertical Scrollbar"),
        ]
        winner = _elect_best(candidates)[0]
        # 24x24 is more square-and-smaller than 28x28
        assert winner["label"] == "Zoom In Button"


# ===========================================================================
# 6. Sanitize  (clamp to screen bounds)
# ===========================================================================

class TestSanitize:
    def test_clips_to_screen_bounds(self):
        el = _el(-10, -5, 200, 100)   # starts off-screen
        result = _sanitize([el], full_w=1920, full_h=1080)
        bb = result[0]["bounding_box"]
        assert bb["x"] == 0
        assert bb["y"] == 0
        assert bb["width"] == 190   # 200 - 10 clipped from left
        assert bb["height"] == 95

    def test_drops_zero_area_element(self):
        el = _el(1920, 0, 100, 100)   # starts at right edge → zero width after clip
        result = _sanitize([el], full_w=1920, full_h=1080)
        assert result == []

    def test_valid_element_passes_through(self):
        el = _el(100, 100, 50, 50)
        result = _sanitize([el], full_w=1920, full_h=1080)
        assert len(result) == 1
        assert result[0]["bounding_box"]["x"] == 100


# ===========================================================================
# 7. Geometric dedup produces union, not selection
# ===========================================================================

class TestGeometricDedupUnion:
    def test_side_by_side_address_bar_unioned(self):
        left  = _el(0,   35, 1104, 30, label="address bar")
        right = _el(816, 35, 1104, 30, label="navigation bar")  # different label
        result = _geometric_dedup([left, right])
        assert len(result) == 1
        bb = result[0]["bounding_box"]
        assert bb["x"] == 0
        assert bb["width"] == 1920

    def test_unrelated_elements_stay_separate(self):
        btn        = _el(50,  50, 28, 28, label="Zoom In")
        search_box = _el(660, 580, 600, 44, label="Search Box")
        result = _geometric_dedup([btn, search_box])
        assert len(result) == 2

    def test_single_element_passes_through(self):
        el = _el(100, 100, 50, 50)
        result = _geometric_dedup([el])
        assert len(result) == 1
