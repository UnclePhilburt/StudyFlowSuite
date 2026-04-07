-- Badge System for StudyFlow Suite
-- Users earn badges for milestones and can equip up to 3 to display on their profile

-- Badge definitions table
CREATE TABLE badge_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL, -- 'engagement', 'content', 'citation', 'community', 'helpful', 'special'
    icon TEXT NOT NULL, -- emoji or icon identifier
    color TEXT, -- hex color for badge display
    requirement_type TEXT NOT NULL, -- 'upvotes', 'posts', 'citations', 'followers', 'comments', 'manual'
    requirement_value INTEGER, -- threshold to earn badge
    tier INTEGER DEFAULT 1, -- 1=bronze, 2=silver, 3=gold, 4=diamond
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User earned badges
CREATE TABLE user_badges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    badge_id TEXT NOT NULL REFERENCES badge_definitions(id),
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, badge_id)
);

-- User equipped badges (max 3)
CREATE TABLE user_equipped_badges (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    badge_1 TEXT REFERENCES badge_definitions(id),
    badge_2 TEXT REFERENCES badge_definitions(id),
    badge_3 TEXT REFERENCES badge_definitions(id),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_user_badges_user ON user_badges(user_id);
CREATE INDEX idx_user_badges_badge ON user_badges(badge_id);
CREATE INDEX idx_badge_category ON badge_definitions(category);

-- RLS Policies
ALTER TABLE badge_definitions DISABLE ROW LEVEL SECURITY;
ALTER TABLE user_badges DISABLE ROW LEVEL SECURITY;
ALTER TABLE user_equipped_badges DISABLE ROW LEVEL SECURITY;

-- Insert initial badge definitions
INSERT INTO badge_definitions (id, name, description, category, icon, color, requirement_type, requirement_value, tier) VALUES
-- Engagement Badges
('first_upvote', 'First Upvote', 'Received your first upvote', 'engagement', '⬆️', '#8B9D83', 'upvotes', 1, 1),
('rising_star', 'Rising Star', 'Received 10 upvotes', 'engagement', '⭐', '#FFD700', 'upvotes', 10, 2),
('popular', 'Popular', 'Received 50 upvotes', 'engagement', '🌟', '#FFD700', 'upvotes', 50, 3),
('viral', 'Viral', 'Received 100 upvotes', 'engagement', '🔥', '#FF6B35', 'upvotes', 100, 4),
('legendary', 'Legendary', 'Received 500 upvotes', 'engagement', '👑', '#9B59B6', 'upvotes', 500, 4),

-- Content Badges
('first_post', 'First Post', 'Uploaded your first note', 'content', '📝', '#8B9D83', 'posts', 1, 1),
('contributor', 'Contributor', 'Uploaded 10 notes', 'content', '📚', '#3498DB', 'posts', 10, 2),
('prolific', 'Prolific', 'Uploaded 50 notes', 'content', '📖', '#2ECC71', 'posts', 50, 3),
('archive_master', 'Archive Master', 'Uploaded 100 notes', 'content', '🏆', '#E74C3C', 'posts', 100, 4),

-- Citation Badges
('cited_once', 'Cited', 'Your note was cited once', 'citation', '🔗', '#8B9D83', 'citations', 1, 1),
('referenced', 'Referenced', 'Your notes cited 10 times', 'citation', '📎', '#3498DB', 'citations', 10, 2),
('authority', 'Authority', 'Your notes cited 50 times', 'citation', '🎓', '#FFD700', 'citations', 50, 3),
('expert_source', 'Expert Source', 'Your notes cited 100 times', 'citation', '💎', '#9B59B6', 'citations', 100, 4),

-- Community Badges
('first_follower', 'First Follower', 'Got your first follower', 'community', '👥', '#8B9D83', 'followers', 1, 1),
('well_known', 'Well Known', 'Reached 25 followers', 'community', '👨‍🎓', '#3498DB', 'followers', 25, 2),
('influencer', 'Influencer', 'Reached 100 followers', 'community', '📢', '#FFD700', 'followers', 100, 3),
('celebrity', 'Celebrity', 'Reached 500 followers', 'community', '⭐', '#9B59B6', 'followers', 500, 4),

-- Helpful Badges
('helper', 'Helper', 'Made 10 helpful comments', 'helpful', '💬', '#8B9D83', 'comments', 10, 1),
('mentor', 'Mentor', 'Made 50 helpful comments', 'helpful', '🤝', '#3498DB', 'comments', 50, 2),
('professor', 'Professor', 'Made 100 helpful comments', 'helpful', '👨‍🏫', '#FFD700', 'comments', 100, 3),

-- Special Badges
('early_adopter', 'Early Adopter', 'Joined during beta', 'special', '🚀', '#E67E22', 'manual', NULL, 4),
('verified_student', 'Verified Student', 'Verified student status', 'special', '✓', '#27AE60', 'manual', NULL, 3),
('top_contributor', 'Top Contributor', 'Top 1% on leaderboard', 'special', '🏅', '#FFD700', 'manual', NULL, 4);

-- Function to check and grant badges automatically
CREATE OR REPLACE FUNCTION check_and_grant_badges(p_user_id UUID)
RETURNS TABLE(newly_earned_badge_id TEXT, badge_name TEXT) AS $$
DECLARE
    v_upvotes INTEGER;
    v_posts INTEGER;
    v_citations INTEGER;
    v_followers INTEGER;
    v_comments INTEGER;
    v_badge RECORD;
BEGIN
    -- Get user stats
    SELECT
        COALESCE(SUM(upvotes), 0) INTO v_upvotes
    FROM social_posts WHERE user_id = p_user_id;

    SELECT COUNT(*) INTO v_posts
    FROM social_posts WHERE user_id = p_user_id;

    SELECT follower_count INTO v_followers
    FROM user_profiles WHERE id = p_user_id;

    -- Note: citations and comments would need their own queries based on your schema
    v_citations := 0; -- Placeholder
    v_comments := 0; -- Placeholder

    -- Check each badge requirement
    FOR v_badge IN
        SELECT * FROM badge_definitions
        WHERE is_active = TRUE
        AND requirement_type != 'manual'
    LOOP
        -- Check if user already has this badge
        IF NOT EXISTS (SELECT 1 FROM user_badges WHERE user_id = p_user_id AND badge_id = v_badge.id) THEN
            -- Check if requirement is met
            IF (v_badge.requirement_type = 'upvotes' AND v_upvotes >= v_badge.requirement_value) OR
               (v_badge.requirement_type = 'posts' AND v_posts >= v_badge.requirement_value) OR
               (v_badge.requirement_type = 'citations' AND v_citations >= v_badge.requirement_value) OR
               (v_badge.requirement_type = 'followers' AND v_followers >= v_badge.requirement_value) OR
               (v_badge.requirement_type = 'comments' AND v_comments >= v_badge.requirement_value) THEN

                -- Grant badge
                INSERT INTO user_badges (user_id, badge_id)
                VALUES (p_user_id, v_badge.id);

                -- Return the newly earned badge
                newly_earned_badge_id := v_badge.id;
                badge_name := v_badge.name;
                RETURN NEXT;
            END IF;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
