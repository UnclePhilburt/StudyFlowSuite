"""
Script to insert all social media routes into app.py
Run this once to add the complete social media system
"""

import os

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))
app_py_path = os.path.join(script_dir, "app.py")

# All social media routes combined
SOCIAL_ROUTES = '''

# ============= SOCIAL MEDIA API =============
# Instagram/Reddit hybrid for sharing and discovering notes

# --- POSTS & FEED ---

@app.route("/api/social/feed", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_social_feed():
    """Get personalized feed from followed users"""
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        # Get posts from followed users + own posts
        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type)"
        ).in_("user_id",
            supabase.table("user_followers").select("following_id").eq("follower_id", user_id)
        ).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        posts = response.data or []

        # Add user interaction flags
        if posts:
            post_ids = [p["id"] for p in posts]
            votes = supabase.table("post_votes").select("post_id, vote_type").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()
            votes_map = {v["post_id"]: v["vote_type"] for v in (votes.data or [])}

            bookmarks = supabase.table("post_bookmarks").select("post_id").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()
            bookmark_ids = {b["post_id"] for b in (bookmarks.data or [])}

            for post in posts:
                post["user_vote_type"] = votes_map.get(post["id"])
                post["is_bookmarked"] = post["id"] in bookmark_ids

        return jsonify({"posts": posts, "page": page}), 200

    except Exception as e:
        debug_log(f"Get feed error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/trending", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_trending_posts():
    """Get trending posts by score"""
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type)"
        ).order("score", desc=True).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        posts = response.data or []

        if posts:
            post_ids = [p["id"] for p in posts]
            votes = supabase.table("post_votes").select("post_id, vote_type").eq(
                "user_id", user_id
            ).in_("post_id", post_ids).execute()
            votes_map = {v["post_id"]: v["vote_type"] for v in (votes.data or [])}

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
    """Create a new social post"""
    try:
        user_id = request.user_id
        data = request.json

        post_type = data.get("post_type")
        note_id = data.get("note_id")
        text_content = data.get("text_content", "").strip()
        group_id = data.get("group_id")

        if post_type not in ["note", "text", "group_invite"]:
            return jsonify({"error": "Invalid post type"}), 400

        profile = get_cached_profile(user_id)
        username = profile.get("username", "Anonymous") if profile else "Anonymous"

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

        return jsonify({"message": "Post created", "post": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Create post error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/posts/<post_id>", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_post_detail(post_id):
    """Get single post details"""
    try:
        user_id = request.user_id

        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type, university, course_code)"
        ).eq("id", post_id).single().execute()

        if not response.data:
            return jsonify({"error": "Post not found"}), 404

        post = response.data

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
    """Upvote or downvote a post"""
    try:
        user_id = request.user_id
        data = request.json
        vote_type = data.get("vote_type")

        if vote_type and vote_type not in ["upvote", "downvote"]:
            return jsonify({"error": "Invalid vote type"}), 400

        existing = supabase.table("post_votes").select("id, vote_type").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        if vote_type is None:
            if existing.data:
                supabase.table("post_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            return jsonify({"message": "No vote to remove"}), 200

        if existing.data:
            if existing.data[0]["vote_type"] == vote_type:
                supabase.table("post_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            else:
                supabase.table("post_votes").update({"vote_type": vote_type}).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                return jsonify({"message": "Vote updated", "vote_type": vote_type}), 200
        else:
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
    """Save or unsave a post"""
    try:
        user_id = request.user_id

        existing = supabase.table("post_bookmarks").select("id").eq(
            "user_id", user_id
        ).eq("post_id", post_id).execute()

        if existing.data:
            supabase.table("post_bookmarks").delete().eq("id", existing.data[0]["id"]).execute()
            return jsonify({"message": "Bookmark removed", "is_bookmarked": False}), 200
        else:
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
    """Delete own post"""
    try:
        user_id = request.user_id

        post = supabase.table("social_posts").select("user_id").eq("id", post_id).single().execute()

        if not post.data:
            return jsonify({"error": "Post not found"}), 404

        if post.data["user_id"] != user_id:
            return jsonify({"error": "You can only delete your own posts"}), 403

        supabase.table("social_posts").delete().eq("id", post_id).execute()

        return jsonify({"message": "Post deleted"}), 200

    except Exception as e:
        debug_log(f"Delete post error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/bookmarks", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_bookmarks():
    """Get user's saved posts"""
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        response = supabase.table("post_bookmarks").select(
            "created_at, social_posts(*, notes(original_filename, thumbnail_url, file_type))"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        bookmarks = response.data or []
        posts = [{"bookmark_date": b["created_at"], **b["social_posts"]} for b in bookmarks if b.get("social_posts")]

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


# --- COMMENTS ---

@app.route("/api/social/posts/<post_id>/comments", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_post_comments(post_id):
    """Get all top-level comments for a post"""
    try:
        user_id = request.user_id
        sort = request.args.get("sort", "top")

        query = supabase.table("post_comments").select("*").eq("post_id", post_id).is_("parent_id", "null")

        if sort == "top":
            query = query.order("score", desc=True).order("created_at", desc=True)
        else:
            query = query.order("created_at", desc=True)

        response = query.execute()
        comments = response.data or []

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
    """Get all replies to a comment"""
    try:
        user_id = request.user_id

        response = supabase.table("post_comments").select("*").eq(
            "parent_id", comment_id
        ).order("created_at", desc=False).execute()

        replies = response.data or []

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
    """Create a new comment on a post"""
    try:
        user_id = request.user_id
        data = request.json
        content = data.get("content", "").strip()
        parent_id = data.get("parent_id")

        if not content or len(content) < 1:
            return jsonify({"error": "Comment content required"}), 400
        if len(content) > 2000:
            return jsonify({"error": "Comment too long"}), 400

        profile = get_cached_profile(user_id)
        username = profile.get("username", "Anonymous") if profile else "Anonymous"

        comment_data = {
            "post_id": post_id,
            "user_id": user_id,
            "username": username,
            "content": content
        }

        if parent_id:
            parent = supabase.table("post_comments").select("id, post_id").eq(
                "id", parent_id
            ).single().execute()
            if not parent.data or parent.data["post_id"] != post_id:
                return jsonify({"error": "Invalid parent comment"}), 400
            comment_data["parent_id"] = parent_id

        response = supabase.table("post_comments").insert(comment_data).execute()

        if not response.data:
            return jsonify({"error": "Failed to create comment"}), 500

        return jsonify({"message": "Comment created", "comment": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Create comment error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>", methods=["DELETE"])
@supabase_auth_required
@account_not_frozen
def delete_comment(comment_id):
    """Delete own comment"""
    try:
        user_id = request.user_id

        comment = supabase.table("post_comments").select("user_id").eq(
            "id", comment_id
        ).single().execute()

        if not comment.data:
            return jsonify({"error": "Comment not found"}), 404
        if comment.data["user_id"] != user_id:
            return jsonify({"error": "You can only delete your own comments"}), 403

        supabase.table("post_comments").delete().eq("id", comment_id).execute()

        return jsonify({"message": "Comment deleted"}), 200

    except Exception as e:
        debug_log(f"Delete comment error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/comments/<comment_id>/vote", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def vote_on_comment(comment_id):
    """Upvote or downvote a comment"""
    try:
        user_id = request.user_id
        data = request.json
        vote_type = data.get("vote_type")

        if vote_type and vote_type not in ["upvote", "downvote"]:
            return jsonify({"error": "Invalid vote type"}), 400

        existing = supabase.table("comment_votes").select("id, vote_type").eq(
            "user_id", user_id
        ).eq("comment_id", comment_id).execute()

        if vote_type is None:
            if existing.data:
                supabase.table("comment_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            return jsonify({"message": "No vote to remove"}), 200

        if existing.data:
            if existing.data[0]["vote_type"] == vote_type:
                supabase.table("comment_votes").delete().eq("id", existing.data[0]["id"]).execute()
                return jsonify({"message": "Vote removed"}), 200
            else:
                supabase.table("comment_votes").update({"vote_type": vote_type}).eq(
                    "id", existing.data[0]["id"]
                ).execute()
                return jsonify({"message": "Vote updated", "vote_type": vote_type}), 200
        else:
            supabase.table("comment_votes").insert({
                "user_id": user_id,
                "comment_id": comment_id,
                "vote_type": vote_type
            }).execute()
            return jsonify({"message": "Vote added", "vote_type": vote_type}), 201

    except Exception as e:
        debug_log(f"Comment vote error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# --- PROFILES & FOLLOWERS ---

@app.route("/api/social/profile/<username>", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_user_profile(username):
    """Get public user profile"""
    try:
        current_user_id = request.user_id

        profile = supabase.table("user_profiles").select(
            "id, username, display_name, bio, avatar_url, banner_url, "
            "follower_count, following_count, post_count, is_public, created_at"
        ).eq("username", username).single().execute()

        if not profile.data:
            return jsonify({"error": "User not found"}), 404

        profile_data = profile.data
        profile_user_id = profile_data["id"]

        follow = supabase.table("user_followers").select("id").eq(
            "follower_id", current_user_id
        ).eq("following_id", profile_user_id).execute()

        profile_data["is_following"] = bool(follow.data)
        profile_data["is_own_profile"] = current_user_id == profile_user_id

        posts = supabase.table("social_posts").select(
            "id, post_type, created_at, score, comment_count, "
            "notes(thumbnail_url, file_type)"
        ).eq("user_id", profile_user_id).order("created_at", desc=True).limit(12).execute()

        profile_data["recent_posts"] = posts.data or []

        return jsonify({"profile": profile_data}), 200

    except Exception as e:
        debug_log(f"Get profile error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/profile", methods=["PATCH"])
@supabase_auth_required
@account_not_frozen
def update_own_profile():
    """Update own profile (bio, display name, avatar, banner)"""
    try:
        user_id = request.user_id
        data = request.json

        update_data = {}

        if "bio" in data:
            bio = data["bio"].strip() if data["bio"] else None
            if bio and len(bio) > 500:
                return jsonify({"error": "Bio too long"}), 400
            update_data["bio"] = bio

        if "display_name" in data:
            display_name = data["display_name"].strip() if data["display_name"] else None
            if display_name and len(display_name) > 50:
                return jsonify({"error": "Display name too long"}), 400
            update_data["display_name"] = display_name

        if "avatar_url" in data:
            update_data["avatar_url"] = data["avatar_url"]

        if "banner_url" in data:
            update_data["banner_url"] = data["banner_url"]

        if not update_data:
            return jsonify({"error": "No fields to update"}), 400

        response = supabase.table("user_profiles").update(update_data).eq("id", user_id).execute()

        return jsonify({"message": "Profile updated", "profile": response.data[0]}), 200

    except Exception as e:
        debug_log(f"Update profile error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/follow/<username>", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def follow_user(username):
    """Follow a user"""
    try:
        follower_id = request.user_id

        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        following_id = target.data["id"]

        if follower_id == following_id:
            return jsonify({"error": "Cannot follow yourself"}), 400

        user1_id = min(follower_id, following_id)
        user2_id = max(follower_id, following_id)

        existing = supabase.table("user_followers").select("id").eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()

        if existing.data:
            return jsonify({"message": "Already following", "is_following": True}), 200

        supabase.table("user_followers").insert({
            "follower_id": follower_id,
            "following_id": following_id
        }).execute()

        return jsonify({"message": "Followed successfully", "is_following": True}), 201

    except Exception as e:
        debug_log(f"Follow error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/unfollow/<username>", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def unfollow_user(username):
    """Unfollow a user"""
    try:
        follower_id = request.user_id

        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        following_id = target.data["id"]

        result = supabase.table("user_followers").delete().eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()

        if not result.data:
            return jsonify({"message": "Not following", "is_following": False}), 200

        return jsonify({"message": "Unfollowed successfully", "is_following": False}), 200

    except Exception as e:
        debug_log(f"Unfollow error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/search/users", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def search_users():
    """Search for users by username or display name"""
    try:
        query = request.args.get("q", "").strip()

        if not query or len(query) < 2:
            return jsonify({"error": "Search query too short"}), 400

        response = supabase.table("user_profiles").select(
            "id, username, display_name, avatar_url, bio, follower_count"
        ).or_(f"username.ilike.%{query}%,display_name.ilike.%{query}%").limit(20).execute()

        users = response.data or []

        return jsonify({"users": users}), 200

    except Exception as e:
        debug_log(f"Search users error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# --- DIRECT MESSAGES ---

@app.route("/api/social/dm/conversations", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_dm_conversations():
    """Get all DM conversations for current user"""
    try:
        user_id = request.user_id

        response = supabase.table("dm_conversations").select(
            "id, user1_id, user2_id, last_message_at, created_at"
        ).or_(f"user1_id.eq.{user_id},user2_id.eq.{user_id}").order(
            "last_message_at", desc=True
        ).execute()

        conversations = response.data or []

        enriched_conversations = []
        for conv in conversations:
            other_user_id = conv["user2_id"] if conv["user1_id"] == user_id else conv["user1_id"]

            profile = supabase.table("user_profiles").select(
                "id, username, display_name, avatar_url"
            ).eq("id", other_user_id).single().execute()

            if not profile.data:
                continue

            last_msg = supabase.table("dm_messages").select(
                "id, sender_id, content, created_at, is_read"
            ).eq("conversation_id", conv["id"]).order("created_at", desc=True).limit(1).execute()

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
    """Get or create conversation with a user"""
    try:
        user_id = request.user_id

        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        other_user_id = target.data["id"]

        if user_id == other_user_id:
            return jsonify({"error": "Cannot message yourself"}), 400

        user1_id = min(user_id, other_user_id)
        user2_id = max(user_id, other_user_id)

        existing = supabase.table("dm_conversations").select("id").eq(
            "user1_id", user1_id
        ).eq("user2_id", user2_id).execute()

        if existing.data:
            conversation_id = existing.data[0]["id"]
        else:
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
    """Get all messages in a conversation"""
    try:
        user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 50
        offset = (page - 1) * per_page

        conv = supabase.table("dm_conversations").select("user1_id, user2_id").eq(
            "id", conversation_id
        ).single().execute()

        if not conv.data:
            return jsonify({"error": "Conversation not found"}), 404

        if user_id not in [conv.data["user1_id"], conv.data["user2_id"]]:
            return jsonify({"error": "Not authorized"}), 403

        response = supabase.table("dm_messages").select("*").eq(
            "conversation_id", conversation_id
        ).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        messages = (response.data or [])[::-1]

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
    """Send a message in a conversation"""
    try:
        user_id = request.user_id
        data = request.json
        content = data.get("content", "").strip()

        if not content or len(content) < 1:
            return jsonify({"error": "Message content required"}), 400
        if len(content) > 2000:
            return jsonify({"error": "Message too long"}), 400

        conv = supabase.table("dm_conversations").select("user1_id, user2_id").eq(
            "id", conversation_id
        ).single().execute()

        if not conv.data:
            return jsonify({"error": "Conversation not found"}), 404

        if user_id not in [conv.data["user1_id"], conv.data["user2_id"]]:
            return jsonify({"error": "Not authorized"}), 403

        response = supabase.table("dm_messages").insert({
            "conversation_id": conversation_id,
            "sender_id": user_id,
            "content": content
        }).execute()

        if not response.data:
            return jsonify({"error": "Failed to send message"}), 500

        return jsonify({"message": "Message sent", "dm": response.data[0]}), 201

    except Exception as e:
        debug_log(f"Send message error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/dm/unread-count", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_unread_dm_count():
    """Get total unread message count for user"""
    try:
        user_id = request.user_id

        convs = supabase.table("dm_conversations").select("id").or_(
            f"user1_id.eq.{user_id},user2_id.eq.{user_id}"
        ).execute()

        conv_ids = [c["id"] for c in (convs.data or [])]

        if not conv_ids:
            return jsonify({"unread_count": 0}), 200

        unread = supabase.table("dm_messages").select("id", count="exact").in_(
            "conversation_id", conv_ids
        ).eq("is_read", False).neq("sender_id", user_id).execute()

        return jsonify({"unread_count": unread.count or 0}), 200

    except Exception as e:
        debug_log(f"Get unread count error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================

'''

