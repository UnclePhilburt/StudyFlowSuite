-- Social Media System for StudyFlow Suite
-- Instagram/Reddit hybrid for sharing and discovering notes
-- Visual feed with upvote/downvote, comments, followers, DMs

-- ============= USER PROFILES & SOCIAL INFO =============

-- Extend user profiles with social features
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS bio TEXT CHECK (char_length(bio) <= 500);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;  -- Profile picture
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS banner_url TEXT;  -- Banner/cover photo
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS display_name TEXT CHECK (char_length(display_name) <= 50);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS follower_count INTEGER DEFAULT 0;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS following_count INTEGER DEFAULT 0;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS post_count INTEGER DEFAULT 0;

-- ============= POSTS =============

-- Social posts (can be note shares, text posts, or study group invites)
CREATE TABLE social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT,  -- Cached for display
    post_type TEXT NOT NULL CHECK (post_type IN ('note', 'text', 'group_invite')),

    -- Content fields (type-specific)
    note_id UUID REFERENCES notes(id) ON DELETE CASCADE,  -- For note posts
    text_content TEXT,  -- For text posts or captions
    group_id UUID REFERENCES study_groups(id) ON DELETE CASCADE,  -- For group invites

    -- Engagement counters
    upvote_count INTEGER DEFAULT 0,
    downvote_count INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,  -- upvotes - downvotes (for sorting)
    comment_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- At least one content field must be set
    CONSTRAINT post_has_content CHECK (
        (post_type = 'note' AND note_id IS NOT NULL) OR
        (post_type = 'text' AND text_content IS NOT NULL) OR
        (post_type = 'group_invite' AND group_id IS NOT NULL)
    )
);

CREATE INDEX idx_posts_user ON social_posts (user_id, created_at DESC);
CREATE INDEX idx_posts_type ON social_posts (post_type, created_at DESC);
CREATE INDEX idx_posts_score ON social_posts (score DESC, created_at DESC);
CREATE INDEX idx_posts_note ON social_posts (note_id);

-- ============= POST VOTES =============

-- Upvote/downvote on posts
CREATE TABLE post_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    vote_type TEXT NOT NULL CHECK (vote_type IN ('upvote', 'downvote')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, post_id)  -- One vote per user per post
);

CREATE INDEX idx_post_votes_post ON post_votes (post_id, vote_type);
CREATE INDEX idx_post_votes_user ON post_votes (user_id);

-- Trigger to update post vote counts
CREATE OR REPLACE FUNCTION update_post_vote_counts()
RETURNS TRIGGER AS $$
DECLARE
    old_vote TEXT;
    new_upvotes INT;
    new_downvotes INT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New vote
        IF NEW.vote_type = 'upvote' THEN
            UPDATE social_posts SET upvote_count = upvote_count + 1, score = score + 1 WHERE id = NEW.post_id;
        ELSE
            UPDATE social_posts SET downvote_count = downvote_count + 1, score = score - 1 WHERE id = NEW.post_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        -- Changed vote
        IF OLD.vote_type = 'upvote' AND NEW.vote_type = 'downvote' THEN
            UPDATE social_posts SET upvote_count = upvote_count - 1, downvote_count = downvote_count + 1, score = score - 2 WHERE id = NEW.post_id;
        ELSIF OLD.vote_type = 'downvote' AND NEW.vote_type = 'upvote' THEN
            UPDATE social_posts SET upvote_count = upvote_count + 1, downvote_count = downvote_count - 1, score = score + 2 WHERE id = NEW.post_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        -- Removed vote
        IF OLD.vote_type = 'upvote' THEN
            UPDATE social_posts SET upvote_count = upvote_count - 1, score = score - 1 WHERE id = OLD.post_id;
        ELSE
            UPDATE social_posts SET downvote_count = downvote_count - 1, score = score + 1 WHERE id = OLD.post_id;
        END IF;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_post_votes
    AFTER INSERT OR UPDATE OR DELETE ON post_votes
    FOR EACH ROW
    EXECUTE FUNCTION update_post_vote_counts();

