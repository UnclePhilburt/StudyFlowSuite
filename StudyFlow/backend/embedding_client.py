"""
OpenAI Embedding Client for StudyFlow
Generates vector embeddings for text chunks using text-embedding-3-small
"""

import os
import openai
from typing import List
from StudyFlow.logging_utils import debug_log

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")


def generate_embedding(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    Generate a single embedding for text.

    Args:
        text: The text to embed
        model: OpenAI embedding model (default: text-embedding-3-small)

    Returns:
        List of floats representing the embedding vector (1536 dimensions)
    """
    try:
        # Clean the text
        text = text.replace("\n", " ").strip()

        if not text:
            debug_log("⚠️ Empty text passed to generate_embedding")
            return None

        # Call OpenAI API
        response = openai.embeddings.create(
            input=text,
            model=model
        )

        embedding = response.data[0].embedding
        debug_log(f"✅ Generated embedding ({len(embedding)} dimensions)")
        return embedding

    except Exception as e:
        debug_log(f"❌ Error generating embedding: {e}")
        return None


def generate_embeddings_batch(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    """
    Generate embeddings for multiple texts in a single API call (more efficient).

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model

    Returns:
        List of embedding vectors (one per input text)
    """
    try:
        # Clean texts
        cleaned_texts = [text.replace("\n", " ").strip() for text in texts if text.strip()]

        if not cleaned_texts:
            debug_log("⚠️ No valid texts to embed")
            return []

        # OpenAI supports up to 2048 inputs per batch, but let's be conservative
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(cleaned_texts), batch_size):
            batch = cleaned_texts[i:i + batch_size]

            # Call OpenAI API
            response = openai.embeddings.create(
                input=batch,
                model=model
            )

            # Extract embeddings in order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

            debug_log(f"✅ Generated {len(batch_embeddings)} embeddings (batch {i//batch_size + 1})")

        return all_embeddings

    except Exception as e:
        debug_log(f"❌ Error generating batch embeddings: {e}")
        return []


def estimate_embedding_cost(text_length: int) -> float:
    """
    Estimate the cost of embedding text.

    Args:
        text_length: Number of characters

    Returns:
        Estimated cost in USD
    """
    # text-embedding-3-small: $0.02 per 1M tokens
    # Rough estimate: 1 token ≈ 4 characters
    tokens = text_length / 4
    cost = (tokens / 1_000_000) * 0.02
    return cost


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Similarity score between -1 and 1 (higher = more similar)
    """
    import math

    # Dot product
    dot_product = sum(a * b for a, b in zip(vec1, vec2))

    # Magnitudes
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


# Example usage
if __name__ == "__main__":
    # Test single embedding
    test_text = "Photosynthesis is the process by which plants convert light energy into chemical energy."
    embedding = generate_embedding(test_text)

    if embedding:
        print(f"Generated embedding with {len(embedding)} dimensions")
        print(f"First 5 values: {embedding[:5]}")

        # Estimate cost
        cost = estimate_embedding_cost(len(test_text))
        print(f"Estimated cost: ${cost:.6f}")

    # Test batch
    test_batch = [
        "The mitochondria is the powerhouse of the cell.",
        "DNA stores genetic information in living organisms.",
        "Photosynthesis requires sunlight, water, and carbon dioxide."
    ]

    batch_embeddings = generate_embeddings_batch(test_batch)
    print(f"\nGenerated {len(batch_embeddings)} embeddings in batch")

    # Test similarity
    if len(batch_embeddings) >= 3:
        sim_0_2 = cosine_similarity(batch_embeddings[0], batch_embeddings[2])
        sim_0_1 = cosine_similarity(batch_embeddings[0], batch_embeddings[1])
        print(f"\nSimilarity between text 0 and 2 (both about biology): {sim_0_2:.4f}")
        print(f"Similarity between text 0 and 1 (different topics): {sim_0_1:.4f}")
