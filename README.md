# Golf Sim Stats

Upload scorecard images from your golf simulator. The app extracts scores, stores rounds, and shows analytics.

## How it works (simple)

1. **Auto crop** — Detects the scorecard rectangle and perspective-warps the image so it's flat and readable.
2. **Google Vision OCR** — Reads text from the image (hole numbers, player names, scores).
3. **Round storage** — Saves rounds to a local SQLite database. You can review and edit before saving.
4. **Analysis** — Computes leaderboards, trends, and ratings from your saved rounds.

## Setup

**Backend:**
```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Optional:** Copy `.env.example` to `.env` and set `GOOGLE_APPLICATION_CREDENTIALS` to your Google Cloud service account JSON path for better OCR. Without it, OCR quality is limited.

**Run:**
```bash
# Terminal 1
python -m uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

App: `http://localhost:5173` · API docs: `http://127.0.0.1:8000/docs`

---

## Analytics — how they're calculated

Most are straightforward: lowest scores, most wins, worst holes, and per-9 rates (birdies, pars, bogeys, etc.) are simple counts or averages.

The **Player Ratings** radar chart (Driving, Fairway, Short Game, Putting) is less obvious:

| Rating | What it uses | How it's scored |
|--------|--------------|------------------|
| **Driving** | Fairway hit % + average drive distance | 55% fairways hit, 45% distance (180 yd = 0, 300 yd = 100) |
| **Fairway** | Greens in regulation (GIR) % | Direct percentage, 0–100 |
| **Short game** | Scramble % + sand save % | 70% scramble rate, 30% sand save rate |
| **Putting** | Putts per hole | Fewer putts = higher score (1.5/hole ≈ 100, 2.4/hole ≈ 0) |

**Hole difficulty** groups holes by stroke index (1–4, 5–8, 9–12, 13–16) and shows your average score-to-par on each difficulty band.

---

## Sharing rounds & analytics

You can export rounds and analytics as static JSON and deploy to GitHub Pages for a read-only share site. See the export endpoint, `build:share` script, and `.github/workflows/deploy-share.yml` for details.