def insert_routes():
    """Insert social media routes into app.py"""

    # Read current app.py content
    with open(app_py_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if routes already added
    if "# ============= SOCIAL MEDIA API =============" in content:
        print("Social media routes already exist in app.py!")
        return False

    # Find the if __name__ == "__main__": line
    if_main_pattern = 'if __name__ == "__main__":'

    if if_main_pattern not in content:
        print("ERROR: Could not find 'if __name__ == \"__main__\":' in app.py")
        return False

    # Insert routes before if __name__
    updated_content = content.replace(if_main_pattern, SOCIAL_ROUTES + '\n' + if_main_pattern)

    # Write updated content back
    with open(app_py_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print("Successfully added social media routes to app.py!")
    print("\nRoutes added:")
    print("  POSTS & FEED:")
    print("    - GET    /api/social/feed")
    print("    - GET    /api/social/posts/trending")
    print("    - POST   /api/social/posts")
    print("    - GET    /api/social/posts/<id>")
    print("    - POST   /api/social/posts/<id>/vote")
    print("    - POST   /api/social/posts/<id>/bookmark")
    print("    - DELETE /api/social/posts/<id>")
    print("    - GET    /api/social/bookmarks")
    print("\n  COMMENTS:")
    print("    - GET    /api/social/posts/<id>/comments")
    print("    - POST   /api/social/posts/<id>/comments")
    print("    - GET    /api/social/comments/<id>/replies")
    print("    - DELETE /api/social/comments/<id>")
    print("    - POST   /api/social/comments/<id>/vote")
    print("\n  PROFILES & FOLLOWERS:")
    print("    - GET    /api/social/profile/<username>")
    print("    - PATCH  /api/social/profile")
    print("    - POST   /api/social/follow/<username>")
    print("    - POST   /api/social/unfollow/<username>")
    print("    - GET    /api/social/search/users")
    print("\n  DIRECT MESSAGES:")
    print("    - GET    /api/social/dm/conversations")
    print("    - GET    /api/social/dm/conversation/<username>")
    print("    - GET    /api/social/dm/conversation/<id>/messages")
    print("    - POST   /api/social/dm/conversation/<id>/send")
    print("    - GET    /api/social/dm/unread-count")
    return True

if __name__ == "__main__":
    insert_routes()
