# extension_bridge.py
"""
Local HTTP server that allows browser extension to communicate with desktop app.
Extension does all the work, desktop app just displays info.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import requests
from StudyFlow.logging_utils import debug_log

app = Flask(__name__)
CORS(app)  # Allow extension to connect

# Store state
current_quiz = None
pending_action = None  # Action for extension to take


@app.route('/health', methods=['GET'])
def health():
    """Health check - extension checks if desktop app is running"""
    return jsonify({"status": "ok", "connected": True})


@app.route('/quiz', methods=['POST'])
def receive_quiz():
    """
    Extension sends detected quiz data.
    Desktop app processes it and tells extension what to do.
    """
    global current_quiz, pending_action

    data = request.get_json()
    current_quiz = data

    question = data.get('question', '')
    answers = data.get('answers', [])

    debug_log(f"📩 Extension detected quiz: {question[:80]}...")
    debug_log(f"📋 {len(answers)} answers found")

    # Get AI answer from backend
    try:
        debug_log("🤖 Asking AI for answer...")
        ai_response = requests.post(
            'https://studyflowsuite.onrender.com/api/answer',
            json={
                'question': question,
                'answers': [a.get('text', '') for a in answers]
            },
            timeout=30
        )

        if ai_response.ok:
            result = ai_response.json()
            correct_index = result.get('correct_answer_index')
            reasoning = result.get('reasoning', '')

            debug_log(f"✅ AI says answer #{correct_index}")
            debug_log(f"💭 Reasoning: {reasoning}")

            # Tell extension to click this answer
            pending_action = {
                'action': 'click',
                'answer_index': correct_index,
                'reasoning': reasoning
            }

            # Update overlay if available
            try:
                from StudyFlow.frontend.assistant_overlay import get_overlay_state
                overlay = get_overlay_state()
                if overlay:
                    overlay.set_answered(
                        question=question,
                        answer=answers[correct_index - 1].get('text', '') if correct_index <= len(answers) else '',
                        reasoning=reasoning,
                        confidence='high',
                        method='extension'
                    )
            except Exception as e:
                debug_log(f"⚠️ Could not update overlay: {e}")

            return jsonify({
                'status': 'success',
                'action': 'click',
                'answer_index': correct_index,
                'reasoning': reasoning
            })
        else:
            debug_log(f"❌ AI request failed: {ai_response.status_code}")
            return jsonify({'status': 'error', 'message': 'AI request failed'}), 500

    except Exception as e:
        debug_log(f"❌ Error processing quiz: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/action', methods=['GET'])
def get_action():
    """Extension polls this to see if there's an action to take"""
    global pending_action

    if pending_action:
        action = pending_action
        pending_action = None  # Clear after sending
        return jsonify(action)
    else:
        return jsonify({'action': 'none'})


def start_server(port=5555):
    """Start the local server in a background thread"""
    debug_log(f"🌐 Starting extension bridge server on http://localhost:{port}")
    debug_log("📡 Extension can now connect and send quiz data")

    thread = threading.Thread(
        target=lambda: app.run(host='localhost', port=port, debug=False, use_reloader=False)
    )
    thread.daemon = True
    thread.start()

    return thread


def get_current_quiz():
    """Get the current quiz data from extension"""
    return current_quiz
