"""
Wikipedia Content Importer for StudyFlow
-----------------------------------------
Extracts Wikipedia articles and adds them to the StudyFlow database
as searchable note chunks for the Collective Brain.

Legal: Wikipedia content is CC BY-SA licensed - properly attributed.
"""

import os
import sys
import wikipediaapi
import openai
import time
from typing import List, Dict
import re

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StudyFlow.config import OPENAI_API_KEY
from StudyFlow.backend.supabase_client import supabase

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    user_agent='StudyFlowBot/1.0 (Educational purpose; contact@studyflowsuite.com)',
    language='en'
)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks for embedding.

    Args:
        text: The text to chunk
        chunk_size: Target size of each chunk (characters)
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    # Clean up text
    text = re.sub(r'\s+', ' ', text).strip()

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            # Look for period followed by space
            last_period = text.rfind('. ', start, end)
            if last_period > start + chunk_size // 2:  # Don't break too early
                end = last_period + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def get_embedding(text: str) -> List[float]:
    """
    Get OpenAI embedding for text.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (1536 dimensions)
    """
    try:
        response = openai.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None


def import_wikipedia_article(
    title: str,
    university: str = "Wikipedia",
    course_code: str = "General Knowledge",
    user_id: str = None
) -> Dict:
    """
    Import a Wikipedia article into StudyFlow database.

    Args:
        title: Wikipedia article title
        university: University name (default: "Wikipedia")
        course_code: Course code (default: "General Knowledge")
        user_id: User ID to associate with (optional, defaults to system user)

    Returns:
        Dictionary with import statistics
    """
    print(f"\n{'='*60}")
    print(f"Importing: {title}")
    print(f"{'='*60}")

    # Fetch article
    page = wiki_wiki.page(title)

    if not page.exists():
        print(f"[-] Article '{title}' not found")
        return {"success": False, "error": "Article not found"}

    # Get article text
    article_text = page.text
    if not article_text:
        print(f"[-] No text content in '{title}'")
        return {"success": False, "error": "No content"}

    print(f"[*] Article length: {len(article_text)} characters")

    # Create note entry
    try:
        note_data = {
            "user_id": user_id,  # None = system-wide
            "original_filename": f"{title}.txt",
            "file_type": "text/wikipedia",
            "file_size": len(article_text),
            "page_count": 1,
            "processed": True,
            "is_public": True,  # Wikipedia content is public
            "university": university,
            "course_code": course_code,
        }

        note_result = supabase.table("notes").insert(note_data).execute()
        note_id = note_result.data[0]['id']
        print(f"[+] Created note entry: {note_id}")

    except Exception as e:
        print(f"[-] Error creating note: {e}")
        return {"success": False, "error": str(e)}

    # Chunk the article
    chunks = chunk_text(article_text, chunk_size=1000, overlap=200)
    print(f"[*] Split into {len(chunks)} chunks")

    # Process each chunk
    success_count = 0
    for i, chunk_text_content in enumerate(chunks):
        try:
            # Get embedding
            embedding = get_embedding(chunk_text_content)
            if not embedding:
                print(f"[!]  Skipping chunk {i+1}: No embedding")
                continue

            # Create summary for collective brain (first 200 chars)
            summary = chunk_text_content[:200] + "..." if len(chunk_text_content) > 200 else chunk_text_content

            # Insert chunk
            chunk_data = {
                "note_id": note_id,
                "user_id": user_id,
                "chunk_text": chunk_text_content,
                "content_summary": f"Wikipedia: {title} - {summary}",
                "chunk_index": i,
                "university": university,
                "course_code": course_code,
                "embedding": embedding,
                "is_public": True
            }

            supabase.table("note_chunks").insert(chunk_data).execute()
            success_count += 1

            print(f"[+] Chunk {i+1}/{len(chunks)} imported", end='\r')

            # Rate limiting
            time.sleep(0.5)  # OpenAI rate limits

        except Exception as e:
            print(f"\n[!]  Error processing chunk {i+1}: {e}")
            continue

    print(f"\n[+] Successfully imported {success_count}/{len(chunks)} chunks")

    return {
        "success": True,
        "note_id": note_id,
        "title": title,
        "total_chunks": len(chunks),
        "successful_chunks": success_count,
        "url": page.fullurl
    }


def import_multiple_articles(titles: List[str], **kwargs) -> List[Dict]:
    """
    Import multiple Wikipedia articles.

    Args:
        titles: List of article titles
        **kwargs: Additional arguments passed to import_wikipedia_article

    Returns:
        List of import results
    """
    results = []

    for title in titles:
        result = import_wikipedia_article(title, **kwargs)
        results.append(result)
        time.sleep(2)  # Be nice to Wikipedia servers

    return results


def search_wikipedia(query: str, limit: int = 10) -> List[str]:
    """
    Search Wikipedia for articles matching query.

    Args:
        query: Search query
        limit: Maximum number of results

    Returns:
        List of article titles
    """
    try:
        import requests

        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": query,
            "limit": limit,
            "namespace": 0,
            "format": "json"
        }

        response = requests.get(url, params=params)
        data = response.json()

        # OpenSearch returns [query, [titles], [descriptions], [urls]]
        titles = data[1] if len(data) > 1 else []
        return titles

    except Exception as e:
        print(f"Error searching Wikipedia: {e}")
        return []


# Example usage
if __name__ == "__main__":
    print("StudyFlow Wikipedia Importer")
    print("=" * 60)

    # Example 1: Import a single article
    print("\n--- Example 1: Single Article ---")
    result = import_wikipedia_article(
        title="World War I",
        university="Wikipedia",
        course_code="History"
    )
    print(f"\nResult: {result}")

    # Example 2: Search and import
    print("\n\n--- Example 2: Search and Import ---")
    query = "photosynthesis"
    print(f"Searching for: {query}")
    search_results = search_wikipedia(query, limit=5)
    print(f"Found {len(search_results)} articles:")
    for i, title in enumerate(search_results, 1):
        print(f"  {i}. {title}")

    # Import first result
    if search_results:
        print(f"\nImporting first result: {search_results[0]}")
        result = import_wikipedia_article(
            title=search_results[0],
            university="Wikipedia",
            course_code="Biology"
        )
        print(f"\nResult: {result}")

    # Example 3: Import multiple related articles
    print("\n\n--- Example 3: Multiple Articles ---")
    biology_topics = [
        "Cell (biology)",
        "DNA",
        "Mitosis",
        "Photosynthesis"
    ]

    print(f"Importing {len(biology_topics)} biology articles...")
    results = import_multiple_articles(
        biology_topics,
        university="Wikipedia",
        course_code="Biology 101"
    )

    print("\n\nSummary:")
    for result in results:
        if result['success']:
            print(f"[+] {result['title']}: {result['successful_chunks']} chunks")
        else:
            print(f"[-] {result.get('title', 'Unknown')}: {result.get('error', 'Unknown error')}")
