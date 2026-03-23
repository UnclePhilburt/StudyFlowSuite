#!/usr/bin/env python3
"""
Add is_public column to user_profiles table for Nexus setting
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from StudyFlow.backend.supabase_client import supabase
from StudyFlow.logging_utils import debug_log

def add_is_public_column():
    """Add is_public column to user_profiles"""
    try:
        # Note: We can't add columns via the Python client
        # We need to use SQL through the Supabase SQL editor or API

        # But we CAN check if the column exists and set defaults
        debug_log("[*] Checking user_profiles structure...")

        # Try to select is_public to see if it exists
        try:
            test = supabase.table("user_profiles").select("is_public").limit(1).execute()
            debug_log("[+] Column 'is_public' already exists!")
            return True
        except Exception as e:
            if "does not exist" in str(e):
                debug_log("[-] Column 'is_public' does NOT exist")
                debug_log("\n[ACTION REQUIRED] Please run this SQL in Supabase SQL editor:")
                debug_log("=" * 60)
                print("""
-- Add is_public column to user_profiles for Nexus setting
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT true;

-- Add comment
COMMENT ON COLUMN user_profiles.is_public IS 'Nexus setting: whether user shares notes publicly';
                """)
                debug_log("=" * 60)
                return False
            else:
                raise e

    except Exception as e:
        debug_log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Checking user_profiles.is_public column...")
    success = add_is_public_column()

    if not success:
        print("\nPlease run the SQL above in your Supabase dashboard:")
        print("1. Go to https://supabase.com/dashboard")
        print("2. Select your project")
        print("3. Go to SQL Editor")
        print("4. Paste and run the SQL above")

    sys.exit(0 if success else 1)
