#!/usr/bin/env python3
"""
One-time script to update all existing notes to is_public = true
Run this after deploying the supabase_client.py fix
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from StudyFlow.backend.supabase_client import supabase
from StudyFlow.logging_utils import debug_log

def fix_note_visibility():
    """Update all notes to be public by default"""
    try:
        # Update all notes where is_public is false or null
        response = supabase.table("notes").update({
            "is_public": True
        }).is_("is_public", "null").execute()

        null_count = len(response.data) if response.data else 0
        debug_log(f"[+] Updated {null_count} notes with NULL is_public to True")

        # Update all notes where is_public is explicitly false
        response2 = supabase.table("notes").update({
            "is_public": True
        }).eq("is_public", False).execute()

        false_count = len(response2.data) if response2.data else 0
        debug_log(f"[+] Updated {false_count} notes with is_public=False to True")

        total = null_count + false_count
        debug_log(f"\n[SUCCESS] Total notes updated: {total}")

        # Verify the update
        all_notes = supabase.table("notes").select("id, is_public").execute()
        public_count = sum(1 for note in all_notes.data if note.get('is_public') == True)
        total_notes = len(all_notes.data) if all_notes.data else 0

        debug_log(f"[STATS] Database stats: {public_count}/{total_notes} notes are now public")

        return True

    except Exception as e:
        debug_log(f"❌ Error updating note visibility: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Fixing note visibility defaults...")
    success = fix_note_visibility()
    sys.exit(0 if success else 1)
