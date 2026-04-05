"""
Social Media Direct Messages API Routes
Private 1-on-1 messaging between users
"""

DM_ROUTES = """

# ============= DIRECT MESSAGES API =============

@app.route("/api/social/dm/conversations", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_dm_conversations():
    \"\"\"Get all DM conversations for current user\"\"\"
    try:
        user_id = request.user_id

        # Get conversations where user is either user1 or user2
        response = supabase.table("dm_conversations").select(
            "id, user1_id, user2_id, last_message_at, created_at"
        ).or_(f"user1_id.eq.{user_id},user2_id.eq.{user_id}").order(
            "last_message_at", desc=True
        ).execute()

        conversations = response.data or []

        # For each conversation, get the other user's profile and last message
        enriched_conversations = []
        for conv in conversations:
            other_user_id = conv["user2_id"] if conv["user1_id"] == user_id else conv["user1_id"]

            # Get other user profile
            profile = supabase.table("user_profiles").select(
                "id, username, display_name, avatar_url"
            ).eq("id", other_user_id).single().execute()

            if not profile.data:
                continue

            # Get last message
            last_msg = supabase.table("dm_messages").select(
                "id, sender_id, content, created_at, is_read"
            ).eq("conversation_id", conv["id"]).order("created_at", desc=True).limit(1).execute()

            # Count unread messages
            unread = supabase.table("dm_messages").select("id", count="exact").eq(
                "conversation_id", conv["id"]
            ).eq("is_read", False).neq("sender_id", user_id).execute()

            enriched_conversations.append({
                "conversation_id": conv["id"],
                "other_user": profile.data,
                "last_message": last_msg.data[0] if last_msg.data else None,
                "unread_count": unread.count or 0,
                "updated_at": conv["last_message_at"]
            })

        return jsonify({"conversations": enriched_conversations}), 200

    except Exception as e:
        debug_log(f"Get conversations error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/dm/conversation/<username>", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_or_create_conversation(username):
    \"\"\"Get or create conversation with a user\"\"\"
    try:
        user_id = request.user_id

        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        other_user_id = target.data["id"]

        if user_id == other_user_id:
            return jsonify({"error": "Cannot message yourself"}), 400

        # Ensure consistent ordering (smaller ID first)
        user1_id = min(user_id, other_user_id)
        user2_id = max(user_id, other_user_id)

        # Check if conversation exists
        existing = supabase.table("dm_conversations").select("id").eq(
            "user1_id", user1_id
        ).eq("user2_id", user2_id).execute()

        if existing.data:
            conversation_id = existing.data[0]["id"]
        else:
            # Create new conversation
            new_conv = supabase.table("dm_conversations").insert({
                "user1_id": user1_id,
                "user2_id": user2_id
            }).execute()
            conversation_id = new_conv.data[0]["id"]

        return jsonify({"conversation_id": conversation_id}), 200

    except Exception as e:
        debug_log(f"Get/create conversation error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/dm/conversation/<conversation_id>/messages", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_dm_messages(conversation_id):
    \"\"\"Get all messages in a conversation\"\"\"
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 50
        offset = (page - 1) * per_page

        # Verify user is part of conversation
        conv = supabase.table("dm_conversations").select("user1_id, user2_id").eq(
            "id", conversation_id
        ).single().execute()

        if not conv.data:
            return jsonify({"error": "Conversation not found"}), 404

        if user_id not in [conv.data["user1_id"], conv.data["user2_id"]]:
            return jsonify({"error": "Not authorized"}), 403

        # Get messages
        response = supabase.table("dm_messages").select("*").eq(
            "conversation_id", conversation_id
        ).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        messages = (response.data or [])[::-1]  # Reverse to show oldest first

        # Mark messages as read
        if messages:
            unread_ids = [m["id"] for m in messages if not m["is_read"] and m["sender_id"] != user_id]
            if unread_ids:
                supabase.table("dm_messages").update({"is_read": True}).in_("id", unread_ids).execute()

        return jsonify({"messages": messages, "page": page}), 200

    except Exception as e:
        debug_log(f"Get messages error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/dm/conversation/<conversation_id>/send", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def send_dm_message(conversation_id):
    \"\"\"Send a message in a conversation\"\"\"
    try:
        user_id = request.user_id
        data = request.json
        content = data.get("content", "").strip()

        # Validation
        if not content or len(content) < 1:
            return jsonify({"error": "Message content required"}), 400
        if len(content) > 2000:
            return jsonify({"error": "Message too long (max 2000 characters)"}), 400

        # Verify user is part of conversation
        conv = supabase.table("dm_conversations").select("user1_id, user2_id").eq(
            "id", conversation_id
        ).single().execute()

        if not conv.data:
            return jsonify({"error": "Conversation not found"}), 404

        if user_id not in [conv.data["user1_id"], conv.data["user2_id"]]:
            return jsonify({"error": "Not authorized"}), 403

        # Send message
        response = supabase.table("dm_messages").insert({
            "conversation_id": conversation_id,
            "sender_id": user_id,
            "content": content
        }).execute()

        if not response.data:
            return jsonify({"error": "Failed to send message"}), 500

        debug_log(f"DM sent in conversation {conversation_id} by user {user_id}")

        return jsonify({"message": "Message sent", "dm": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Send message error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/dm/unread-count", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_unread_dm_count():
    \"\"\"Get total unread message count for user\"\"\"
    try:
        user_id = request.user_id

        # Get all conversations
        convs = supabase.table("dm_conversations").select("id").or_(
            f"user1_id.eq.{user_id},user2_id.eq.{user_id}"
        ).execute()

        conv_ids = [c["id"] for c in (convs.data or [])]

        if not conv_ids:
            return jsonify({"unread_count": 0}), 200

        # Count unread messages (not sent by user)
        unread = supabase.table("dm_messages").select("id", count="exact").in_(
            "conversation_id", conv_ids
        ).eq("is_read", False).neq("sender_id", user_id).execute()

        return jsonify({"unread_count": unread.count or 0}), 200

    except Exception as e:
        debug_log(f"Get unread count error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""
