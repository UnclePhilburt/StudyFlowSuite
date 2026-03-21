"""
Test import of 10 educational Wikipedia articles (auto-run)
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.wikipedia_importer import import_multiple_articles

# 10 diverse test articles covering different subjects
test_articles = [
    # History
    "World War I",
    "French Revolution",

    # Science - Biology
    "Photosynthesis",
    "DNA",

    # Science - Physics
    "Gravity",
    "Electricity",

    # Math
    "Pythagorean theorem",
    "Calculus",

    # Computer Science
    "Python (programming language)",

    # Literature
    "William Shakespeare"
]

print("=" * 70)
print("Wikipedia Test Import - 10 Articles (AUTO-RUN)")
print("=" * 70)
print("\nArticles to import:")
for i, title in enumerate(test_articles, 1):
    print(f"  {i}. {title}")

print("\n" + "=" * 70)
print("Starting automatic import...")
print("=" * 70)
print()

# Import the articles
results = import_multiple_articles(
    test_articles,
    university="Wikipedia",
    course_code="Test Import"
)

# Print summary
print("\n" + "=" * 70)
print("TEST IMPORT SUMMARY")
print("=" * 70)

successful = sum(1 for r in results if r.get('success'))
print(f"Successful: {successful}/{len(test_articles)}")
print(f"Failed: {len(test_articles) - successful}/{len(test_articles)}")

print("\nDetailed Results:")
for i, result in enumerate(results, 1):
    if result.get('success'):
        print(f"  [{i}] [+] {result['title']}: {result['successful_chunks']} chunks")
    else:
        print(f"  [{i}] [-] {result.get('title', 'Unknown')}: {result.get('error')}")

print("\n" + "=" * 70)

if successful > 0:
    print("\n[+] Test successful! You can now search these topics in NoteFlow.")
    print("    Try asking: 'What caused World War I?' or 'Explain photosynthesis'")
else:
    print("\n[-] Test failed. Check your Supabase and OpenAI credentials.")
