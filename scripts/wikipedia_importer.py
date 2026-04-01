"""
Wikipedia Content Importer for StudyFlow
-----------------------------------------
Imports Wikipedia articles as searchable note chunks in the Nexus.
Uses Gemini embeddings (768 dimensions).

Legal: Wikipedia content is CC BY-SA licensed - properly attributed.
"""

import os
import sys
import time
import re
import requests
from typing import List, Dict

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from StudyFlow.backend.supabase_client import supabase
from StudyFlow.backend.embedding_client import generate_embedding


# Wikipedia system user ID (no real user -- set to None for system-level)
WIKI_USER_ID = None


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks."""
    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            last_period = text.rfind('. ', start, end)
            if last_period > start + chunk_size // 2:
                end = last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap

    return chunks


def fetch_wikipedia_article(title: str) -> dict:
    """Fetch article text from Wikipedia API."""
    try:
        url = "https://en.wikipedia.org/w/api.php"
        resp = requests.get(url, params={
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": True,
            "format": "json"
        }, timeout=15)

        data = resp.json()
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            if page_id == "-1":
                return None
            return {
                "title": page.get("title", title),
                "text": page.get("extract", ""),
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            }
    except Exception as e:
        print(f"Error fetching {title}: {e}")
    return None


def import_article(title: str, course_code: str = "General Knowledge") -> dict:
    """Import a single Wikipedia article into StudyFlow."""
    print(f"\n{'='*50}")
    print(f"Importing: {title}")

    article = fetch_wikipedia_article(title)
    if not article or not article["text"]:
        print(f"  Article not found or empty")
        return {"success": False, "title": title, "error": "Not found"}

    text = article["text"]
    print(f"  {len(text)} chars")

    # Check if already imported
    existing = supabase.table("notes").select("id").eq(
        "original_filename", f"{article['title']}.txt"
    ).eq("university", "Wikipedia").execute()

    if existing.data:
        print(f"  Already imported, skipping")
        return {"success": False, "title": title, "error": "Already exists"}

    # Create note record
    try:
        note_data = {
            "user_id": WIKI_USER_ID,
            "original_filename": f"{article['title']}.txt",
            "file_type": "text/wikipedia",
            "file_size": len(text),
            "page_count": 1,
            "processed": True,
            "is_public": True,
            "university": "Wikipedia",
            "course_code": course_code,
        }
        note_result = supabase.table("notes").insert(note_data).execute()
        note_id = note_result.data[0]['id']
    except Exception as e:
        print(f"  Error creating note: {e}")
        return {"success": False, "title": title, "error": str(e)}

    # Chunk and embed
    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks")

    success = 0
    for i, chunk_text_content in enumerate(chunks):
        try:
            embedding = generate_embedding(chunk_text_content)
            if not embedding:
                continue

            summary = chunk_text_content[:200] + "..." if len(chunk_text_content) > 200 else chunk_text_content

            supabase.table("note_chunks").insert({
                "note_id": note_id,
                "user_id": WIKI_USER_ID,
                "chunk_text": chunk_text_content,
                "content_summary": f"Wikipedia: {article['title']} - {summary}",
                "chunk_index": i,
                "university": "Wikipedia",
                "course_code": course_code,
                "embedding": embedding,
                "is_public": True
            }).execute()

            success += 1
            time.sleep(0.05)  # Gemini rate limit respect

        except Exception as e:
            print(f"  Chunk {i} error: {e}")

    print(f"  Done: {success}/{len(chunks)} chunks")
    return {"success": True, "title": title, "note_id": note_id, "chunks": success}


def import_batch(titles: List[str], course_code: str = "General Knowledge") -> List[dict]:
    """Import multiple articles."""
    results = []
    for title in titles:
        result = import_article(title, course_code)
        results.append(result)
        time.sleep(1)  # Be nice to Wikipedia
    return results


# ============ ARTICLE LISTS BY SUBJECT ============

BIOLOGY = [
    "Cell (biology)", "DNA", "RNA", "Mitosis", "Meiosis",
    "Photosynthesis", "Cellular respiration", "Protein",
    "Gene expression", "Evolution", "Natural selection",
    "Genetics", "Mendelian inheritance", "Chromosome",
    "Enzyme", "Metabolism", "Ecology", "Biodiversity",
    "Taxonomy (biology)", "Microbiology",
    "Human anatomy", "Nervous system", "Immune system",
    "Circulatory system", "Digestive system",
]

CHEMISTRY = [
    "Atom", "Chemical bond", "Molecule", "Chemical reaction",
    "Periodic table", "Organic chemistry", "Inorganic chemistry",
    "Acid", "Base (chemistry)", "pH", "Oxidation",
    "Electrochemistry", "Thermodynamics", "Chemical equilibrium",
    "Stoichiometry", "Mole (unit)", "Gas laws",
    "Solutions (chemistry)", "Nuclear chemistry",
]

PHYSICS = [
    "Classical mechanics", "Newton's laws of motion",
    "Thermodynamics", "Electromagnetism", "Optics",
    "Quantum mechanics", "Special relativity", "General relativity",
    "Wave", "Sound", "Light", "Gravity", "Energy",
    "Momentum", "Force", "Electric current", "Magnetism",
    "Nuclear physics", "Particle physics",
]

US_HISTORY = [
    "American Revolution", "United States Constitution",
    "American Civil War", "Reconstruction era",
    "World War I", "World War II", "Great Depression",
    "Cold War", "Civil rights movement",
    "Vietnam War", "Manifest destiny", "Louisiana Purchase",
    "Industrial Revolution in the United States",
    "New Deal", "War on Terror", "Watergate scandal",
    "American frontier", "Slavery in the United States",
    "Women's suffrage in the United States",
]

WORLD_HISTORY = [
    "Ancient Rome", "Ancient Greece", "Ancient Egypt",
    "Renaissance", "Industrial Revolution", "French Revolution",
    "Russian Revolution", "Ottoman Empire", "British Empire",
    "Colonialism", "Imperialism", "Feudalism",
    "Reformation", "Enlightenment", "Silk Road",
    "Mongol Empire", "Byzantine Empire", "Mesopotamia",
    "Chinese dynasties", "Meiji Restoration",
]

MATH = [
    "Algebra", "Calculus", "Trigonometry", "Geometry",
    "Statistics", "Probability", "Linear algebra",
    "Differential equation", "Number theory",
    "Mathematical proof", "Function (mathematics)",
    "Derivative", "Integral", "Matrix (mathematics)",
    "Logarithm", "Polynomial", "Pythagorean theorem",
    "Set theory", "Graph theory",
]

PSYCHOLOGY = [
    "Psychology", "Cognitive psychology", "Behavioral psychology",
    "Developmental psychology", "Social psychology",
    "Abnormal psychology", "Classical conditioning",
    "Operant conditioning", "Memory", "Motivation",
    "Emotion", "Personality psychology", "Intelligence",
    "Sigmund Freud", "Carl Jung", "B. F. Skinner",
    "Abraham Maslow", "Jean Piaget", "Cognitive bias",
    "Mental disorder",
]

COMPUTER_SCIENCE = [
    "Algorithm", "Data structure", "Computer programming",
    "Object-oriented programming", "Database",
    "Operating system", "Computer network", "Internet",
    "Artificial intelligence", "Machine learning",
    "Cryptography", "Software engineering",
    "Computer architecture", "Boolean algebra",
    "Turing machine", "Big O notation",
    "HTTP", "Cloud computing", "Cybersecurity",
]

ECONOMICS = [
    "Microeconomics", "Macroeconomics", "Supply and demand",
    "Inflation", "Gross domestic product", "Fiscal policy",
    "Monetary policy", "International trade",
    "Stock market", "Federal Reserve", "Capitalism",
    "Socialism", "Market failure", "Elasticity (economics)",
    "Opportunity cost", "Comparative advantage",
]

ENGLISH_LIT = [
    "William Shakespeare", "Literary criticism",
    "Poetry", "Novel", "Short story", "Rhetoric",
    "Metaphor", "Symbolism (arts)", "Narrative",
    "Tragedy", "Comedy", "Romanticism",
    "Modernist literature", "Postmodern literature",
    "Gothic fiction", "Harlem Renaissance",
    "American literature", "English literature",
]

POLITICAL_SCIENCE = [
    "Democracy", "Republic", "Authoritarianism",
    "United States Congress", "Supreme Court of the United States",
    "Political party", "Federalism", "Separation of powers",
    "Bill of Rights", "International relations",
    "United Nations", "European Union", "NATO",
    "Political philosophy", "Liberalism", "Conservatism",
    "Constitution", "Human rights",
]

ALL_SUBJECTS = {
    "Biology": BIOLOGY,
    "Chemistry": CHEMISTRY,
    "Physics": PHYSICS,
    "US History": US_HISTORY,
    "World History": WORLD_HISTORY,
    "Mathematics": MATH,
    "Psychology": PSYCHOLOGY,
    "Computer Science": COMPUTER_SCIENCE,
    "Economics": ECONOMICS,
    "English Literature": ENGLISH_LIT,
    "Political Science": POLITICAL_SCIENCE,
}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import Wikipedia articles into StudyFlow")
    parser.add_argument("--subject", type=str, help="Subject to import (Biology, Chemistry, etc.)")
    parser.add_argument("--all", action="store_true", help="Import all subjects")
    parser.add_argument("--article", type=str, help="Import a single article by title")
    parser.add_argument("--list", action="store_true", help="List available subjects")

    args = parser.parse_args()

    if args.list:
        print("Available subjects:")
        for name, articles in ALL_SUBJECTS.items():
            print(f"  {name}: {len(articles)} articles")
        print(f"\nTotal: {sum(len(a) for a in ALL_SUBJECTS.values())} articles")

    elif args.article:
        import_article(args.article)

    elif args.subject:
        if args.subject in ALL_SUBJECTS:
            articles = ALL_SUBJECTS[args.subject]
            print(f"Importing {len(articles)} {args.subject} articles...")
            import_batch(articles, course_code=args.subject)
        else:
            print(f"Unknown subject: {args.subject}")
            print(f"Available: {', '.join(ALL_SUBJECTS.keys())}")

    elif args.all:
        for subject, articles in ALL_SUBJECTS.items():
            print(f"\n{'#'*60}")
            print(f"# {subject} ({len(articles)} articles)")
            print(f"{'#'*60}")
            import_batch(articles, course_code=subject)

    else:
        parser.print_help()
