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


def extract_calendar_events(syllabus_text: str, course_name: str = None, course_code: str = None) -> List[Dict]:
    """
    Use AI to extract calendar events (assignments, exams, etc.) from syllabus text

    Args:
        syllabus_text: Full text extracted from syllabus PDF/DOCX
        course_name: Optional course name to include in events
        course_code: Optional course code to include in events

    Returns:
        List of calendar event dictionaries with keys:
        - event_type: assignment, exam, quiz, reading, lecture, etc.
        - title: Event title
        - description: Event description (optional)
        - due_date: Date in YYYY-MM-DD format
        - due_time: Time in HH:MM format (optional)
    """
    try:
        debug_log(f"📅 Extracting calendar events from syllabus (length: {len(syllabus_text)} chars)")

        # Prepare prompt for AI
        prompt = f"""You are a syllabus parser. Extract all calendar events from this course syllabus.

Identify:
- Assignments (homework, papers, projects)
- Exams (midterms, finals, quizzes)
- Readings (required readings with due dates)
- Lectures (important lecture topics with dates)
- Other events (presentations, discussions, labs)

For each event, extract:
1. event_type: One of [assignment, exam, quiz, reading, lecture, project, presentation, discussion, lab, other]
2. title: Brief title of the event
3. description: Any additional details (optional)
4. due_date: Date in YYYY-MM-DD format
5. due_time: Time in HH:MM 24-hour format if specified (optional)

If the year is not specified, assume it's the current academic year. If only a month and day are given, infer the year based on typical semester schedules (Fall: Aug-Dec, Spring: Jan-May, Summer: Jun-Jul).

Current date for reference: {datetime.now().strftime('%Y-%m-%d')}

Return ONLY a valid JSON array of events. Do not include any explanatory text.

Example output:
[
  {{
    "event_type": "assignment",
    "title": "Chapter 1-3 Reading Quiz",
    "description": "Multiple choice quiz on chapters 1-3",
    "due_date": "2026-09-15",
    "due_time": "23:59"
  }},
  {{
    "event_type": "exam",
    "title": "Midterm Exam",
    "description": "Covers chapters 1-7",
    "due_date": "2026-10-20",
    "due_time": "14:00"
  }}
]

SYLLABUS TEXT:
{syllabus_text[:15000]}
"""

        # Call OpenAI API
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a precise syllabus parser that extracts calendar events in JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=3000
        )

        ai_response = response.choices[0].message.content.strip()
        debug_log(f"🤖 AI response (first 200 chars): {ai_response[:200]}")

        # Parse JSON response
        # Remove markdown code blocks if present
        if ai_response.startswith("```"):
            ai_response = re.sub(r'^```json?\s*', '', ai_response)
            ai_response = re.sub(r'\s*```$', '', ai_response)

        events = json.loads(ai_response)

        # Add course info to each event
        for event in events:
            if course_name:
                event['course_name'] = course_name
            if course_code:
                event['course_code'] = course_code

        debug_log(f"✅ Extracted {len(events)} calendar events")
        return events

    except json.JSONDecodeError as e:
        debug_log(f"❌ Failed to parse AI response as JSON: {e}")
        debug_log(f"AI response was: {ai_response}")
        return []
    except Exception as e:
        debug_log(f"❌ Error extracting calendar events: {e}")
        import traceback
        debug_log(traceback.format_exc())
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
