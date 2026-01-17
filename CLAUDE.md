# StudyFlow Suite - Project Documentation

## Quick Reference

**Entry Point**: `python -m StudyFlow.frontend.main`

**Backend URL**: `https://studyflowsuite.onrender.com` (deployed on Render)

**Three Study Modes**:
- **FreeFlow**: Automated quiz answering - takes screenshots, OCR, AI voting, clicks answers
- **FocusFlow**: Real-time overlay showing answers with explanations
- **DeepFlow**: AI-generated practice questions on any topic

---

## Project Structure

```
StudyFlow Suite/
├── StudyFlow/
│   ├── frontend/                 # PySide6 GUI (runs locally)
│   │   ├── main.py               # Entry point
│   │   ├── studyflow_menu.py     # Main menu with tabs
│   │   ├── gui.py                # FreeFlow window
│   │   ├── focusflow.py          # FocusFlow overlay
│   │   ├── deepflow_gui.py       # DeepFlow quiz interface
│   │   ├── core_engine.py        # Quiz processing loop
│   │   ├── ocr_extraction.py     # OCR and layout parsing
│   │   ├── screen_interaction.py # Mouse/keyboard automation
│   │   └── button_capture.py     # Submit button capture
│   │
│   ├── backend/                  # Flask API (deployed on Render)
│   │   ├── app.py                # All REST endpoints
│   │   ├── ai_manager.py         # AI voting (OpenAI + Claude + Cohere)
│   │   ├── ai_clients/           # Individual AI clients
│   │   ├── image_processing.py   # Image preprocessing
│   │   ├── ocr_logic.py          # Fallback OCR parsing
│   │   ├── deepflow.py           # Question generation
│   │   ├── tasks.py              # Celery async tasks
│   │   └── submit_button_storage.py
│   │
│   ├── Media/                    # Logo images (StudyFlow.png, FreeFlow.png, etc.)
│   ├── config.py                 # API keys, Tesseract path
│   └── logging_utils.py          # Debug logging
│
├── .env                          # Environment variables (local)
├── requirements.txt              # Python dependencies
└── Dockerfile                    # Production deployment
```

---

## Key Import Paths

All frontend imports use `StudyFlow.frontend.xxx`:
```python
from StudyFlow.frontend.gui import MainWindow
from StudyFlow.frontend.ocr_extraction import get_tagged_words_from_region
from StudyFlow.frontend.screen_interaction import human_move_click
```

Backend imports use `StudyFlow.backend.xxx`:
```python
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
from StudyFlow.backend.image_processing import preprocess_image
```

Top-level utilities:
```python
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
```

---

## External Dependencies

| Service | Purpose | Notes |
|---------|---------|-------|
| OpenAI | GPT-4o for answers, GPT-3.5 for layout | API key in config.py |
| Anthropic | Claude 3.7 Sonnet for voting | API key in config.py |
| Cohere | Command R+ for voting | API key in config.py |
| Tesseract | Local OCR engine | `brew install tesseract` on Mac |
| PostgreSQL | Q&A caching, users | On Render |
| Redis | Celery message queue | On Render |
| Stripe | Subscriptions | Webhook at /api/stripe_webhook |
| SendGrid | Email delivery | Access key emails |

---

## Backend API Endpoints

**Question Processing**:
- `POST /api/process` - Submit question for AI answer
- `GET /api/status/<task_id>` - Poll async task status
- `POST /api/focusflow` - Full pipeline (image → answer + explanation)

**OCR/Layout**:
- `POST /ocr` - Extract text with bounding boxes
- `POST /api/layout` - AI-powered layout parsing
- `POST /api/fallback` - Heuristic parsing backup
- `POST /api/merge` - Combine AI + fallback results

**DeepFlow**:
- `POST /api/deepflow_question` - Generate practice question

**Admin**:
- `GET /admin/view-qa` - View cached Q&A pairs
- `GET /admin/button-templates` - View submit button templates

---

## Data Flow

### FreeFlow (Automated)
```
Screenshot → OCR → Layout Parsing → AI Voting (3 models) → Click Answer → Click Submit → Repeat
```

### FocusFlow (Real-time)
```
Poll region every 1s → Detect text change → Debounce 2s → AI process → Update overlay
```

### AI Voting
```
Send OCR JSON to: OpenAI + Claude + Cohere → Majority vote wins (≥2 agree)
```

---

## Cross-Platform Notes

**Mac**:
- Tesseract: `brew install tesseract` (auto-detected at `/opt/homebrew/bin/tesseract`)
- PySide6: `pip install PySide6`
- pyautogui: `pip install pyautogui`

**Windows**:
- Tesseract bundled in `StudyFlow/external/tesseract/tesseract.exe`
- Same Python dependencies

**Media paths** use `os.path.join(MEDIA_DIR, "filename.png")` for cross-platform compatibility.

---

## Environment Variables

Required for backend (already on Render):
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `SENDGRID_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`

API keys are hardcoded in `config.py` (works for frontend).

---

## Common Issues

1. **Import errors**: Ensure using `StudyFlow.frontend.xxx` not `StudyFlow.xxx`
2. **Images not loading**: Check `MEDIA_DIR` path resolution
3. **Tesseract not found**: Install via Homebrew or set `TESSERACT_PATH`
4. **pyautogui missing**: `pip install pyautogui`
