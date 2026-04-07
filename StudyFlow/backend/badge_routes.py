"""
Badge System API Routes
Users earn badges for milestones and can equip up to 3 to display
"""

BADGE_ROUTES = """

# ============= BADGE SYSTEM API =============

@app.route("/api/badges/available", methods=["GET"])
def get_available_badges():
    \"\"\"Get all available badge definitions\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase

        result = supabase.table("badge_definitions").select("*").eq("is_active", True).order("tier").order("requirement_value").execute()

        badges = result.data or []

        return jsonify({"badges": badges}), 200
    except Exception as e:
        debug_log(f"Get available badges error: {e}\\n{traceback.format_exc()}")
        return jsonify({"badges": []}), 200


@app.route("/api/badges/my-badges", methods=["GET"])
@supabase_auth_required
def get_my_badges():
    \"\"\"Get current user's earned badges and equipped badges\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase
        user_id = request.user_id

        # Get earned badges with badge details
        earned = supabase.table("user_badges").select(
            "*, badge_definitions(*)"
        ).eq("user_id", user_id).execute()

        earned_badges = []
        for item in (earned.data or []):
            if item.get("badge_definitions"):
                badge = item["badge_definitions"]
                badge["earned_at"] = item["earned_at"]
                earned_badges.append(badge)

        # Get equipped badges
        equipped = supabase.table("user_equipped_badges").select("*").eq("user_id", user_id).single().execute()

        equipped_ids = []
        if equipped.data:
            if equipped.data.get("badge_1"):
                equipped_ids.append(equipped.data["badge_1"])
            if equipped.data.get("badge_2"):
                equipped_ids.append(equipped.data["badge_2"])
            if equipped.data.get("badge_3"):
                equipped_ids.append(equipped.data["badge_3"])

        return jsonify({
            "earned_badges": earned_badges,
            "equipped_badge_ids": equipped_ids
        }), 200

    except Exception as e:
        debug_log(f"Get my badges error: {e}\\n{traceback.format_exc()}")
        return jsonify({"earned_badges": [], "equipped_badge_ids": []}), 200


@app.route("/api/badges/<username>", methods=["GET"])
@supabase_auth_required
def get_user_badges(username):
    \"\"\"Get a specific user's equipped badges (for display on posts)\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Get user ID from username
        user = supabase.table("user_profiles").select("id").eq("username", username).single().execute()

        if not user.data:
            return jsonify({"badges": []}), 404

        user_id = user.data["id"]

        # Get equipped badges
        equipped = supabase.table("user_equipped_badges").select("*").eq("user_id", user_id).single().execute()

        badge_ids = []
        if equipped.data:
            if equipped.data.get("badge_1"):
                badge_ids.append(equipped.data["badge_1"])
            if equipped.data.get("badge_2"):
                badge_ids.append(equipped.data["badge_2"])
            if equipped.data.get("badge_3"):
                badge_ids.append(equipped.data["badge_3"])

        # Get badge details
        badges = []
        if badge_ids:
            result = supabase.table("badge_definitions").select("*").in_("id", badge_ids).execute()
            badges = result.data or []

        return jsonify({"badges": badges}), 200

    except Exception as e:
        debug_log(f"Get user badges error: {e}\\n{traceback.format_exc()}")
        return jsonify({"badges": []}), 200


@app.route("/api/badges/equip", methods=["POST"])
@supabase_auth_required
def equip_badges():
    \"\"\"Equip up to 3 badges for display\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase
        user_id = request.user_id
        data = request.json or {}

        badge_ids = data.get("badge_ids", [])

        # Validate max 3 badges
        if len(badge_ids) > 3:
            return jsonify({"error": "Maximum 3 badges allowed"}), 400

        # Verify user owns all these badges
        for badge_id in badge_ids:
            if badge_id:  # Skip None/empty values
                owned = supabase.table("user_badges").select("id").eq(
                    "user_id", user_id
                ).eq("badge_id", badge_id).execute()

                if not owned.data:
                    return jsonify({"error": f"You have not earned badge: {badge_id}"}), 403

        # Prepare equipped data
        equipped_data = {
            "badge_1": badge_ids[0] if len(badge_ids) > 0 else None,
            "badge_2": badge_ids[1] if len(badge_ids) > 1 else None,
            "badge_3": badge_ids[2] if len(badge_ids) > 2 else None,
            "updated_at": "now()"
        }

        # Upsert equipped badges
        supabase.table("user_equipped_badges").upsert({
            "user_id": user_id,
            **equipped_data
        }).execute()

        debug_log(f"User {user_id} equipped badges: {badge_ids}")

        return jsonify({"success": True, "equipped_badges": badge_ids}), 200

    except Exception as e:
        debug_log(f"Equip badges error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/badges/check-new", methods=["POST"])
@supabase_auth_required
def check_new_badges():
    \"\"\"Check if user has earned any new badges based on current stats\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase
        user_id = request.user_id

        # Call the database function
        result = supabase.rpc("check_and_grant_badges", {"p_user_id": user_id}).execute()

        newly_earned = result.data or []

        return jsonify({
            "newly_earned": newly_earned,
            "count": len(newly_earned)
        }), 200

    except Exception as e:
        debug_log(f"Check new badges error: {e}\\n{traceback.format_exc()}")
        return jsonify({"newly_earned": [], "count": 0}), 200


@app.route("/api/badges/grant", methods=["POST"])
@supabase_auth_required
def manually_grant_badge():
    \"\"\"Manually grant a badge (admin only - for special badges)\"\"\"
    try:
        from StudyFlow.backend.supabase_client import supabase
        data = request.json or {}

        target_user_id = data.get("user_id")
        badge_id = data.get("badge_id")

        if not target_user_id or not badge_id:
            return jsonify({"error": "user_id and badge_id required"}), 400

        # Check if badge is manual type
        badge = supabase.table("badge_definitions").select("requirement_type").eq("id", badge_id).single().execute()

        if not badge.data or badge.data.get("requirement_type") != "manual":
            return jsonify({"error": "This badge cannot be manually granted"}), 403

        # Grant badge
        supabase.table("user_badges").insert({
            "user_id": target_user_id,
            "badge_id": badge_id
        }).execute()

        debug_log(f"Manually granted badge {badge_id} to user {target_user_id}")

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Manually grant badge error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""
