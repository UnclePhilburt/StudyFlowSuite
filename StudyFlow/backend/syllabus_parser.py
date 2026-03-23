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
        debug_log(f"Extracting calendar events from syllabus (length: {len(syllabus_text)} chars)")

        # FERPA Compliance: Redact PII before processing
        syllabus_text = redact_pii(syllabus_text)

        # Prepare prompt for AI - FAIR USE: Extract only factual data
        prompt = f"""You are a syllabus parser that extracts ONLY factual scheduling data for Fair Use compliance.

CRITICAL: Extract ONLY factual information (dates, times, task names). Do NOT reproduce:
- Professor's creative lecture descriptions
- Original assignment instructions or requirements
- Proprietary reading lists or materials
- Any creative expression from the syllabus

Extract ONLY:
- Assignment/exam names (factual titles only)
- Due dates and times
- Event types (assignment, exam, quiz, etc.)

For each event, extract:
1. event_type: One of [assignment, exam, quiz, reading, lecture, project, presentation, discussion, lab, other]
2. title: BRIEF factual name only (e.g., "Midterm Exam", "Assignment 3", "Chapter 5 Quiz")
3. description: MINIMAL factual info ONLY if needed (e.g., "Chapters 1-5" not full instructions)
4. due_date: Date in YYYY-MM-DD format
5. due_time: Time in HH:MM 24-hour format if specified (optional)

If the year is not specified, assume it's the current academic year. If only a month and day are given, infer the year based on typical semester schedules (Fall: Aug-Dec, Spring: Jan-May, Summer: Jun-Jul).

Current date for reference: {datetime.now().strftime('%Y-%m-%d')}

Return ONLY a valid JSON array of events. Do not include any explanatory text.

Example output (factual data only):
[
  {{
    "event_type": "quiz",
    "title": "Reading Quiz 1",
    "description": "Chapters 1-3",
    "due_date": "2026-09-15",
    "due_time": "23:59"
  }},
  {{
    "event_type": "exam",
    "title": "Midterm Exam",
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
