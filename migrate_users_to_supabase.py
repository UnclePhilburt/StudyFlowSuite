"""
Migration Script: Render PostgreSQL → Supabase Auth

This script migrates existing users from the old custom JWT system to Supabase Auth.

IMPORTANT: Since we can't recover plain-text passwords from bcrypt hashes,
we'll create users with temporary passwords and send them password reset emails.

Usage:
    python migrate_users_to_supabase.py

Requirements:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY in environment
    - DATABASE_URL (old Render PostgreSQL) in environment
"""

import os
import psycopg2
import secrets
from StudyFlow.backend.supabase_client import supabase, create_user_profile
from StudyFlow.backend.supabase_auth import reset_password_email
from StudyFlow.logging_utils import debug_log


def generate_temp_password():
    """Generate a secure temporary password"""
    return secrets.token_urlsafe(16)


def migrate_users():
    """
    Migrate all users from Render PostgreSQL to Supabase Auth.
    """
    print("🚀 Starting user migration to Supabase Auth...")
    print("=" * 60)

    # Connect to old database
    old_db_url = os.environ.get("DATABASE_URL")
    if not old_db_url:
        print("❌ ERROR: DATABASE_URL not found in environment")
        return

    try:
        conn = psycopg2.connect(old_db_url)
        cur = conn.cursor()

        # Get all users from old system
        cur.execute("""
            SELECT id, email, name, subscription_status, stripe_customer_id, is_beta
            FROM users
            ORDER BY id
        """)

        users = cur.fetchall()
        conn.close()

        print(f"📊 Found {len(users)} users to migrate\n")

        # Migration stats
        migrated = 0
        skipped = 0
        errors = 0

        for old_id, email, name, subscription_status, stripe_customer_id, is_beta in users:
            try:
                print(f"🔄 Migrating: {email} (old ID: {old_id})")

                # Check if user already exists in Supabase
                try:
                    # Try to sign in (will fail if user doesn't exist)
                    existing = supabase.auth.admin.list_users()
                    user_exists = any(u.email == email for u in existing)

                    if user_exists:
                        print(f"   ⏭️  User already exists in Supabase, skipping...")
                        skipped += 1
                        continue

                except Exception:
                    pass  # User doesn't exist, proceed with creation

                # Generate temporary password
                temp_password = generate_temp_password()

                # Create user in Supabase Auth using admin API
                # Note: Using admin API to bypass email confirmation
                auth_response = supabase.auth.admin.create_user({
                    "email": email,
                    "password": temp_password,
                    "email_confirm": True,  # Auto-confirm email
                    "user_metadata": {
                        "name": name,
                        "migrated_from_old_system": True
                    }
                })

                if not auth_response or not auth_response.user:
                    raise Exception("Failed to create Supabase Auth user")

                new_user_id = auth_response.user.id
                print(f"   ✅ Created Supabase Auth user (new ID: {new_user_id})")

                # Map subscription tiers
                tier_map = {
                    'free': 'free',
                    'premium': 'pro',
                    'pro': 'pro',
                    'beta': 'pro'  # Beta users get pro
                }
                subscription_tier = tier_map.get(subscription_status, 'free')

                # Create user profile in Supabase
                profile = create_user_profile(
                    user_id=new_user_id,
                    email=email,
                    full_name=name,
                    collective_brain_opt_in=False  # Default to false, users can opt-in later
                )

                if not profile:
                    raise Exception("Failed to create user profile")

                # Update with subscription info
                supabase.table("user_profiles").update({
                    "subscription_tier": subscription_tier,
                    "stripe_customer_id": stripe_customer_id
                }).eq("id", new_user_id).execute()

                print(f"   ✅ Created user profile (tier: {subscription_tier})")

                # Send password reset email so user can set their own password
                print(f"   📧 Sending password reset email...")
                reset_password_email(email)

                print(f"   ✅ Migration complete for {email}\n")
                migrated += 1

            except Exception as e:
                print(f"   ❌ ERROR migrating {email}: {e}\n")
                errors += 1
                continue

        # Print summary
        print("=" * 60)
        print("📊 Migration Summary:")
        print(f"   ✅ Migrated: {migrated}")
        print(f"   ⏭️  Skipped (already exists): {skipped}")
        print(f"   ❌ Errors: {errors}")
        print(f"   📊 Total: {len(users)}")
        print("=" * 60)

        if migrated > 0:
            print("\n📧 IMPORTANT:")
            print("   All migrated users have been sent password reset emails.")
            print("   They must reset their password before they can log in.")

    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
        import traceback
        print(traceback.format_exc())


if __name__ == "__main__":
    # Check environment variables
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("❌ ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
        print("   Make sure these are set in your environment")
        exit(1)

    if not os.environ.get("DATABASE_URL"):
        print("❌ ERROR: Missing DATABASE_URL (old Render PostgreSQL)")
        print("   Make sure this is set in your environment")
        exit(1)

    # Confirm before proceeding
    print("\n⚠️  WARNING: This will migrate all users to Supabase Auth")
    print("   Users will receive password reset emails")
    print("   This operation cannot be easily undone\n")

    response = input("Continue? (yes/no): ").strip().lower()

    if response != 'yes':
        print("❌ Migration cancelled")
        exit(0)

    migrate_users()
