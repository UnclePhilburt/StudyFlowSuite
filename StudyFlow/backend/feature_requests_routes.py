"""
Feature Requests API Routes for StudyFlow Suite

These routes should be added to app.py before the `if __name__ == "__main__":` line.
"""

# ============= FEATURE REQUESTS API =============
# ADD THESE ROUTES TO app.py


# @app.route("/api/feature-requests", methods=["GET"])
# @supabase_auth_required
# @account_not_frozen
def get_feature_requests_route(app, supabase, get_cached_profile, debug_log, traceback, request, jsonify):
    """Get all feature requests with vote status for current user"""
    @app.route("/api/feature-requests", methods=["GET"])
    @supabase_auth_required
    @account_not_frozen
    def get_feature_requests():
        try:
            user_id = request.user_id

            # Get filter and sort parameters
            status_filter = request.args.get("status", "all")  # all, pending, in-progress, completed
            sort_by = request.args.get("sort", "popular")  # popular, recent, status

            # Build base query
            query = supabase.table("feature_requests").select(
                "id, user_id, username, title, description, status, vote_count, "
                "admin_response, completed_at, created_at, updated_at"
            )

            # Apply status filter
            if status_filter != "all":
                query = query.eq("status", status_filter)

            # Apply sorting
            if sort_by == "popular":
                query = query.order("vote_count", desc=True).order("created_at", desc=True)
            elif sort_by == "recent":
                query = query.order("created_at", desc=True)
            elif sort_by == "status":
                # Custom sort: in-progress, pending, reviewing, completed, rejected
                query = query.order("status").order("created_at", desc=True)

            # Execute query
            response = query.execute()
            requests_data = response.data or []

            # Get user's votes to mark which requests they've voted for
            votes_response = supabase.table("feature_request_votes").select(
                "request_id"
            ).eq("user_id", user_id).execute()

            user_voted_ids = {v["request_id"] for v in (votes_response.data or [])}

            # Add has_voted flag to each request
            for req in requests_data:
                req["has_voted"] = req["id"] in user_voted_ids
                req["is_owner"] = req["user_id"] == user_id

            return jsonify({
                "requests": requests_data,
                "total": len(requests_data)
            }), 200

        except Exception as e:
            debug_log(f"Get feature requests error: {e}\n{traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500


# To integrate into app.py, copy the code below and paste it before `if __name__ == "__main__"`":

INTEGRATION_CODE = """

# ============= FEATURE REQUESTS API =============

@app.route("/api/feature-requests", methods=["GET"])
@supabase_auth_required
@account_not_frozen
def get_feature_requests():
    \"\"\"Get all feature requests with vote status for current user\"\"\"
    try:
        user_id = request.user_id

        # Get filter and sort parameters
        status_filter = request.args.get("status", "all")
        sort_by = request.args.get("sort", "popular")

        # Build base query
        query = supabase.table("feature_requests").select(
            "id, user_id, username, title, description, status, vote_count, "
            "admin_response, completed_at, created_at, updated_at"
        )

        # Apply status filter
        if status_filter != "all":
            query = query.eq("status", status_filter)

        # Apply sorting
        if sort_by == "popular":
            query = query.order("vote_count", desc=True).order("created_at", desc=True)
        elif sort_by == "recent":
            query = query.order("created_at", desc=True)
        elif sort_by == "status":
            query = query.order("status").order("created_at", desc=True)

        # Execute query
        response = query.execute()
        requests_data = response.data or []

        # Get user's votes
        votes_response = supabase.table("feature_request_votes").select(
            "request_id"
        ).eq("user_id", user_id).execute()

        user_voted_ids = {v["request_id"] for v in (votes_response.data or [])}

        # Add flags to each request
        for req in requests_data:
            req["has_voted"] = req["id"] in user_voted_ids
            req["is_owner"] = req["user_id"] == user_id

        return jsonify({"requests": requests_data, "total": len(requests_data)}), 200

    except Exception as e:
        debug_log(f"Get feature requests error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/feature-requests", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def create_feature_request():
    \"\"\"Submit a new feature request\"\"\"
    try:
        user_id = request.user_id
        data = request.json

        title = data.get("title", "").strip()
        description = data.get("description", "").strip()

        # Validation
        if not title or len(title) < 5:
            return jsonify({"error": "Title must be at least 5 characters"}), 400
        if len(title) > 200:
            return jsonify({"error": "Title must be less than 200 characters"}), 400
        if not description or len(description) < 10:
            return jsonify({"error": "Description must be at least 10 characters"}), 400
        if len(description) > 2000:
            return jsonify({"error": "Description must be less than 2000 characters"}), 400

        # Get username
        profile = get_cached_profile(user_id)
        username = profile.get("username", "Anonymous") if profile else "Anonymous"

        # Create feature request
        response = supabase.table("feature_requests").insert({
            "user_id": user_id,
            "username": username,
            "title": title,
            "description": description,
            "status": "pending",
            "vote_count": 0
        }).execute()

        if not response.data:
            return jsonify({"error": "Failed to create feature request"}), 500

        created_request = response.data[0]
        created_request["has_voted"] = False
        created_request["is_owner"] = True

        debug_log(f"Feature request created: {created_request['id']} by user {user_id}")

        return jsonify({
            "message": "Feature request submitted successfully",
            "request": created_request
        }), 201

    except Exception as e:
        debug_log(f"Create feature request error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/feature-requests/<request_id>/vote", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def toggle_vote_feature_request(request_id):
    \"\"\"Toggle vote for a feature request\"\"\"
    try:
        user_id = request.user_id

        # Check if user already voted
        existing_vote = supabase.table("feature_request_votes").select(
            "id"
        ).eq("user_id", user_id).eq("request_id", request_id).execute()

        if existing_vote.data:
            # Remove vote
            vote_id = existing_vote.data[0]["id"]
            supabase.table("feature_request_votes").delete().eq("id", vote_id).execute()
            action = "removed"
        else:
            # Add vote
            supabase.table("feature_request_votes").insert({
                "user_id": user_id,
                "request_id": request_id
            }).execute()
            action = "added"

        # Get updated request
        updated_request = supabase.table("feature_requests").select(
            "id, vote_count"
        ).eq("id", request_id).single().execute()

        debug_log(f"Vote {action} for request {request_id} by user {user_id}")

        return jsonify({
            "message": f"Vote {action}",
            "vote_count": updated_request.data.get("vote_count", 0) if updated_request.data else 0,
            "has_voted": action == "added"
        }), 200

    except Exception as e:
        debug_log(f"Toggle vote error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/feature-requests/<request_id>", methods=["PATCH"])
@supabase_auth_required
@account_not_frozen
def update_feature_request(request_id):
    \"\"\"Update a feature request (users can update their own)\"\"\"
    try:
        user_id = request.user_id
        data = request.json

        # Get existing request
        existing = supabase.table("feature_requests").select(
            "user_id"
        ).eq("id", request_id).single().execute()

        if not existing.data:
            return jsonify({"error": "Feature request not found"}), 404

        # Check ownership
        if existing.data["user_id"] != user_id:
            return jsonify({"error": "You can only update your own feature requests"}), 403

        # Users can only update title and description
        update_data = {}
        if "title" in data:
            title = data["title"].strip()
            if len(title) < 5 or len(title) > 200:
                return jsonify({"error": "Title must be 5-200 characters"}), 400
            update_data["title"] = title

        if "description" in data:
            description = data["description"].strip()
            if len(description) < 10 or len(description) > 2000:
                return jsonify({"error": "Description must be 10-2000 characters"}), 400
            update_data["description"] = description

        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        # Update
        response = supabase.table("feature_requests").update(update_data).eq(
            "id", request_id
        ).execute()

        debug_log(f"Feature request {request_id} updated by user {user_id}")

        return jsonify({
            "message": "Feature request updated",
            "request": response.data[0] if response.data else {}
        }), 200

    except Exception as e:
        debug_log(f"Update feature request error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/feature-requests/<request_id>", methods=["PATCH"])
@supabase_auth_required
@account_not_frozen
def admin_update_feature_request(request_id):
    \"\"\"Admin endpoint to update feature request status and response\"\"\"
    try:
        user_id = request.user_id
        data = request.json

        # TODO: Add proper admin role check here
        # For now, this endpoint works but should be restricted to admins only

        update_data = {}

        if "status" in data:
            valid_statuses = ["pending", "reviewing", "in-progress", "completed", "rejected"]
            if data["status"] not in valid_statuses:
                return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400
            update_data["status"] = data["status"]

        if "admin_response" in data:
            update_data["admin_response"] = data["admin_response"]

        if not update_data:
            return jsonify({"error": "No fields to update"}), 400

        # Update
        response = supabase.table("feature_requests").update(update_data).eq(
            "id", request_id
        ).execute()

        if not response.data:
            return jsonify({"error": "Feature request not found"}), 404

        debug_log(f"Admin updated feature request {request_id}: {update_data}")

        return jsonify({
            "message": "Feature request updated by admin",
            "request": response.data[0]
        }), 200

    except Exception as e:
        debug_log(f"Admin update error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/feature-requests/<request_id>", methods=["DELETE"])
@supabase_auth_required
@account_not_frozen
def delete_feature_request(request_id):
    \"\"\"Delete a feature request (owner only)\"\"\"
    try:
        user_id = request.user_id

        # Get existing request
        existing = supabase.table("feature_requests").select(
            "user_id"
        ).eq("id", request_id).single().execute()

        if not existing.data:
            return jsonify({"error": "Feature request not found"}), 404

        # Check ownership
        if existing.data["user_id"] != user_id:
            return jsonify({"error": "You can only delete your own feature requests"}), 403

        # Delete (votes cascade)
        supabase.table("feature_requests").delete().eq("id", request_id).execute()

        debug_log(f"Feature request {request_id} deleted by user {user_id}")

        return jsonify({"message": "Feature request deleted"}), 200

    except Exception as e:
        debug_log(f"Delete feature request error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# =================================================
"""