-- ============= COMMENTS =============

-- Comments on posts (threaded with parent_id)
CREATE TABLE post_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT,  -- Cached
    parent_id UUID REFERENCES post_comments(id) ON DELETE CASCADE,  -- For replies
    content TEXT NOT NULL CHECK (char_length(content) >= 1 AND char_length(content) <= 2000),
    upvote_count INTEGER DEFAULT 0,
    downvote_count INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_comments_post ON post_comments (post_id, score DESC, created_at DESC);
CREATE INDEX idx_comments_user ON post_comments (user_id, created_at DESC);
CREATE INDEX idx_comments_parent ON post_comments (parent_id, created_at ASC);

-- Trigger to update post comment count
CREATE OR REPLACE FUNCTION update_post_comment_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE social_posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
        -- If it's a reply, update parent comment reply count
        IF NEW.parent_id IS NOT NULL THEN
            UPDATE post_comments SET reply_count = reply_count + 1 WHERE id = NEW.parent_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE social_posts SET comment_count = comment_count - 1 WHERE id = OLD.post_id;
        IF OLD.parent_id IS NOT NULL THEN
            UPDATE post_comments SET reply_count = reply_count - 1 WHERE id = OLD.parent_id;
        END IF;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_post_comment_count
    AFTER INSERT OR DELETE ON post_comments
    FOR EACH ROW
    EXECUTE FUNCTION update_post_comment_count();

-- ============= COMMENT VOTES =============

-- Votes on comments
CREATE TABLE comment_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    comment_id UUID NOT NULL REFERENCES post_comments(id) ON DELETE CASCADE,
    vote_type TEXT NOT NULL CHECK (vote_type IN ('upvote', 'downvote')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, comment_id)
);

CREATE INDEX idx_comment_votes_comment ON comment_votes (comment_id);
CREATE INDEX idx_comment_votes_user ON comment_votes (user_id);

-- Trigger to update comment vote counts
CREATE OR REPLACE FUNCTION update_comment_vote_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.vote_type = 'upvote' THEN
            UPDATE post_comments SET upvote_count = upvote_count + 1, score = score + 1 WHERE id = NEW.comment_id;
        ELSE
            UPDATE post_comments SET downvote_count = downvote_count + 1, score = score - 1 WHERE id = NEW.comment_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.vote_type = 'upvote' AND NEW.vote_type = 'downvote' THEN
            UPDATE post_comments SET upvote_count = upvote_count - 1, downvote_count = downvote_count + 1, score = score - 2 WHERE id = NEW.comment_id;
        ELSIF OLD.vote_type = 'downvote' AND NEW.vote_type = 'upvote' THEN
            UPDATE post_comments SET upvote_count = upvote_count + 1, downvote_count = downvote_count - 1, score = score + 2 WHERE id = NEW.comment_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        IF OLD.vote_type = 'upvote' THEN
            UPDATE post_comments SET upvote_count = upvote_count - 1, score = score - 1 WHERE id = OLD.comment_id;
        ELSE
            UPDATE post_comments SET downvote_count = downvote_count - 1, score = score + 1 WHERE id = OLD.comment_id;
        END IF;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_comment_votes
    AFTER INSERT OR UPDATE OR DELETE ON comment_votes
    FOR EACH ROW
    EXECUTE FUNCTION update_comment_vote_counts();

-- ============= FOLLOWERS =============

-- Follower relationships
CREATE TABLE user_followers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    follower_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,  -- User who follows
    following_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,  -- User being followed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(follower_id, following_id),
    CHECK (follower_id != following_id)  -- Can't follow yourself
);

CREATE INDEX idx_followers_following ON user_followers (following_id, created_at DESC);
CREATE INDEX idx_followers_follower ON user_followers (follower_id, created_at DESC);

