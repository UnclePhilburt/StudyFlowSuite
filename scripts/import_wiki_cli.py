"""
Simple CLI tool for importing Wikipedia articles into StudyFlow
Usage: python import_wiki_cli.py
"""

from wikipedia_importer import (
    import_wikipedia_article,
    import_multiple_articles,
    search_wikipedia
)


def main():
    print("=" * 70)
    print("         StudyFlow Wikipedia Importer - Interactive Mode")
    print("=" * 70)
    print()
    print("Import Wikipedia articles into your StudyFlow Nexus!")
    print()

    while True:
        print("\nOptions:")
        print("1. Import a specific article")
        print("2. Search and import")
        print("3. Import multiple articles (comma-separated)")
        print("4. Import a list from file")
        print("5. Exit")

        choice = input("\nSelect option (1-5): ").strip()

        if choice == "1":
            # Single article
            title = input("\nEnter Wikipedia article title: ").strip()
            if not title:
                print("❌ Title cannot be empty")
                continue

            course = input("Course code (default: General Knowledge): ").strip() or "General Knowledge"

            print(f"\nImporting '{title}'...")
            result = import_wikipedia_article(
                title=title,
                university="Wikipedia",
                course_code=course
            )

            if result['success']:
                print(f"\n✅ Success! Imported {result['successful_chunks']} chunks")
                print(f"   URL: {result['url']}")
            else:
                print(f"\n❌ Failed: {result['error']}")

        elif choice == "2":
            # Search and import
            query = input("\nEnter search query: ").strip()
            if not query:
                print("❌ Query cannot be empty")
                continue

            print(f"\nSearching Wikipedia for '{query}'...")
            results = search_wikipedia(query, limit=10)

            if not results:
                print("❌ No results found")
                continue

            print("\nSearch Results:")
            for i, title in enumerate(results, 1):
                print(f"  {i}. {title}")

            selection = input("\nSelect article number (or 0 to cancel): ").strip()

            try:
                idx = int(selection) - 1
                if idx < 0 or idx >= len(results):
                    print("❌ Invalid selection")
                    continue

                selected_title = results[idx]
                course = input("Course code (default: General Knowledge): ").strip() or "General Knowledge"

                print(f"\nImporting '{selected_title}'...")
                result = import_wikipedia_article(
                    title=selected_title,
                    university="Wikipedia",
                    course_code=course
                )

                if result['success']:
                    print(f"\n✅ Success! Imported {result['successful_chunks']} chunks")
                else:
                    print(f"\n❌ Failed: {result['error']}")

            except ValueError:
                print("❌ Please enter a valid number")

        elif choice == "3":
            # Multiple articles
            titles_input = input("\nEnter article titles (comma-separated): ").strip()
            if not titles_input:
                print("❌ Titles cannot be empty")
                continue

            titles = [t.strip() for t in titles_input.split(',') if t.strip()]
            course = input("Course code (default: General Knowledge): ").strip() or "General Knowledge"

            print(f"\nImporting {len(titles)} articles...")
            results = import_multiple_articles(
                titles,
                university="Wikipedia",
                course_code=course
            )

            print("\n" + "=" * 70)
            print("Import Summary:")
            success = sum(1 for r in results if r['success'])
            print(f"  ✅ Successful: {success}/{len(results)}")
            print(f"  ❌ Failed: {len(results) - success}/{len(results)}")

            for result in results:
                if result['success']:
                    print(f"  ✅ {result['title']}: {result['successful_chunks']} chunks")
                else:
                    print(f"  ❌ {result.get('title', 'Unknown')}: {result.get('error')}")

        elif choice == "4":
            # Import from file
            filepath = input("\nEnter path to text file (one title per line): ").strip()

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    titles = [line.strip() for line in f if line.strip()]

                if not titles:
                    print("❌ File is empty or invalid")
                    continue

                print(f"\nFound {len(titles)} articles in file")
                course = input("Course code (default: General Knowledge): ").strip() or "General Knowledge"

                confirm = input(f"\nImport {len(titles)} articles? (y/n): ").strip().lower()
                if confirm != 'y':
                    print("Cancelled")
                    continue

                print(f"\nImporting {len(titles)} articles...")
                results = import_multiple_articles(
                    titles,
                    university="Wikipedia",
                    course_code=course
                )

                print("\n" + "=" * 70)
                print("Import Summary:")
                success = sum(1 for r in results if r['success'])
                print(f"  ✅ Successful: {success}/{len(results)}")
                print(f"  ❌ Failed: {len(results) - success}/{len(results)}")

            except FileNotFoundError:
                print(f"❌ File not found: {filepath}")
            except Exception as e:
                print(f"❌ Error reading file: {e}")

        elif choice == "5":
            print("\nGoodbye! 👋")
            break

        else:
            print("❌ Invalid option. Please select 1-5.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye! 👋")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
