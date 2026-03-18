"""
Gemini API client for quiz question answering
Uses Gemini 1.5 Flash for fast, cheap responses
"""
import os
import json
from collections import Counter
import google.generativeai as genai
from StudyFlow.logging_utils import debug_log


def get_gemini_answer_single(question, answers, attempt_num=1, model_name='gemini-2.5-flash'):
    """
    Get a single answer from Gemini.

    Args:
        question (str): The quiz question text
        answers (list): List of answer choices
        attempt_num (int): Attempt number for logging
        model_name (str): Gemini model to use

    Returns:
        dict: Answer response with index, text, confidence, reasoning
    """
    try:
        # Configure Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            debug_log("⚠️ GEMINI_API_KEY not found in environment")
            return None

        genai.configure(api_key=api_key)

        # Map user-friendly names to actual API model names
        model_mapping = {
            'gemini-2.5-flash': 'gemini-2.5-flash',
            'gemini-2.5-pro': 'gemini-2.5-pro',
            'gemini-3-flash-preview': 'gemini-3-flash-preview',
            'gemini-3.1-flash-lite-preview': 'gemini-3.1-flash-lite-preview',
            'gemini-3.1-pro-preview': 'gemini-3.1-pro-preview'
        }

        actual_model_name = model_mapping.get(model_name, model_name)
        debug_log(f"Using Gemini model: {actual_model_name}")

        # Format answers
        answers_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))

        prompt = f"""Answer this quiz question and return ONLY a JSON object.

Question: {question}

Options:
{answers_text}

Return this exact JSON format:
{{
    "correct_answer_index": <number 1-{len(answers)}>,
    "correct_answer_text": "<answer text>",
    "confidence": "high",
    "reasoning": "<10 words max>"
}}

Rules: Index is 1-based. Keep reasoning under 10 words. Return ONLY valid JSON."""

        # Use specified Gemini model
        model = genai.GenerativeModel(actual_model_name)

        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.1,
                'max_output_tokens': 100,  # Reduced to prevent truncation issues
            }
        )

        response_text = response.text.strip()
        debug_log(f"📥 Gemini ({actual_model_name}) raw response ({len(response_text)} chars): {response_text[:500]}...")

        # Parse JSON - handle markdown code blocks
        if "```" in response_text:
            lines = response_text.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```json") or line.startswith("```"):
                    in_json = not in_json
                    continue
                if in_json:
                    json_lines.append(line)
            response_text = "\n".join(json_lines)

        result = json.loads(response_text)
        debug_log(f"🤖 Gemini ({actual_model_name}) attempt {attempt_num}: Answer={result.get('correct_answer_index')}, Confidence={result.get('confidence')}")

        return result

    except json.JSONDecodeError as e:
        debug_log(f"❌ Gemini attempt {attempt_num} JSON parse error: {e}")
        debug_log(f"Raw response was: {response_text}")
        return None
    except Exception as e:
        import traceback
        debug_log(f"❌ Gemini attempt {attempt_num} API error: {e}")
        debug_log(f"Full traceback: {traceback.format_exc()}")
        return None


def get_gemini_answer(question, answers, model='gemini-2.5-flash'):
    """
    Get answer from Gemini with 3-vote system for improved accuracy.
    Calls Gemini 3 times and returns the majority answer.

    Args:
        question (str): The quiz question text
        answers (list): List of answer choices
        model (str): Gemini model to use (default: gemini-2.5-flash)

    Returns:
        dict: Answer response with index, text, confidence, reasoning
    """
    debug_log(f"🗳️ Starting 3-vote Gemini system with {model}...")

    votes = []
    results = []

    # Get 3 independent answers
    for i in range(3):
        result = get_gemini_answer_single(question, answers, attempt_num=i+1, model_name=model)
        if result and result.get('correct_answer_index'):
            votes.append(result['correct_answer_index'])
            results.append(result)

    if not votes:
        debug_log("❌ All 3 Gemini attempts failed")
        return None

    # Count votes
    vote_counts = Counter(votes)
    winning_answer = vote_counts.most_common(1)[0][0]
    vote_count = vote_counts[winning_answer]

    debug_log(f"📊 Voting results: {dict(vote_counts)}")
    debug_log(f"✅ Winner: Answer {winning_answer} with {vote_count}/3 votes")

    # Find the result that matches the winning answer
    winning_result = None
    for result in results:
        if result['correct_answer_index'] == winning_answer:
            winning_result = result
            break

    # If we have unanimous or majority vote, increase confidence
    if vote_count == 3:
        winning_result['confidence'] = 'high'
        winning_result['reasoning'] = f"[UNANIMOUS 3/3] {winning_result.get('reasoning', '')}"
    elif vote_count == 2:
        winning_result['confidence'] = 'medium'
        winning_result['reasoning'] = f"[MAJORITY 2/3] {winning_result.get('reasoning', '')}"
    else:
        winning_result['confidence'] = 'low'
        winning_result['reasoning'] = f"[SPLIT VOTE 1/3] {winning_result.get('reasoning', '')}"

    return winning_result


def get_gemini_essay(question, model='gemini-2.5-flash'):
    """
    Generate an essay/short answer using Gemini.

    Args:
        question (str): The essay question
        model (str): Gemini model to use (default: gemini-2.5-flash)

    Returns:
        str: The generated essay answer
    """
    try:
        # Configure Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            debug_log("⚠️ GEMINI_API_KEY not found in environment")
            return None

        genai.configure(api_key=api_key)

        prompt = f"""You are answering a quiz question that requires a text response (essay, short answer, or fill-in-the-blank).

Question: {question}

Provide an accurate answer. Follow these rules:
- For fill-in-the-blank questions (asking for a single word/phrase/number): Give ONLY the answer, no extra text
- For short answer questions: Provide 2-5 complete sentences
- For essay questions: Provide 1-3 well-structured paragraphs
- Be factually accurate and direct
- Use a natural, student-like tone
- If the question asks for a definition, name, date, or specific term, provide just that without elaboration

Return ONLY the answer text, nothing else."""

        # Map model name
        model_mapping = {
            'gemini-2.5-flash': 'gemini-2.5-flash',
            'gemini-2.5-pro': 'gemini-2.5-pro'
        }
        actual_model = model_mapping.get(model, model)
        debug_log(f"Using Gemini model for essay: {actual_model}")

        # Use specified Gemini model
        gemini_model = genai.GenerativeModel(actual_model)

        response = gemini_model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.7,
                'max_output_tokens': 500,
            }
        )

        essay_answer = response.text.strip()
        debug_log(f"📝 Gemini ({actual_model}) essay: Generated {len(essay_answer)} characters")

        return essay_answer

    except Exception as e:
        debug_log(f"❌ Gemini essay error: {e}")
        return None
