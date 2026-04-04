-- Track pomodoro completions
CREATE TABLE IF NOT EXISTS pomodoro_completions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    work_minutes INTEGER NOT NULL,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pomodoro_user ON pomodoro_completions(user_id);
CREATE INDEX IF NOT EXISTS idx_pomodoro_date ON pomodoro_completions(completed_at);
