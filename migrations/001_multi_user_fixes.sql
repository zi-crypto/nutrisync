-- Migration: 001_multi_user_fixes.sql
-- Description: Fixes multi-user scalability issues by enforcing user_id and removing singleton constraints.

-- 1. Add user_id to user_profile if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profile' AND column_name = 'user_id') THEN
        ALTER TABLE user_profile ADD COLUMN user_id UUID REFERENCES auth.users(id);
        -- Optional: specific update for legacy user if needed, otherwise leave null or handle in app
    END IF;
END $$;

-- 2. Add user_id to daily_goals
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'daily_goals' AND column_name = 'user_id') THEN
        ALTER TABLE daily_goals ADD COLUMN user_id UUID REFERENCES auth.users(id);
    END IF;
END $$;

-- 3. Add user_id to persistent_context
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'persistent_context' AND column_name = 'user_id') THEN
        ALTER TABLE persistent_context ADD COLUMN user_id UUID REFERENCES auth.users(id);
    END IF;
END $$;

-- 4. Enable RLS (Row Level Security) on these tables
ALTER TABLE user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE persistent_context ENABLE ROW LEVEL SECURITY;

-- 5. Create Policies (if they don't exist, we drop and recreate to be safe)
DROP POLICY IF EXISTS "Users can view their own profile" ON user_profile;
CREATE POLICY "Users can view their own profile" ON user_profile FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own profile" ON user_profile;
CREATE POLICY "Users can update their own profile" ON user_profile FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own profile" ON user_profile;
CREATE POLICY "Users can insert their own profile" ON user_profile FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view their own daily goals" ON daily_goals;
CREATE POLICY "Users can view their own daily goals" ON daily_goals FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage their own daily goals" ON daily_goals;
CREATE POLICY "Users can manage their own daily goals" ON daily_goals FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view their own context" ON persistent_context;
CREATE POLICY "Users can view their own context" ON persistent_context FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage their own context" ON persistent_context;
CREATE POLICY "Users can manage their own context" ON persistent_context FOR ALL USING (auth.uid() = user_id);

-- 4. Ensure RLS is enabled (Best Practice for Multi-User)
ALTER TABLE public.body_composition_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nutrition_improvement_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nutrition_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.persistent_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scores_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sleep_improvement_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sleep_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.split_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workout_improvement_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workout_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workout_splits ENABLE ROW LEVEL SECURITY;
