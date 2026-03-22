"""
Check Imported Wikipedia Articles
----------------------------------
Query the database to see which Wikipedia articles have already been imported.
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StudyFlow.backend.supabase_client import supabase


def get_imported_wikipedia_articles():
    """Get list of all imported Wikipedia articles"""
    try:
        # Query notes table for Wikipedia articles
        response = supabase.table("notes").select("original_filename, course_code, uploaded_at").eq("file_type", "text/wikipedia").order("uploaded_at", desc=True).execute()

        articles = []
        for note in response.data:
            filename = note['original_filename']
            if filename.endswith('.txt'):
                title = filename[:-4]  # Remove .txt
                articles.append({
                    'title': title,
                    'course_code': note.get('course_code', 'N/A'),
                    'imported_at': note.get('uploaded_at', 'N/A')
                })

        return articles

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    import sys

    # Check for command line arguments
    show_detailed = '--detailed' in sys.argv or '-d' in sys.argv
    export_file = '--export' in sys.argv or '-e' in sys.argv

    print("="*70)
    print("Imported Wikipedia Articles")
    print("="*70)
    print()

    articles = get_imported_wikipedia_articles()

    if not articles:
        print("No Wikipedia articles found in database.")
        return

    print(f"Total Wikipedia articles: {len(articles)}\n")

    # Group by course code
    by_course = {}
    for article in articles:
        course = article['course_code']
        if course not in by_course:
            by_course[course] = []
        by_course[course].append(article['title'])

    # Display summary
    print("Summary by Course:")
    print("-" * 70)
    for course, titles in sorted(by_course.items()):
        print(f"{course}: {len(titles)} articles")

    # Show detailed list if requested
    if show_detailed:
        print("\n" + "="*70)
        print("Detailed List")
        print("="*70)
        for i, article in enumerate(articles, 1):
            print(f"{i}. {article['title']} ({article['course_code']})")

    # Export if requested
    if export_file:
        filename = 'imported_wikipedia_articles.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("Imported Wikipedia Articles\n")
            f.write("="*70 + "\n\n")
            f.write(f"Total: {len(articles)}\n\n")
            f.write("By Course:\n")
            f.write("-"*70 + "\n")
            for course, titles in sorted(by_course.items()):
                f.write(f"{course}: {len(titles)} articles\n")
            f.write("\n\nDetailed List:\n")
            f.write("="*70 + "\n")
            for i, article in enumerate(articles, 1):
                f.write(f"{i}. {article['title']} ({article['course_code']})\n")

        print(f"\nExported to {filename}")

    if not show_detailed and not export_file:
        print("\nUse --detailed or -d to show full list")
        print("Use --export or -e to export to file")


if __name__ == "__main__":
    main()
