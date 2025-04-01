import re
import cohere
from StudyFlow.config import COHERE_API_KEY
from StudyFlow.logging_utils import debug_log

def get_cohere_answer(ocr_json, cohere_client_instance=None):
    # Create a client instance if one isn't provided.
    if cohere_client_instance is None:
        cohere_client_instance = cohere.ClientV2(api_key=COHERE_API_KEY)
    
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("Sending prompt to Cohere: " + prompt)
    
    try:
        response = cohere_client_instance.chat(
            model="command-r-plus-08-2024",
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Extract the first message from the response
        if isinstance(response, list):
            first_message = response[0]
        elif isinstance(response, dict) and "message" in response:
            first_message = response["message"]
            if isinstance(first_message, list):
                first_message = first_message[0]
        else:
            first_message = response

        # Extract content from the message
        content = ""
        if hasattr(first_message, "content") and first_message.content:
            content = first_message.content
        elif hasattr(first_message, "message") and hasattr(first_message.message, "content"):
            content = first_message.message.content
        elif isinstance(first_message, dict):
            content = first_message.get("content", "")
        else:
            content = ""
        
        if isinstance(content, list):
            content = " ".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content).strip()
        else:
            content = str(content).strip()
        
        debug_log("Extracted Cohere response: " + content)
        # Try to match a response that is just a number
        match = re.fullmatch(r'\s*(\d+)\s*', content)
        if match:
            return int(match.group(1))
        else:
            # If not a full match, try finding any digits in the content.
            numbers = re.findall(r'\d+', content)
            if numbers:
                return int(numbers[0])
            else:
                debug_log("Cohere response format error. Response: " + content)
                return None
    except Exception as e:
        debug_log("Cohere API error: " + str(e))
        return None
