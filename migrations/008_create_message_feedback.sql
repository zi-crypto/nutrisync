-- Migration: 008_create_message_feedback.sql
-- Description: Creates the message_feedback table for per-message like/dislike feedback with required comments.

-- 1. Create the table
CREATE TABLE IF NOT EXISTS public.message_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES public.chat_history(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    feedback_value SMALLINT NOT NULL CHECK (feedback_value IN (1, -1)),
    feedback_comment TEXT NOT NULL CHECK (char_length(feedback_comment) >= 10),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (message_id, user_id)
);

-- 2. Index for analytics queries (time-range, per-user, per-message)
CREATE INDEX IF NOT EXISTS idx_message_feedback_created_at ON public.message_feedback (created_at);
CREATE INDEX IF NOT EXISTS idx_message_feedback_user_id ON public.message_feedback (user_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_message_id ON public.message_feedback (message_id);

-- 3. Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_message_feedback_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_message_feedback_updated_at ON public.message_feedback;
CREATE TRIGGER trg_message_feedback_updated_at
    BEFORE UPDATE ON public.message_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_message_feedback_updated_at();

-- 4. Enable RLS
ALTER TABLE public.message_feedback ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies
DROP POLICY IF EXISTS "Users can view their own feedback" ON public.message_feedback;
CREATE POLICY "Users can view their own feedback" ON public.message_feedback
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own feedback" ON public.message_feedback;
CREATE POLICY "Users can insert their own feedback" ON public.message_feedback
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own feedback" ON public.message_feedback;
CREATE POLICY "Users can update their own feedback" ON public.message_feedback
    FOR UPDATE USING (auth.uid() = user_id);

-- 6. Grant access to service role (for backend API calls)
GRANT ALL ON public.message_feedback TO service_role;
GRANT ALL ON public.message_feedback TO authenticated;
