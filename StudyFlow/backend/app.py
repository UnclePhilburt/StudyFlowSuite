# app.py
from flask import Flask, request, jsonify
from .ai_manager import triple_call_ai_api_json_final  # Import your function

app = Flask(__name__)

@app.route("/api/process", methods=["POST"])
def process_data():
    # Get the JSON data sent to the endpoint
    ocr_json = request.get_json()
    # Process the data using your ai_manager function
    result = triple_call_ai_api_json_final(ocr_json)
    # Return the result as JSON
    return jsonify({"result": result})

if __name__ == "__main__":
    import os
    # Render sets the PORT; locally we default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
