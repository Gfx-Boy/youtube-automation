# Video AI — Automated Short-Form Video Generation

A 9-module system for generating beat-synced, styled 9:16 short-form videos (Shorts/Reels/TikToks) with full re-editing support.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GOOGLE COLAB (Training)                   │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ Data Collect  │→│ Train Aesthetic   │→│ Export .pt    │  │
│  │ + Labelling   │  │ + Style Scorer   │  │ + configs    │  │
│  └──────────────┘  └──────────────────┘  └──────┬───────┘  │
└─────────────────────────────────────────────────┼───────────┘
                          Google Drive            │
                                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   MAC MINI M4 (Runtime)                      │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │1.Ingest  │→│3.Scenes  │→│4.Rank    │→│6.Plan    │   │
│  │  yt-dlp  │  │SceneDetect│ │CLIP+ML  │  │Timeline  │   │
│  └──────────┘  └──────────┘  └──────────┘  └────┬─────┘   │
│  ┌──────────┐  ┌──────────┐                      │          │
│  │2.Images  │  │5.Audio   │                      ▼          │
│  │ Search   │  │ librosa  │  ┌──────────┐  ┌──────────┐   │
│  └──────────┘  └──────────┘  │7.Text    │→│8.Render  │   │
│                               │ Engine   │  │  FFmpeg  │   │
│                               └──────────┘  └────┬─────┘   │
│                                                   │          │
│                               ┌──────────┐       │          │
│                               │9.Re-Edit │←──────┘          │
│                               │ Patch TL │                   │
│                               └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

## Execution Order

### Phase 1: Training (Google Colab) — DO THIS FIRST
1. Open `notebooks/colab_training/01_data_collection.ipynb` in Colab
2. Add your source video URLs
3. Run all cells → extracts frames, computes CLIP embeddings, auto-labels
4. Open `notebooks/colab_training/02_train_aesthetic_ranker.ipynb`
5. Run all cells → trains aesthetic ranker + style scorer
6. Copy output files from Google Drive to `weights/`:
   - `aesthetic_ranker.pt`
   - `style_ranker.pt`
   - `thresholds.json`
   - `prompt_weights.json`

### Phase 2: Runtime (Mac Mini M4)
```bash
# 1. Setup
cd video_ai
bash scripts/setup.sh

# 2. Activate environment
source .venv/bin/activate

# 3. Generate a video
python -m app.cli generate \
  --name "My First Edit" \
  --audio path/to/song.mp3 \
  --urls "https://youtube.com/watch?v=..." \
  --style dark_cinematic

# 4. Re-edit the same project
python -m app.cli edit \
  --project <project_id> \
  --action change_font \
  --params '{"font": "Impact", "font_size": 72}'

# 5. Re-render
python -m app.cli render --project <project_id>
```

## Modules

| # | Module | Purpose | Tools |
|---|--------|---------|-------|
| 1 | Ingestion | Download/import media | yt-dlp, Python |
| 2 | Asset Search | Fetch still images | Google Custom Search API |
| 3 | Scene Detection | Split videos into shots | PySceneDetect, OpenCV |
| 4 | Clip Ranking | Score & rank clips | OpenCLIP, PyTorch, OpenCV |
| 5 | Audio Analysis | Beat/tempo/section detection | librosa |
| 6 | Timeline Planner | Rule-based edit decisions | Python |
| 7 | Text Engine | Animated text overlays | Pillow, FFmpeg drawtext |
| 8 | Renderer | Final mp4 output | FFmpeg |
| 9 | Re-Editor | Patch timeline & re-render | Python |

## Style Presets

| Preset | Description |
|--------|-------------|
| `default` | Balanced cinematic with beat sync |
| `dark_cinematic` | Slow cuts, smooth transitions, dramatic drops |
| `hype_energy` | Fast cuts, flash, punch zooms |
| `smooth_emotional` | Soft, slow, ideal for sad/romantic |
| `meme_edit` | Fast ironic, hard cuts, bass-boosted feel |

## Project Structure

```
video_ai/
├── app/
│   ├── api/              # FastAPI REST endpoints
│   ├── core/             # Config, schemas, pipeline, project manager
│   ├── ingestion/        # Module 1 — download/import
│   ├── search/           # Module 2 — image search
│   ├── analysis/         # Modules 3-5 — scenes, clips, audio
│   ├── planning/         # Module 6 — timeline planner
│   ├── rendering/        # Modules 7-8 — text engine + renderer
│   ├── editing/          # Module 9 — re-editor
│   ├── models/           # Model loader utility
│   ├── presets/          # Style & transition presets
│   └── utils/
├── projects/             # Per-project data (source of truth)
│   └── <project_id>/
│       ├── project.json  # ← THE source of truth
│       ├── inputs/
│       ├── raw_media/
│       ├── scenes/
│       ├── images/
│       ├── audio/
│       ├── cache/
│       └── renders/
├── notebooks/colab_training/   # Colab notebooks
├── weights/              # Trained model files
├── fonts/                # Custom fonts
├── luts/                 # Color grading LUTs
├── scripts/
├── requirements.txt
└── .env
```

## Key Design Decisions

- **project.json is the source of truth** — never the final mp4
- **Image search is provider-based** — first provider = Google Custom Search, swappable later
- **Timeline is rule-based** — section type determines cut duration, transitions, effects
- **Trained models are optional** — system works with CLIP zero-shot; trained rankers improve quality
- **Re-editing patches the timeline** — doesn't start from zero

## API

Start the server:
```bash
python -m app.cli serve
```

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/presets` | List style presets |
| GET | `/projects` | List all projects |
| POST | `/projects` | Create a project |
| GET | `/projects/{id}` | Get project details |
| POST | `/projects/{id}/generate` | Run full pipeline |
| POST | `/projects/{id}/edit` | Apply edit commands |
| POST | `/projects/{id}/render` | Re-render timeline |

## Requirements

### Mac Mini (Runtime)
- Python 3.11+
- FFmpeg
- yt-dlp (installed via pip or brew)

### Google Colab (Training)
- Free tier is sufficient for the MLP training
- GPU helpful for embedding computation

### Optional
- Google Custom Search API key (for image search)
- Custom fonts (.ttf files in `fonts/`)
- LUT files (.cube in `luts/`)
# youtube-automation