-- Trigger to update follower counts
CREATE OR REPLACE FUNCTION update_follower_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE user_profiles SET follower_count = follower_count + 1 WHERE id = NEW.following_id;
        UPDATE user_profiles SET following_count = following_count + 1 WHERE id = NEW.follower_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE user_profiles SET follower_count = follower_count - 1 WHERE id = OLD.following_id;
        UPDATE user_profiles SET following_count = following_count - 1 WHERE id = OLD.follower_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_follower_counts
    AFTER INSERT OR DELETE ON user_followers
    FOR EACH ROW
    EXECUTE FUNCTION update_follower_counts();

-- ============= BOOKMARKS =============

-- Saved/bookmarked posts
CREATE TABLE post_bookmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, post_id)
);

CREATE INDEX idx_bookmarks_user ON post_bookmarks (user_id, created_at DESC);

-- ============= DIRECT MESSAGES =============

-- DM conversations
CREATE TABLE dm_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user1_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    user2_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user1_id, user2_id),
    CHECK (user1_id < user2_id)  -- Ensure consistent ordering
);

CREATE INDEX idx_dm_conversations_user1 ON dm_conversations (user1_id, last_message_at DESC);
CREATE INDEX idx_dm_conversations_user2 ON dm_conversations (user2_id, last_message_at DESC);

-- DM messages
CREATE TABLE dm_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES dm_conversations(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    content TEXT NOT NULL CHECK (char_length(content) >= 1 AND char_length(content) <= 2000),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dm_messages_conversation ON dm_messages (conversation_id, created_at DESC);
CREATE INDEX idx_dm_messages_sender ON dm_messages (sender_id, created_at DESC);

-- Trigger to update last_message_at
CREATE OR REPLACE FUNCTION update_dm_last_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE dm_conversations SET last_message_at = NEW.created_at WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_dm_last_message
    AFTER INSERT ON dm_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_dm_last_message();

-- ============= ROW LEVEL SECURITY =============

-- Social posts
ALTER TABLE social_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view posts"
    ON social_posts FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Users can create own posts"
    ON social_posts FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own posts"
    ON social_posts FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own posts"
    ON social_posts FOR DELETE
    USING (auth.uid() = user_id);

-- Post votes
ALTER TABLE post_votes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view votes"
    ON post_votes FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Users can manage own votes"
    ON post_votes FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Comments
ALTER TABLE post_comments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view comments"
    ON post_comments FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Users can create comments"
    ON post_comments FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own comments"
    ON post_comments FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own comments"
    ON post_comments FOR DELETE
    USING (auth.uid() = user_id);

-- Comment votes
ALTER TABLE comment_votes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view comment votes"
    ON comment_votes FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Users can manage own comment votes"
    ON comment_votes FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Followers
ALTER TABLE user_followers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view followers"
    ON user_followers FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Users can manage own follows"
    ON user_followers FOR ALL
    USING (auth.uid() = follower_id)
    WITH CHECK (auth.uid() = follower_id);

-- Bookmarks
ALTER TABLE post_bookmarks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own bookmarks"
    ON post_bookmarks FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own bookmarks"
    ON post_bookmarks FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- DM conversations
ALTER TABLE dm_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own conversations"
    ON dm_conversations FOR SELECT
    USING (auth.uid() = user1_id OR auth.uid() = user2_id);

CREATE POLICY "Users can create conversations"
    ON dm_conversations FOR INSERT
    WITH CHECK (auth.uid() = user1_id OR auth.uid() = user2_id);

-- DM messages
ALTER TABLE dm_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view messages in their conversations"
    ON dm_messages FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM dm_conversations
            WHERE id = conversation_id
            AND (user1_id = auth.uid() OR user2_id = auth.uid())
        )
    );

CREATE POLICY "Users can send messages"
    ON dm_messages FOR INSERT
    WITH CHECK (
        auth.uid() = sender_id
        AND EXISTS (
            SELECT 1 FROM dm_conversations
            WHERE id = conversation_id
            AND (user1_id = auth.uid() OR user2_id = auth.uid())
        )
    );

CREATE POLICY "Users can update own messages"
    ON dm_messages FOR UPDATE
    USING (auth.uid() = sender_id);
