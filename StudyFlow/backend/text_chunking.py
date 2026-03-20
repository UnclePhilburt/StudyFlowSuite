"""
Text chunking utilities for RAG
Splits large text into overlapping chunks for better semantic search
"""

import re
from typing import List
from StudyFlow.logging_utils import debug_log


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into chunks of approximately chunk_size words with overlap.

    Args:
        text: The text to chunk
        chunk_size: Target number of words per chunk (default: 500)
        overlap: Number of words to overlap between chunks (default: 50)

    Returns:
        List of text chunks
    """
    # Clean the text
    text = text.strip()
    if not text:
        return []

    # Split into words (preserving whitespace context)
    words = text.split()

    if len(words) <= chunk_size:
        # Text is small enough, return as single chunk
        return [text]

    chunks = []
    start_idx = 0

    while start_idx < len(words):
        # Get chunk_size words starting from start_idx
        end_idx = start_idx + chunk_size
        chunk_words = words[start_idx:end_idx]

        # Join back into text
        chunk = " ".join(chunk_words)
        chunks.append(chunk)

        # Move to next chunk, accounting for overlap
        start_idx += chunk_size - overlap

        # Prevent infinite loop if we're at the end
        if end_idx >= len(words):
            break

    debug_log(f"✂️ Split text into {len(chunks)} chunks ({len(words)} words total)")
    return chunks


def chunk_text_smart(text: str, chunk_size: int = 500, overlap: int = 50) -> List[dict]:
    """
    Smart chunking that tries to split on natural boundaries (paragraphs, sentences).

    Returns list of dicts with 'text' and 'metadata' keys.
    """
    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n', text)

    chunks = []
    current_chunk = []
    current_word_count = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_words = para.split()
        para_word_count = len(para_words)

        # If adding this paragraph would exceed chunk_size, save current chunk
        if current_word_count > 0 and current_word_count + para_word_count > chunk_size:
            # Save current chunk
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "word_count": current_word_count
            })

            # Start new chunk with overlap from previous
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:]
                current_word_count = overlap
            else:
                current_chunk = []
                current_word_count = 0

        # Add paragraph to current chunk
        current_chunk.extend(para_words)
        current_word_count += para_word_count

    # Don't forget the last chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunks.append({
            "text": chunk_text,
            "word_count": current_word_count
        })

    debug_log(f"✂️ Smart chunking: {len(paragraphs)} paragraphs → {len(chunks)} chunks")
    return chunks


def estimate_tokens(text: str) -> int:
    """
    Rough estimate of OpenAI tokens (1 token ≈ 0.75 words)
    """
    word_count = len(text.split())
    return int(word_count * 1.33)  # words / 0.75


# Example usage
if __name__ == "__main__":
    sample_text = """
    This is a sample document. It has multiple paragraphs.

    The second paragraph talks about something else. We want to split this into chunks.

    The third paragraph continues the discussion. This chunking system is designed for RAG.

    And so on. The overlap ensures that concepts split across chunk boundaries are still captured.
    """

    chunks = chunk_text_smart(sample_text, chunk_size=20, overlap=5)
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1} ({chunk['word_count']} words):")
        print(chunk['text'])
        print()
