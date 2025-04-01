# deepflow.py
import openai
import json

def get_deepflow_question(topic, previous_questions):
    """
    Generates a multiple-choice question using the OpenAI API.
    
    Args:
        topic (str): The topic the user wants to learn about.
        previous_questions (list): List of previously asked questions to avoid repeats.
        
    Returns:
        dict: A dictionary with keys "question", "options", "correct_index", and "explanation",
              or None if an error occurs.
    """
    prompt = (
        f"You are a helpful study assistant. The user wants to learn about '{topic}'. "
        "Generate a multiple-choice question with 4 answer options (only one of which is correct). "
        "Return a JSON object with the following keys:\n"
        "  - 'question': the question text\n"
        "  - 'options': a list of 4 answer options\n"
        "  - 'correct_index': the 0-indexed number of the correct option\n"
        "  - 'explanation': a brief explanation of why that answer is correct.\n"
    )
    
    # If there are previous questions, include them to avoid repetition.
    if previous_questions:
        prompt += "Do not repeat any of the following questions: " + ", ".join(previous_questions) + "."
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
    except Exception as e:
        print("Error calling OpenAI API:", e)
        return None

    result_text = response.choices[0].message["content"]
    
    try:
        result = json.loads(result_text)
        return result
    except json.JSONDecodeError as e:
        print("Error decoding JSON:", e)
        print("Received response:", result_text)
        return None
