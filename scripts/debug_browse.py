#!/usr/bin/env python3
"""
Debug script to check why browse is showing no notes
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from StudyFlow.backend.supabase_client import supabase
from StudyFlow.logging_utils import debug_log

def debug_browse():
    """Check what's blocking notes from appearing in browse"""
    try:
        # Get all public notes
        all_public_notes = supabase.table("notes").select(
            "id, original_filename, user_id, is_public"
        ).eq("is_public", True).not_.is_("user_id", "null").execute()

        public_notes = all_public_notes.data if all_public_notes.data else []
        debug_log(f"[1] Found {len(public_notes)} public notes in database")

        # Check how many users have Nexus enabled
        all_users = supabase.table("user_profiles").select("id, username, is_public").execute()
        users = all_users.data if all_users.data else []

        nexus_enabled = sum(1 for u in users if u.get('is_public', True) == True)
        nexus_disabled = sum(1 for u in users if u.get('is_public', True) == False)

        debug_log(f"[2] User Nexus settings: {nexus_enabled} enabled, {nexus_disabled} disabled")

        # Check which notes would pass the filter
        filtered_count = 0
        for note in public_notes:
            try:
                user_profile = supabase.table("user_profiles").select("username, is_public").eq("id", note['user_id']).single().execute()

                if user_profile.data:
                    user_is_public = user_profile.data.get('is_public', True)
                    if user_is_public:
                        filtered_count += 1
                    else:
                        debug_log(f"  - Note '{note['original_filename'][:30]}' BLOCKED: user has Nexus disabled")
                else:
                    debug_log(f"  - Note '{note['original_filename'][:30]}' BLOCKED: no profile found")
            except Exception as e:
                debug_log(f"  - Note '{note['original_filename'][:30]}' BLOCKED: error {e}")

        debug_log(f"\n[3] After Nexus filter: {filtered_count}/{len(public_notes)} notes would show in browse")

        # Show sample of blocked notes
        debug_log(f"\n[4] Sample of users with Nexus disabled:")
        for user in users[:10]:
            if user.get('is_public', True) == False:
                debug_log(f"  - User {user.get('username', 'unknown')}: is_public = {user.get('is_public')}")

        return True

    except Exception as e:
        debug_log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Debugging browse endpoint...")
    success = debug_browse()
    sys.exit(0 if success else 1)
