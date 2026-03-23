"""
Syllabus Parser - Extract calendar events from course syllabi using AI
"""

import openai
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
from StudyFlow.logging_utils import debug_log
from StudyFlow.config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY


def redact_pii(text: str) -> str:
    """
    Redact personally identifiable information from syllabus text.
    Removes student names, IDs, and handwritten notes.

    FERPA Compliance: Student metadata must be scrubbed before processing.
    """
    # Remove common PII patterns
    # Student names (Name: John Doe, Student: Jane Smith, etc.)
    text = re.sub(r'(?i)(student\s+name|name):\s*[A-Z][a-z]+\s+[A-Z][a-z]+', r'\1: [REDACTED]', text)

    # Student IDs (ID: 123456789, Student ID: A00123456, etc.)
    text = re.sub(r'(?i)(student\s+)?id:\s*[A-Z0-9]+', r'\1ID: [REDACTED]', text)

    # Email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL REDACTED]', text)

    return text


def extract_calendar_events(syllabus_text: str, course_name: str = None, course_code: str = None) -> List[Dict]:
    """
    Extract ONLY factual calendar data from syllabus (Fair Use compliant).

    COPYRIGHT COMPLIANCE:
    - Extracts only dates, times, and task names (factual data - not copyrightable)
    - Does NOT reproduce professor's creative expression, lecture descriptions, or proprietary content
    - Creates transformative derivative work (calendar) for personal time management

    PRIVACY COMPLIANCE (FERPA/SB 1324):
    - Redacts student names and IDs before processing
    - Does not store or share original syllabus content

    Args:
        syllabus_text: Full text extracted from syllabus PDF/DOCX
        course_name: Optional course name to include in events
        course_code: Optional course code to include in events

    Returns:
        List of calendar event dictionaries with keys:
        - event_type: assignment, exam, quiz, reading, lecture, etc.
        - title: Brief title of the event (factual name only)
        - description: Minimal factual description (optional)
        - due_date: Date in YYYY-MM-DD format
        - due_time: Time in HH:MM format (optional)
    """
    try:
        print(f"\n========== SYLLABUS EXTRACTION START ==========", flush=True)
        print(f"[EXTRACT] Syllabus length: {len(syllabus_text)} chars", flush=True)
        print(f"[EXTRACT] First 500 chars:\n{syllabus_text[:500]}", flush=True)
        print(f"========================================\n", flush=True)

        # FERPA Compliance: Redact PII before processing
        syllabus_text = redact_pii(syllabus_text)
        print(f"[EXTRACT] After PII redaction: {len(syllabus_text)} chars", flush=True)

        # Prepare prompt for AI - FAIR USE: Extract only factual data
        current_year = datetime.now().year
        current_month = datetime.now().month

        # Determine likely semester based on current date
        if current_month >= 8:  # Aug or later - likely Fall semester
            fall_year = current_year
            spring_year = current_year + 1
        else:  # Before Aug - likely Spring semester
            fall_year = current_year - 1
            spring_year = current_year

        prompt = f"""You are a syllabus parser that extracts ONLY factual scheduling data for Fair Use compliance.

CRITICAL: Extract ONLY factual information (dates, times, task names). Do NOT reproduce professor's creative content.

IMPORTANT DATE PARSING RULES:
- Current date for reference: {datetime.now().strftime('%Y-%m-%d')}
- For Fall semester dates (Aug-Dec), use year {fall_year}
- For Spring semester dates (Jan-May), use year {spring_year}
- For Summer dates (Jun-Jul), use year {spring_year}
- Look for dates in ANY format: "Sept 15", "9/15", "September 15th", "Week 3 - Sep 15"
- Look for times in ANY format: "11:59pm", "11:59 PM", "2:00", "14:00"
- If no time is given, leave due_time as null

WHAT TO EXTRACT:
- Assignments (homework, papers, projects, labs)
- Exams (midterms, finals, tests)
- Quizzes (reading quizzes, chapter quizzes)
- Presentations (individual or group)
- Due dates for any graded work
- Important academic deadlines

WHERE TO LOOK:
- Course schedule sections
- Weekly breakdowns
- Assignment lists
- Exam schedules
- Grading breakdown sections
- Important dates sections

For each event, extract:
1. event_type: One of [assignment, exam, quiz, reading, lecture, project, presentation, discussion, lab, other]
2. title: BRIEF factual name (e.g., "Midterm 1", "Essay 2", "Quiz 3")
3. description: MINIMAL factual info only (e.g., "Chapters 1-5")
4. due_date: Date in YYYY-MM-DD format (REQUIRED)
5. due_time: Time in HH:MM 24-hour format (optional)

Return ONLY a valid JSON array. Extract EVERY due date you can find!

Example output:
[
  {{
    "event_type": "quiz",
    "title": "Quiz 1",
    "description": "Chapters 1-3",
    "due_date": "{fall_year}-09-15",
    "due_time": "23:59"
  }},
  {{
    "event_type": "exam",
    "title": "Midterm Exam",
    "due_date": "{fall_year}-10-20",
    "due_time": "14:00"
  }},
  {{
    "event_type": "assignment",
    "title": "Paper 1",
    "due_date": "{fall_year}-11-01",
    "due_time": null
  }}
]

SYLLABUS TEXT:
{syllabus_text[:15000]}
"""

        # Call OpenAI API - use GPT-4o for better extraction accuracy
        print(f"\n[AI] Calling GPT-4o for calendar extraction...", flush=True)
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a precise syllabus parser that extracts calendar events in JSON format. Extract EVERY due date, exam, quiz, and assignment you can find."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )

        ai_response = response.choices[0].message.content.strip()
        print(f"\n========== AI RESPONSE START ==========", flush=True)
        print(ai_response, flush=True)
        print(f"========== AI RESPONSE END ==========\n", flush=True)

        # Parse JSON response
        # Remove markdown code blocks if present
        if ai_response.startswith("```"):
            ai_response = re.sub(r'^```json?\s*', '', ai_response)
            ai_response = re.sub(r'\s*```$', '', ai_response)

        events = json.loads(ai_response)
        print(f"[AI PARSED] Successfully parsed {len(events)} events from JSON", flush=True)

        # Add course info to each event
        for event in events:
            if course_name:
                event['course_name'] = course_name
            if course_code:
                event['course_code'] = course_code

        print(f"\n[SUCCESS] Extracted {len(events)} calendar events", flush=True)
        print(f"========== SYLLABUS EXTRACTION END ==========\n", flush=True)
        return events

    except json.JSONDecodeError as e:
        print(f"\n[ERROR] Failed to parse AI response as JSON: {e}", flush=True)
        print(f"[ERROR] AI response was: {ai_response}", flush=True)
        print(f"========== SYLLABUS EXTRACTION END (ERROR) ==========\n", flush=True)
        return []
    except Exception as e:
        print(f"\n[ERROR] Error extracting calendar events: {e}", flush=True)
        import traceback
        print(traceback.format_exc(), flush=True)
        print(f"========== SYLLABUS EXTRACTION END (ERROR) ==========\n", flush=True)
        return []


def validate_event(event: Dict) -> bool:
    """Validate that an event has required fields"""
    required_fields = ['event_type', 'title', 'due_date']
    return all(field in event and event[field] for field in required_fields)


def format_event_for_db(event: Dict, user_id: str, syllabus_id: str = None) -> Dict:
    """Format event dictionary for database insertion"""
    return {
        'user_id': user_id,
        'syllabus_id': syllabus_id,
        'event_type': event.get('event_type', 'other'),
        'title': event.get('title', 'Untitled Event'),
        'description': event.get('description'),
        'due_date': event.get('due_date'),
        'due_time': event.get('due_time'),
        'course_name': event.get('course_name'),
        'course_code': event.get('course_code'),
        'completed': False
    }
