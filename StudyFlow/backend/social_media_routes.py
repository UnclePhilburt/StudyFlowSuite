"""
Social Media API Routes for StudyFlow Suite
Instagram/Reddit hybrid for sharing and discovering notes

To integrate: Copy the routes marked with ### INTEGRATION ### to app.py
"""

SOCIAL_ROUTES = """

# ============= SOCIAL MEDIA API =============

@app.route("/api/social/feed", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_social_feed():
    \"\"\"Get personalized feed from followed users\"\"\"
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        # Get posts from followed users + own posts
        query = \"\"\"
            SELECT sp.*,
                   n.original_filename, n.thumbnail_url, n.file_type,
                   EXISTS(SELECT 1 FROM post_votes WHERE post_id = sp.id AND user_id = %s) as user_voted,
                   (SELECT vote_type FROM post_votes WHERE post_id = sp.id AND user_id = %s) as user_vote_type,
                   EXISTS(SELECT 1 FROM post_bookmarks WHERE post_id = sp.id AND user_id = %s) as is_bookmarked
            FROM social_posts sp
            LEFT JOIN notes n ON sp.note_id = n.id
            WHERE sp.user_id IN (
                SELECT following_id FROM user_followers WHERE follower_id = %s
                UNION
                SELECT %s
            )
            ORDER BY sp.created_at DESC
            LIMIT %s OFFSET %s
        \"\"\"

        response = supabase.rpc('execute_sql', {
            'query': query,
            'params': [user_id, user_id, user_id, user_id, user_id, per_page, offset]
        }).execute()

        return jsonify({"posts": response.data or [], "page": page}), 200

    except Exception as e:
        debug_log(f"Get feed error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/trending", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_trending_posts():
    \"\"\"Get trending posts by score\"\"\"
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        timeframe = request.args.get("timeframe", "week")  # day, week, month, all
        per_page = 20
        offset = (page - 1) * per_page

        # Calculate time filter
        time_filters = {
            "day": "sp.created_at > NOW() - INTERVAL '24 hours'",
            "week": "sp.created_at > NOW() - INTERVAL '7 days'",
            "month": "sp.created_at > NOW() - INTERVAL '30 days'",
            "all": "TRUE"
        }
        time_filter = time_filters.get(timeframe, time_filters["week"])

        # Get trending posts
        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type)"
        ).order("score", desc=True).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        posts = response.data or []

        # Add user interaction flags
        if posts:
            post_ids = [p["id"] for p in posts]

            # Get user votes
            votes = supabase.table("post_votes").select("post_id, vote_type").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()

            votes_map = {v["post_id"]: v["vote_type"] for v in (votes.data or [])}

            # Get bookmarks
            bookmarks = supabase.table("post_bookmarks").select("post_id").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()

            bookmark_ids = {b["post_id"] for b in (bookmarks.data or [])}

            for post in posts:
                post["user_vote_type"] = votes_map.get(post["id"])
                post["is_bookmarked"] = post["id"] in bookmark_ids

        return jsonify({"posts": posts, "page": page}), 200

    except Exception as e:
        debug_log(f"Get trending error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def create_social_post():
    \"\"\"Create a new social post\"\"\"
    try:
        user_id = request.user_id
        data = request.json

        post_type = data.get("post_type")  # note, text, group_invite
        note_id = data.get("note_id")
        text_content = data.get("text_content", "").strip()
        group_id = data.get("group_id")

        # Validation
        if post_type not in ["note", "text", "group_invite"]:
            return jsonify({"error": "Invalid post type"}), 400

        if post_type == "note" and not note_id:
            return jsonify({"error": "Note ID required for note posts"}), 400

        if post_type == "text" and (not text_content or len(text_content) < 1):
            return jsonify({"error": "Text content required for text posts"}), 400

        if post_type == "group_invite" and not group_id:
            return jsonify({"error": "Group ID required for group invite posts"}), 400

        # Get username
        profile = get_cached_profile(user_id)
        username = profile.get("username", "Anonymous") if profile else "Anonymous"

        # Create post
        post_data = {
            "user_id": user_id,
            "username": username,
            "post_type": post_type,
            "text_content": text_content if text_content else None
        }

        if post_type == "note":
            post_data["note_id"] = note_id
        elif post_type == "group_invite":
            post_data["group_id"] = group_id

        response = supabase.table("social_posts").insert(post_data).execute()

        if not response.data:
            return jsonify({"error": "Failed to create post"}), 500

        # Update user post count
        supabase.table("user_profiles").update({
            "post_count": supabase.rpc("increment", {"x": 1})
        }).eq("id", user_id).execute()

        debug_log(f"Social post created: {response.data[0]['id']} by user {user_id}")

        return jsonify({"message": "Post created", "post": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Create post error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_post_detail(post_id):
    \"\"\"Get single post with full details\"\"\"
    try:
        user_id = request.user_id

        # Get post
        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type, university, course_code)"
        ).eq("id", post_id).single().execute()

        if not response.data:
            return jsonify({"error": "Post not found"}), 404

        post = response.data

        # Add user interaction flags
        vote = supabase.table("post_votes").select("vote_type").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        post["user_vote_type"] = vote.data[0]["vote_type"] if vote.data else None

        bookmark = supabase.table("post_bookmarks").select("id").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        post["is_bookmarked"] = bool(bookmark.data)

        return jsonify({"post": post}), 200

    except Exception as e:
        debug_log(f"Get post detail error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>/vote", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def vote_on_post(post_id):
    \"\"\"Upvote or downvote a post\"\"\"
    try:
        user_id = request.user_id
        data = request.json
        vote_type = data.get("vote_type")  # upvote, downvote, or null to remove

        if vote_type and vote_type not in ["upvote", "downvote"]:
            return jsonify({"error": "Invalid vote type"}), 400

        # Check existing vote
        existing = supabase.table("post_votes").select("id, vote_type").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        if vote_type is None:
            # Remove vote
            if existing.data:
                supabase.table("post_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            return jsonify({"message": "No vote to remove"}), 200

        if existing.data:
            # Update existing vote
            if existing.data[0]["vote_type"] == vote_type:
                # Same vote, remove it
                supabase.table("post_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            else:
                # Change vote
                supabase.table("post_votes").update({"vote_type": vote_type}).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                return jsonify({"message": "Vote updated", "vote_type": vote_type}), 200
        else:
            # New vote
            supabase.table("post_votes").insert({
                "user_id": user_id,
                "post_id": post_id,
                "vote_type": vote_type
            }).execute()
            return jsonify({"message": "Vote added", "vote_type": vote_type}), 201

    except Exception as e:
        debug_log(f"Vote error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>/bookmark", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def toggle_bookmark(post_id):
    \"\"\"Save or unsave a post\"\"\"
    try:
        user_id = request.user_id

        # Check existing bookmark
        existing = supabase.table("post_bookmarks").select("id").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        if existing.data:
            # Remove bookmark
            supabase.table("post_bookmarks").delete().eq("id", existing.data[0]["id"]).execute()
            return jsonify({"message": "Bookmark removed", "is_bookmarked": False}), 200
        else:
            # Add bookmark
            supabase.table("post_bookmarks").insert({
                "user_id": user_id,
                "post_id": post_id
            }).execute()
            return jsonify({"message": "Bookmark added", "is_bookmarked": True}), 201

    except Exception as e:
        debug_log(f"Bookmark error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>", methods=["DELETE"])
@supabase_auth_required
@account_not_frozen
def delete_post(post_id):
    \"\"\"Delete own post\"\"\"
    try:
        user_id = request.user_id

        # Check ownership
        post = supabase.table("social_posts").select("user_id").eq("id", post_id).single().execute()

        if not post.data:
            return jsonify({"error": "Post not found"}), 404

        if post.data["user_id"] != user_id:
            return jsonify({"error": "You can only delete your own posts"}), 403

        # Delete post (cascades to votes, comments, bookmarks)
        supabase.table("social_posts").delete().eq("id", post_id).execute()

        # Update user post count
        supabase.table("user_profiles").update({
            "post_count": supabase.rpc("decrement", {"x": 1})
        }).eq("id", user_id).execute()

        debug_log(f"Post deleted: {post_id} by user {user_id}")

        return jsonify({"message": "Post deleted"}), 200

    except Exception as e:
        debug_log(f"Delete post error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/bookmarks", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_bookmarks():
    \"\"\"Get user's saved posts\"\"\"
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        # Get bookmarked posts
        response = supabase.table("post_bookmarks").select(
            "created_at, social_posts(*, notes(original_filename, thumbnail_url, file_type))"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        bookmarks = response.data or []
        posts = [{"bookmark_date": b["created_at"], **b["social_posts"]} for b in bookmarks if b.get("social_posts")]

        # Add vote status
        if posts:
            post_ids = [p["id"] for p in posts]
            votes = supabase.table("post_votes").select("post_id, vote_type").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()
            votes_map = {v["post_id"]: v["vote_type"] for v in (votes.data or [])}

            for post in posts:
                post["user_vote_type"] = votes_map.get(post["id"])
                post["is_bookmarked"] = True

        return jsonify({"posts": posts, "page": page}), 200

    except Exception as e:
        debug_log(f"Get bookmarks error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""

if __name__ == "__main__":
    print("Social Media Routes - Ready for integration")
    print("Copy the SOCIAL_ROUTES content to app.py before 'if __name__ == \"__main__\"'")
