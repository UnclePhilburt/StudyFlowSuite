"""
Force re-embedding of ALL note chunks with Gemini embeddings.

This script:
1. Sets all existing embeddings to NULL (clears old OpenAI embeddings)
2. Triggers the batch re-embedding task to generate new Gemini embeddings

This fixes the embedding model mismatch issue where notes were embedded
with OpenAI but searches use Gemini.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StudyFlow.backend.supabase_client import supabase
from StudyFlow.backend.tasks import reembed_all_chunks

def nullify_all_embeddings():
    """Set all note_chunk embeddings to NULL."""
    print("=" * 60)
    print("STEP 1: Nullifying all existing embeddings...")
    print("=" * 60)

    try:
        # Count total chunks
        count_resp = supabase.table("note_chunks").select("id", count="exact").execute()
        total = count_resp.count
        print(f"Total chunks in database: {total}")

        # Set all embeddings to NULL
        print("\nSetting all embeddings to NULL...")
        update_resp = supabase.table("note_chunks").update(
            {"embedding": None}
        ).neq("id", "00000000-0000-0000-0000-000000000000").execute()  # Update all (dummy condition)

        print(f"Successfully nullified all embeddings")

        # Verify
        null_count = supabase.table("note_chunks").select("id", count="exact").is_("embedding", "null").execute()
        print(f"Chunks with NULL embeddings: {null_count.count}")

        return True

    except Exception as e:
        print(f"ERROR nullifying embeddings: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_reembed():
    """Run the batch re-embedding task."""
    print("\n" + "=" * 60)
    print("STEP 2: Re-embedding all chunks with Gemini...")
    print("=" * 60)

    try:
        reembed_all_chunks()
        print("\nRe-embedding complete!")
        return True
    except Exception as e:
        print(f"ERROR during re-embedding: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("FORCE RE-EMBED ALL NOTE CHUNKS")
    print("=" * 60)
    print("\nThis will:")
    print("1. Clear all existing embeddings (OpenAI)")
    print("2. Generate new embeddings with Gemini")
    print("\nWARNING: This will make search unavailable until re-embedding completes!")
    print("=" * 60)

    response = input("\nContinue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    # Step 1: Nullify
    if not nullify_all_embeddings():
        print("\nFailed to nullify embeddings. Aborting.")
        sys.exit(1)

    # Step 2: Re-embed
    if not run_reembed():
        print("\nFailed to re-embed chunks.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SUCCESS! All chunks re-embedded with Gemini")
    print("=" * 60)
