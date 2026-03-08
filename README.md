# Golf Sim Stats

Upload scorecard and stats images from your golf simulator, review or edit the extracted data, and save rounds. View round history and basic analytics.

## Backend (FastAPI)

### Setup

```bash
cd /path/to/GolfSimStats
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
```

### Environment (optional)

| Variable | Description |
|----------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to a Google Cloud **service account** JSON key file. When set, the app uses **Google Cloud Vision** for OCR on uploaded images. Create a key in [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create service account → Keys → Add JSON key. Do not commit the key file. |

Copy `.env.example` to `.env` and set these if needed.

### Run

```bash
python -m uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000`  
Docs: `http://127.0.0.1:8000/docs`

## Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:5173`

## Scorecard Parse V2

A layout-first, constraints-driven scorecard extraction pipeline that aims to reduce OCR errors from ~30% to <5% on hard photos.  It lives alongside the existing parser and is accessed via a separate endpoint.

### How it works

1. **Panel detection** -- auto-detects the scorecard rectangle and perspective-warps it (skipped if the image was already cropped by the frontend `ImageWarpEditor`).
2. **Grid reconstruction** -- tries two strategies and picks the higher-confidence result:
   - *Line-based*: adaptive threshold → morphological line enhancement → HoughLinesP → cluster x/y into row/column separators.  Best when the scorecard has visible grid lines.
   - *Text-box clustering*: cluster Vision OCR token centres on x/y axes.  Fallback when grid lines are faint or absent.
3. **Token-to-cell assignment** -- each OCR word box is placed into the nearest grid cell; candidates are ranked by Vision confidence, proximity, and numeric-likeness.
4. **Semantic inference** -- identifies hole-number row, PAR, stroke-index, OUT/IN/TOTAL columns, and player rows using the reconstructed grid structure.
5. **Constraint validation + repair** -- checks hard constraints (sub-total sums) and applies a bounded beam search over OCR confusion pairs (3↔8, 5↔6, 4↔9, 1↔7, 0↔8) to fix misreads automatically.

### Endpoint

```
POST /api/scorecard/parse_v2
```

| Field | Type | Description |
|---|---|---|
| `scorecard_image` | file (required) | JPEG/PNG scorecard image |
| `image_date_hint` | string | `YYYY-MM-DD` date hint |
| `scorecard_is_warped` | string | `"true"` to skip panel detection |
| `debug` | string | `"true"` to include `debug_layout` in response |

Returns the same `DraftRound` shape as `/api/rounds/ocr-draft`, plus:
- `repaired_cells` -- list of auto-corrected cells with old/new values and reason.
- `debug_layout` (when `debug=true`) -- strategy used, grid boundaries, per-cell confidence, repaired cells.

### Running without Vision

When `GOOGLE_APPLICATION_CREDENTIALS` is not set, Vision OCR returns no word boxes.  The v2 parser will still run but produce an empty/low-confidence result.  To test locally without Vision, mock `extract_word_boxes` in tests (see `tests/test_scorecard_parse_v2_api.py`).

### Debugging failures

1. Call the endpoint with `debug=true` to inspect `debug_layout` in the JSON response.
2. Check `strategy_used` (`line_based` vs `textbox_clustering`) and `strategy_confidence`.
3. Look at `repaired_cells` for any auto-corrections and `cell_confidences` for per-cell OCR quality.
4. Use `app.scorecard.debug.render_debug_overlay(image_bytes, geometry, tokens, cell_values)` to generate a JPEG overlay with grid lines and token bounding boxes for visual inspection.

### Adding new simulator templates

The v2 parser uses generic layout heuristics rather than template matching.  If a new simulator produces scorecards with unusual layouts:
- Adjust keyword sets in `app/scorecard/semantic_inference.py` (`_PAR_KW`, `_SI_KW`, `_SKIP_ROW_KW`).
- Tune clustering tolerances in `app/scorecard/grid_reconstruction.py` (`_cluster_1d` gap thresholds).
- Add OCR confusion pairs to `app/scorecard/validator.py` `CONFUSION_MAP`.
- Add a test fixture image and expected output under `tests/`.

### Accuracy and remaining failure modes

**Expected improvements**: constraints-driven repair eliminates the most common single-digit OCR confusions (3↔8, 5↔6, etc.) that v1 cannot catch.  Layout-first grid reconstruction is more robust against misaligned text clustering on busy backgrounds and moiré patterns.

**Remaining failure modes**:
- Images with no visible grid lines *and* very few OCR tokens (< 6 words) -- the parser cannot infer grid structure.
- Multi-page or stitched scorecards with >1 table -- only a single grid is detected.
- Heavily rotated images (> 15°) that defeat both panel detection and OCR -- the frontend warp editor should be used first.
- Stats-page extraction is not yet covered by v2; the existing `predict_stats` is still used.

### Tests

```bash
python -m pytest tests/ -v
```

V2-specific tests:
- `tests/test_scorecard_layout_parser.py` -- clustering, token assignment, semantic inference, adapter.
- `tests/test_scorecard_validator.py` -- constraint checks, confusion repair, edge cases.
- `tests/test_scorecard_parse_v2_api.py` -- endpoint contract, debug flag, error handling.
