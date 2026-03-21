# StudyFlow Suite - Project Documentation

## CRITICAL USER PREFERENCES

**NEVER USE EMOJIS - The user absolutely hates emojis. Use text instead.**
- ❌ DON'T: Use 📤, 📝, ⚙️, ✨, 💬, or any emoji characters
- ✅ DO: Use plain text like "Upload", "Notes", "Settings", "New Chat"
- This applies to ALL code: frontend, backend, UI, buttons, messages, logs, everything

---

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
├── browser-extension/            # Chrome extension (runs in browser)
│   ├── manifest.json             # Extension config
│   ├── popup.html/js             # Extension popup UI
│   ├── background.js             # Service worker
│   ├── content.js                # Page content script
│   └── element-picker.js         # Element selection tool
│
├── .env                          # Environment variables (local)
├── requirements.txt              # Python dependencies
└── Dockerfile                    # Production deployment
```

**Website (Marketing/Demo Site):**
- Location: `C:\Users\CodyW\OneDrive\Documents\studyflowsuitewebsite`
- Contains: Landing page, demo quizzes, documentation
- Demo page has 3 tutorial quizzes + Canvas LMS example

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

## GitHub Push Rules ⚠️

**CRITICAL: Every push to GitHub triggers automatic Render deployment!**

### When to Push:
- ✅ **Backend changes ONLY** (StudyFlow/backend/)
  - Changes to app.py, ai_clients/, tasks.py, etc.
  - ALWAYS ask user first: "This is a backend change. Should I push to GitHub to deploy on Render?"

### When NOT to Push:
- ❌ **Browser extension changes** (browser-extension/)
  - These run locally in the browser
  - User just needs to reload the extension in Chrome
  - NO GitHub push needed!

- ❌ **Frontend desktop app changes** (StudyFlow/frontend/)
  - These run locally on user's computer
  - NO deployment needed
  - NO GitHub push needed!

### Exception:
- User explicitly says "push to github" or "deploy to render"
- User says "update backend" or similar

**Remember: Unnecessary pushes waste 2-3 minutes of deployment time!**

---

## Browser Extension - Single-Page Canvas Quiz Mode

### Critical Architecture
The extension handles Canvas LMS single-page quizzes where ALL questions are visible on one page (no Next button).

**Key Files:**
- `content.js` (lines 48-290): `detectOnePageQuiz()` - Scans all question containers
- `background.js` (lines 205-520): `runQuizLoop()` - Processes questions sequentially
- `popup.js` (line 185): Sets `onePageMode: true` for single-page mode

### Question Tracking System (CRITICAL FIX - Jan 2025)
**Problem Solved:** Questions were being marked as "answered" during detection (before actually being filled), causing the extension to skip questions.

**Solution Implemented:**
1. **Detection Phase** (content.js lines 156-279):
   - Questions are detected but NOT marked as answered
   - Each question returns a `questionHash` identifier
   - Only already-filled questions are marked during detection

2. **Processing Phase** (background.js lines 411-438 for multiple choice, 273-314 for essays):
   - After successfully clicking/filling an answer
   - Send `markQuestionAnswered` message to content.js
   - Only then is the question marked in `answeredLearnosityQuestions` Set

3. **Message Handler** (content.js lines 947-959):
   - `markQuestionAnswered` action adds hash to tracking Set
   - Prevents re-processing same question on next detection

### Question Detection Selectors
**Learnosity/Canvas specific:**
- Primary: `[data-automation="sdk-take-item-question"]`
- Fallback: `.lrn-assess-item, .lrn_widget, [class*="lrn_question"]`

**Question Types Supported:**
1. Multiple Choice: Radio buttons with `data-studyflow-radio-group` and `data-studyflow-radio-index` attributes
2. Essay (TinyMCE): iframe with `data-studyflow-field-id` attribute
3. Fill-in-blank: textarea with `data-studyflow-field-id` attribute

### Cross-Frame Message Routing
**Critical Fix (background.js line 413):**
- Use `sendMessageToFrame()` NOT `chrome.tabs.sendMessage()`
- Ensures messages go to correct iframe via `currentFrameId`
- Fixes: "Radio button not found" and "Essay field not found" errors

### Submit Button Logic
**One-page mode behavior:**
- Skip submit between questions (background.js line 429)
- Only click submit after ALL questions answered (background.js line 363)
- Prevents premature quiz submission

### Flow Example (3-question quiz):
```
1. Detect Q1 (multiple choice) → Return Q1 [NOT marked]
2. Get AI answer → Click radio → Send markQuestionAnswered → Q1 marked ✓
3. Detect Q2 (essay) → Return Q2 [NOT marked, Q1 skipped]
4. Get AI answer → Fill iframe → Send markQuestionAnswered → Q2 marked ✓
5. Detect Q3 (fill-blank) → Return Q3 [NOT marked, Q1-Q2 skipped]
6. Get AI answer → Fill textarea → Send markQuestionAnswered → Q3 marked ✓
7. Detect next → All marked → Return "All questions answered! Ready for final submit"
```

---

## Common Issues

1. **Import errors**: Ensure using `StudyFlow.frontend.xxx` not `StudyFlow.xxx`
2. **Images not loading**: Check `MEDIA_DIR` path resolution
3. **Tesseract not found**: Install via Homebrew or set `TESSERACT_PATH`
4. **pyautogui missing**: `pip install pyautogui`
5. **Extension skipping questions**: Ensure `markQuestionAnswered` is called AFTER successful answer (not during detection)
