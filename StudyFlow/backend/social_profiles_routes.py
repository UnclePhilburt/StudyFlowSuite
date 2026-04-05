"""
Social Media Profiles & Followers API Routes
User profiles with bio, avatar, banner, followers
"""

PROFILES_ROUTES = """

# ============= USER PROFILES & FOLLOWERS API =============

@app.route("/api/social/profile/<username>", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_user_profile(username):
    \"\"\"Get public user profile\"\"\"
    try:
        current_user_id = request.user_id

        # Get user profile
        profile = supabase.table("user_profiles").select(
            "id, username, display_name, bio, avatar_url, banner_url, "
            "follower_count, following_count, post_count, is_public, created_at"
        ).eq("username", username).single().execute()

        if not profile.data:
            return jsonify({"error": "User not found"}), 404

        profile_data = profile.data
        profile_user_id = profile_data["id"]

        # Check if current user follows this profile
        follow = supabase.table("user_followers").select("id").eq(
            "follower_id", current_user_id
        ).eq("following_id", profile_user_id).execute()

        profile_data["is_following"] = bool(follow.data)
        profile_data["is_own_profile"] = current_user_id == profile_user_id

        # Get user's posts
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
    \"\"\"Update own profile (bio, display name, avatar, banner)\"\"\"
    try:
        user_id = request.user_id
        data = request.json

        update_data = {}

        if "bio" in data:
            bio = data["bio"].strip() if data["bio"] else None
            if bio and len(bio) > 500:
                return jsonify({"error": "Bio too long (max 500 characters)"}), 400
            update_data["bio"] = bio

        if "display_name" in data:
            display_name = data["display_name"].strip() if data["display_name"] else None
            if display_name and len(display_name) > 50:
                return jsonify({"error": "Display name too long (max 50 characters)"}), 400
            update_data["display_name"] = display_name

        if "avatar_url" in data:
            update_data["avatar_url"] = data["avatar_url"]

        if "banner_url" in data:
            update_data["banner_url"] = data["banner_url"]

        if not update_data:
            return jsonify({"error": "No fields to update"}), 400

        response = supabase.table("user_profiles").update(update_data).eq("id", user_id).execute()

        debug_log(f"Profile updated for user {user_id}")

        return jsonify({"message": "Profile updated", "profile": response.data[0]}), 200

    except Exception as e:
        debug_log(f"Update profile error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/follow/<username>", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def follow_user(username):
    \"\"\"Follow a user\"\"\"
    try:
        follower_id = request.user_id

        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        following_id = target.data["id"]

        if follower_id == following_id:
            return jsonify({"error": "Cannot follow yourself"}), 400

        # Check if already following
        existing = supabase.table("user_followers").select("id").eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()

        if existing.data:
            return jsonify({"message": "Already following", "is_following": True}), 200

        # Create follow
        supabase.table("user_followers").insert({
            "follower_id": follower_id,
            "following_id": following_id
        }).execute()

        debug_log(f"User {follower_id} followed {following_id}")

        return jsonify({"message": "Followed successfully", "is_following": True}), 201

    except Exception as e:
        debug_log(f"Follow error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/unfollow/<username>", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def unfollow_user(username):
    \"\"\"Unfollow a user\"\"\"
    try:
        follower_id = request.user_id

        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        following_id = target.data["id"]

        # Delete follow
        result = supabase.table("user_followers").delete().eq(
            "follower_id", follower_id
        ).eq("following_id", following_id).execute()

        if not result.data:
            return jsonify({"message": "Not following", "is_following": False}), 200

        debug_log(f"User {follower_id} unfollowed {following_id}")

        return jsonify({"message": "Unfollowed successfully", "is_following": False}), 200

    except Exception as e:
        debug_log(f"Unfollow error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/profile/<username>/followers", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_user_followers(username):
    \"\"\"Get list of users who follow this user\"\"\"
    try:
        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        user_id = target.data["id"]

        # Get followers
        response = supabase.table("user_followers").select(
            "created_at, user_profiles!follower_id(id, username, display_name, avatar_url, bio)"
        ).eq("following_id", user_id).order("created_at", desc=True).execute()

        followers = []
        for f in (response.data or []):
            if f.get("user_profiles"):
                follower_data = f["user_profiles"]
                follower_data["followed_at"] = f["created_at"]
                followers.append(follower_data)

        return jsonify({"followers": followers}), 200

    except Exception as e:
        debug_log(f"Get followers error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/profile/<username>/following", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_user_following(username):
    \"\"\"Get list of users this user follows\"\"\"
    try:
        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        user_id = target.data["id"]

        # Get following
        response = supabase.table("user_followers").select(
            "created_at, user_profiles!following_id(id, username, display_name, avatar_url, bio)"
        ).eq("follower_id", user_id).order("created_at", desc=True).execute()

        following = []
        for f in (response.data or []):
            if f.get("user_profiles"):
                following_data = f["user_profiles"]
                following_data["followed_at"] = f["created_at"]
                following.append(following_data)

        return jsonify({"following": following}), 200

    except Exception as e:
        debug_log(f"Get following error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/profile/<username>/posts", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_user_posts(username):
    \"\"\"Get all posts by a user (for profile page grid)\"\"\"
    try:
        current_user_id = request.user_id
        page = int(request.args.get("page", 1))
        per_page = 20
        offset = (page - 1) * per_page

        # Get target user
        target = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not target.data:
            return jsonify({"error": "User not found"}), 404

        user_id = target.data["id"]

        # Get posts
        response = supabase.table("social_posts").select(
            "*, notes(original_filename, thumbnail_url, file_type)"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(per_page).offset(offset).execute()

        posts = response.data or []

        # Add vote and bookmark status for current user
        if posts:
            post_ids = [p["id"] for p in posts]

            votes = supabase.table("post_votes").select("post_id, vote_type").eq(
                "user_id", current_user_id
            ).in_("post_id", post_ids).execute()
            votes_map = {v["post_id"]: v["vote_type"] for v in (votes.data or [])}

            bookmarks = supabase.table("post_bookmarks").select("post_id").eq(
                "user_id", current_user_id
            ).in_("post_id", post_ids).execute()
            bookmark_ids = {b["post_id"] for b in (bookmarks.data or [])}

            for post in posts:
                post["user_vote_type"] = votes_map.get(post["id"])
                post["is_bookmarked"] = post["id"] in bookmark_ids

        return jsonify({"posts": posts, "page": page}), 200

    except Exception as e:
        debug_log(f"Get user posts error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/search/users", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def search_users():
    \"\"\"Search for users by username or display name\"\"\"
    try:
        query = request.args.get("q", "").strip()

        if not query or len(query) < 2:
            return jsonify({"error": "Search query must be at least 2 characters"}), 400

        # Search users
        response = supabase.table("user_profiles").select(
            "id, username, display_name, avatar_url, bio, follower_count"
        ).or_(f"username.ilike.%{query}%,display_name.ilike.%{query}%").limit(20).execute()

        users = response.data or []

        return jsonify({"users": users}), 200

    except Exception as e:
        debug_log(f"Search users error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""
