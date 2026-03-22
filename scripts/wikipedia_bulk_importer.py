"""
Wikipedia Bulk Importer for StudyFlow
--------------------------------------
Systematically imports Wikipedia articles into StudyFlow database.

IMPORTANT: Full Wikipedia = 6.8M+ articles
- Estimated cost: $5,000-$10,000 in OpenAI embeddings
- Estimated time: Weeks/months
- Use educational categories first, then expand

Recommended approach:
1. Start with educational categories (History, Science, Math, etc.)
2. Process in batches with progress saving
3. Resume-able if interrupted
"""

import os
import sys
import json
import time
import requests
from typing import List, Dict, Set
from datetime import datetime
import wikipediaapi

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wikipedia_importer import import_wikipedia_article

# Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    user_agent='StudyFlowBot/1.0 (Educational; contact@studyflowsuite.com)',
    language='en'
)


class WikipediaBulkImporter:
    def __init__(self, progress_file='wikipedia_import_progress.json'):
        self.progress_file = progress_file
        self.processed_articles = self.load_progress()
        self.db_cached_articles = self.load_from_database()
        self.stats = {
            'total_attempted': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'skipped_db': 0,
            'start_time': None,
            'end_time': None
        }

    def load_progress(self) -> Set[str]:
        """Load previously processed articles from progress file"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('processed', []))
            except Exception as e:
                print(f"[!] Could not load progress: {e}")
        return set()

    def load_from_database(self) -> Set[str]:
        """Load already imported Wikipedia articles from database"""
        try:
            from StudyFlow.backend.supabase_client import supabase

            print("[*] Checking database for existing Wikipedia articles...")

            # Query notes table for Wikipedia articles
            # Wikipedia articles have file_type = "text/wikipedia" and original_filename ends with .txt
            response = supabase.table("notes").select("original_filename").eq("file_type", "text/wikipedia").execute()

            # Extract article titles from filenames (remove .txt extension)
            existing = set()
            for note in response.data:
                filename = note['original_filename']
                if filename.endswith('.txt'):
                    title = filename[:-4]  # Remove .txt
                    existing.add(title)

            print(f"[+] Found {len(existing)} Wikipedia articles already in database")
            return existing

        except Exception as e:
            print(f"[!] Could not load from database: {e}")
            return set()

    def save_progress(self):
        """Save progress to resume later"""
        data = {
            'processed': list(self.processed_articles),
            'stats': self.stats,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def get_category_members(self, category_name: str, max_depth: int = 1, limit: int = None) -> List[str]:
        """
        Get all articles in a Wikipedia category

        Args:
            category_name: Category name (e.g., "Category:World War I")
            max_depth: How deep to recurse into subcategories
            limit: Max number of articles to return

        Returns:
            List of article titles
        """
        print(f"[*] Fetching articles from category: {category_name}")

        try:
            category = wiki_wiki.page(category_name)
            if not category.exists():
                print(f"[-] Category not found: {category_name}")
                return []

            articles = []
            self._collect_category_articles(category, articles, max_depth, limit)

            print(f"[+] Found {len(articles)} articles in {category_name}")
            return articles

        except Exception as e:
            print(f"[-] Error fetching category: {e}")
            return []

    def _collect_category_articles(self, category, articles: List[str], depth: int, limit: int):
        """Recursively collect articles from category"""
        if depth < 0 or (limit and len(articles) >= limit):
            return

        for member_name, member in category.categorymembers.items():
            if limit and len(articles) >= limit:
                break

            if member.ns == wikipediaapi.Namespace.MAIN:  # Article
                if member_name not in articles:
                    articles.append(member_name)

            elif member.ns == wikipediaapi.Namespace.CATEGORY and depth > 0:  # Subcategory
                self._collect_category_articles(member, articles, depth - 1, limit)

    def get_random_articles(self, count: int = 100) -> List[str]:
        """Get random Wikipedia articles"""
        print(f"[*] Fetching {count} random articles...")

        url = "https://en.wikipedia.org/w/api.php"
        articles = []

        # Wikipedia API returns max 10 random per request
        requests_needed = (count + 9) // 10

        for i in range(requests_needed):
            params = {
                'action': 'query',
                'list': 'random',
                'rnnamespace': 0,  # Main namespace (articles)
                'rnlimit': min(10, count - len(articles)),
                'format': 'json'
            }

            try:
                response = requests.get(url, params=params)
                data = response.json()

                for page in data['query']['random']:
                    articles.append(page['title'])

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                print(f"[-] Error fetching random articles: {e}")
                break

        print(f"[+] Found {len(articles)} random articles")
        return articles

    def import_articles(
        self,
        articles: List[str],
        university: str = "Wikipedia",
        course_code: str = "General Knowledge",
        delay: float = 1.0
    ):
        """
        Import a list of articles with progress tracking

        Args:
            articles: List of article titles
            university: University name for tagging
            course_code: Course code for tagging
            delay: Delay between articles (seconds) for rate limiting
        """
        self.stats['start_time'] = datetime.now().isoformat()
        total = len(articles)

        print(f"\n{'='*70}")
        print(f"Starting import of {total} articles")
        print(f"{'='*70}\n")

        for i, title in enumerate(articles, 1):
            # Skip if already in database
            if title in self.db_cached_articles:
                self.stats['skipped_db'] += 1
                print(f"[{i}/{total}] Skipping (already in database): {title}")
                continue

            # Skip if already processed in this session
            if title in self.processed_articles:
                self.stats['skipped'] += 1
                print(f"[{i}/{total}] Skipping (already processed): {title}")
                continue

            self.stats['total_attempted'] += 1

            print(f"\n[{i}/{total}] Processing: {title}")
            print(f"  Progress: {(i/total)*100:.1f}%")
            print(f"  Success rate: {(self.stats['successful']/(self.stats['total_attempted'] or 1))*100:.1f}%")

            try:
                result = import_wikipedia_article(
                    title=title,
                    university=university,
                    course_code=course_code
                )

                if result['success']:
                    self.stats['successful'] += 1
                    self.processed_articles.add(title)
                else:
                    self.stats['failed'] += 1

            except Exception as e:
                print(f"[-] Error importing {title}: {e}")
                self.stats['failed'] += 1

            # Save progress every 10 articles
            if i % 10 == 0:
                self.save_progress()
                print(f"[*] Progress saved ({len(self.processed_articles)} articles processed)")

            # Rate limiting
            time.sleep(delay)

        self.stats['end_time'] = datetime.now().isoformat()
        self.save_progress()
        self.print_summary()

    def print_summary(self):
        """Print import summary"""
        print(f"\n{'='*70}")
        print("IMPORT SUMMARY")
        print(f"{'='*70}")
        print(f"Total attempted:        {self.stats['total_attempted']}")
        print(f"Successful:             {self.stats['successful']}")
        print(f"Failed:                 {self.stats['failed']}")
        print(f"Skipped (in database):  {self.stats['skipped_db']}")
        print(f"Skipped (progress file): {self.stats['skipped']}")
        if self.stats['total_attempted'] > 0:
            print(f"Success rate:           {(self.stats['successful']/(self.stats['total_attempted']))*100:.1f}%")
        print(f"{'='*70}\n")


# Pre-defined educational categories
EDUCATIONAL_CATEGORIES = {
    'History': [
        'Category:World War I',
        'Category:World War II',
        'Category:American Civil War',
        'Category:Ancient Rome',
        'Category:Ancient Egypt',
        'Category:Medieval history',
        'Category:Renaissance',
        'Category:French Revolution',
        'Category:Cold War',
    ],
    'Science': [
        'Category:Biology',
        'Category:Chemistry',
        'Category:Physics',
        'Category:Astronomy',
        'Category:Genetics',
        'Category:Evolution',
        'Category:Ecology',
    ],
    'Mathematics': [
        'Category:Algebra',
        'Category:Calculus',
        'Category:Geometry',
        'Category:Statistics',
        'Category:Number theory',
    ],
    'Computer Science': [
        'Category:Programming languages',
        'Category:Algorithms',
        'Category:Data structures',
        'Category:Artificial intelligence',
        'Category:Computer science',
    ],
    'Literature': [
        'Category:American literature',
        'Category:British literature',
        'Category:Poetry',
        'Category:Shakespeare',
    ],
}


def main():
    """Interactive CLI"""
    print("="*70)
    print("Wikipedia Bulk Importer for StudyFlow")
    print("="*70)
    print()
    print("WARNING: Full Wikipedia = 6.8M articles")
    print("Estimated cost: $5,000-$10,000 in API fees")
    print("Estimated time: Weeks to months")
    print()
    print("Recommended: Start with educational categories")
    print()

    importer = WikipediaBulkImporter()

    while True:
        print("\nOptions:")
        print("1. Import from educational category")
        print("2. Import random articles (testing)")
        print("3. Import specific category")
        print("4. View progress")
        print("5. Exit")

        choice = input("\nSelect option (1-5): ").strip()

        if choice == "1":
            # Educational categories
            print("\nEducational Categories:")
            categories_list = []
            for subject, cats in EDUCATIONAL_CATEGORIES.items():
                print(f"\n{subject}:")
                for i, cat in enumerate(cats, 1):
                    categories_list.append(cat)
                    print(f"  {len(categories_list)}. {cat}")

            selection = input(f"\nSelect category (1-{len(categories_list)}) or 'all': ").strip()

            if selection.lower() == 'all':
                confirm = input(f"\nImport ALL educational categories? This could take hours. (y/n): ").strip()
                if confirm.lower() != 'y':
                    continue

                for category in categories_list:
                    articles = importer.get_category_members(category, max_depth=1, limit=100)
                    if articles:
                        importer.import_articles(articles, course_code=category.replace('Category:', ''))

            else:
                try:
                    idx = int(selection) - 1
                    if 0 <= idx < len(categories_list):
                        category = categories_list[idx]
                        limit = input("Max articles per category (default 100): ").strip()
                        limit = int(limit) if limit else 100

                        articles = importer.get_category_members(category, max_depth=1, limit=limit)
                        if articles:
                            importer.import_articles(articles, course_code=category.replace('Category:', ''))
                    else:
                        print("[-] Invalid selection")
                except ValueError:
                    print("[-] Invalid number")

        elif choice == "2":
            # Random articles
            count = input("How many random articles? (default 10): ").strip()
            count = int(count) if count else 10

            articles = importer.get_random_articles(count)
            if articles:
                importer.import_articles(articles)

        elif choice == "3":
            # Custom category
            category = input("\nEnter category name (e.g., 'Category:Biology'): ").strip()
            limit = input("Max articles (default 100): ").strip()
            limit = int(limit) if limit else 100

            articles = importer.get_category_members(category, max_depth=1, limit=limit)
            if articles:
                course = input("Course code (default: category name): ").strip()
                course = course if course else category.replace('Category:', '')
                importer.import_articles(articles, course_code=course)

        elif choice == "4":
            # View progress
            print(f"\n{'='*70}")
            print("CURRENT PROGRESS")
            print(f"{'='*70}")
            print(f"Articles processed: {len(importer.processed_articles)}")
            importer.print_summary()

        elif choice == "5":
            print("\nGoodbye!")
            break

        else:
            print("[-] Invalid option")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved. Goodbye!")
    except Exception as e:
        print(f"\n[-] Unexpected error: {e}")
