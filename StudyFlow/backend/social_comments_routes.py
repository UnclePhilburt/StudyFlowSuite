"""
Social Media Comments API Routes
Threaded comments with upvote/downvote system
"""

COMMENTS_ROUTES = """

# ============= COMMENTS API =============

@app.route("/api/social/posts/<post_id>/comments", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_post_comments(post_id):
    \"\"\"Get all top-level comments for a post\"\"\"
    try:
        user_id = request.user_id
        sort = request.args.get("sort", "top")  # top, new

        # Build query
        query = supabase.table("post_comments").select("*").eq("post_id", post_id).is_("parent_id", "null")

        if sort == "top":
            query = query.order("score", desc=True).order("created_at", desc=True)
        else:
            query = query.order("created_at", desc=True)

        response = query.execute()
        comments = response.data or []

        # Add user vote status
        if comments:
            comment_ids = [c["id"] for c in comments]
            votes = supabase.table("comment_votes").select("comment_id, vote_type").eq(
                "user_id", user_id
            ).in_("comment_id", comment_ids).execute()
            votes_map = {v["comment_id"]: v["vote_type"] for v in (votes.data or [])}

            for comment in comments:
                comment["user_vote_type"] = votes_map.get(comment["id"])

        return jsonify({"comments": comments}), 200

    except Exception as e:
        debug_log(f"Get comments error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>/replies", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_comment_replies(comment_id):
    \"\"\"Get all replies to a comment\"\"\"
    try:
        user_id = request.user_id

        response = supabase.table("post_comments").select("*").eq(
            "parent_id", comment_id
        ).order("created_at", desc=False).execute()  # Chronological for replies

        replies = response.data or []

        # Add user vote status
        if replies:
            reply_ids = [r["id"] for r in replies]
            votes = supabase.table("comment_votes").select("comment_id, vote_type").eq(
                "user_id", user_id
            ).in_("comment_id", reply_ids).execute()
            votes_map = {v["comment_id"]: v["vote_type"] for v in (votes.data or [])}

            for reply in replies:
                reply["user_vote_type"] = votes_map.get(reply["id"])

        return jsonify({"replies": replies}), 200

    except Exception as e:
        debug_log(f"Get replies error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>/comments", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def create_comment(post_id):
    \"\"\"Create a new comment on a post\"\"\"
    try:
        user_id = request.user_id
        data = request.json
        content = data.get("content", "").strip()
        parent_id = data.get("parent_id")  # Optional for replies

        # Validation
        if not content or len(content) < 1:
            return jsonify({"error": "Comment content required"}), 400
        if len(content) > 2000:
            return jsonify({"error": "Comment too long (max 2000 characters)"}), 400

        # Get username
        profile = get_cached_profile(user_id)
        username = profile.get("username", "Anonymous") if profile else "Anonymous"

        # Create comment
        comment_data = {
            "post_id": post_id,
            "user_id": user_id,
            "username": username,
            "content": content
        }

        if parent_id:
            # Verify parent exists
            parent = supabase.table("post_comments").select("id, post_id").eq(
                "id", parent_id
            ).single().execute()
            if not parent.data:
                return jsonify({"error": "Parent comment not found"}), 404
            if parent.data["post_id"] != post_id:
                return jsonify({"error": "Parent comment is on a different post"}), 400
            comment_data["parent_id"] = parent_id

        response = supabase.table("post_comments").insert(comment_data).execute()

        if not response.data:
            return jsonify({"error": "Failed to create comment"}), 500

        debug_log(f"Comment created: {response.data[0]['id']} by user {user_id}")

        return jsonify({"message": "Comment created", "comment": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Create comment error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>", methods=["PATCH"])
@supabase_auth_required
@account_not_frozen
def update_comment(comment_id):
    \"\"\"Update own comment\"\"\"
    try:
        user_id = request.user_id
        data = request.json
        content = data.get("content", "").strip()

        if not content or len(content) < 1:
            return jsonify({"error": "Comment content required"}), 400
        if len(content) > 2000:
            return jsonify({"error": "Comment too long"}), 400

        # Check ownership
        comment = supabase.table("post_comments").select("user_id").eq(
            "id", comment_id
        ).single().execute()

        if not comment.data:
            return jsonify({"error": "Comment not found"}), 404
        if comment.data["user_id"] != user_id:
            return jsonify({"error": "You can only edit your own comments"}), 403

        # Update
        response = supabase.table("post_comments").update({
            "content": content,
            "updated_at": "NOW()"
        }).eq("id", comment_id).execute()

        return jsonify({"message": "Comment updated", "comment": response.data[0]}), 200

    except Exception as e:
        debug_log(f"Update comment error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>", methods=["DELETE"])
@supabase_auth_required
@account_not_frozen
def delete_comment(comment_id):
    \"\"\"Delete own comment\"\"\"
    try:
        user_id = request.user_id

        # Check ownership
        comment = supabase.table("post_comments").select("user_id").eq(
            "id", comment_id
        ).single().execute()

        if not comment.data:
            return jsonify({"error": "Comment not found"}), 404
        if comment.data["user_id"] != user_id:
            return jsonify({"error": "You can only delete your own comments"}), 403

        # Delete (cascades to replies and votes)
        supabase.table("post_comments").delete().eq("id", comment_id).execute()

        return jsonify({"message": "Comment deleted"}), 200

    except Exception as e:
        debug_log(f"Delete comment error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>/vote", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def vote_on_comment(comment_id):
    \"\"\"Upvote or downvote a comment\"\"\"
    try:
        user_id = request.user_id
        data = request.json
        vote_type = data.get("vote_type")  # upvote, downvote, or null

        if vote_type and vote_type not in ["upvote", "downvote"]:
            return jsonify({"error": "Invalid vote type"}), 400

        # Check existing vote
        existing = supabase.table("comment_votes").select("id, vote_type").eq(
            "user_id", user_id
        ).eq("comment_id", comment_id).execute()

        if vote_type is None:
            # Remove vote
            if existing.data:
                supabase.table("comment_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            return jsonify({"message": "No vote to remove"}), 200

        if existing.data:
            # Update or remove
            if existing.data[0]["vote_type"] == vote_type:
                supabase.table("comment_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            else:
                supabase.table("comment_votes").update({"vote_type": vote_type}).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                return jsonify({"message": "Vote updated", "vote_type": vote_type}), 200
        else:
            # New vote
            supabase.table("comment_votes").insert({
                "user_id": user_id,
                "comment_id": comment_id,
                "vote_type": vote_type
            }).execute()
            return jsonify({"message": "Vote added", "vote_type": vote_type}), 201

    except Exception as e:
        debug_log(f"Comment vote error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""
