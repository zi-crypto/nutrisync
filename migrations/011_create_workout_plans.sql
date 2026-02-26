-- Migration: 011_create_workout_plans.sql
-- Description: Creates tables for AI-generated workout plans and set-level exercise logging.
--   - workout_plan_exercises: stores the AI-prescribed plan per split day
--   - exercise_logs: stores actual set-by-set performance for progressive overload tracking
--
-- References:
--   Schoenfeld's dose-response volume landmarks (MEV / MAV / MRV)
--   RP Strength volume recommendations per muscle group
--   Industry patterns from Strong, Hevy, JEFIT (plan vs. log separation)

BEGIN;

-- ============================================================================
-- 1. WORKOUT PLAN EXERCISES (The Prescription)
--    Stores what the AI recommends for each day in the user's active split.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.workout_plan_exercises (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    split_id        uuid NOT NULL REFERENCES public.workout_splits(id) ON DELETE CASCADE,
    split_day_name  text NOT NULL,           -- e.g. 'Push', 'Pull', 'Legs'
    exercise_order  int NOT NULL,            -- 1-based ordering within the day
    exercise_name   text NOT NULL,           -- e.g. 'Barbell Bench Press'
    exercise_type   text NOT NULL CHECK (exercise_type IN ('compound', 'isolation')),
    target_muscles  text[] NOT NULL,         -- e.g. ARRAY['chest','front_delts','triceps']
    sets            int NOT NULL,            -- prescribed number of sets (e.g. 4)
    rep_range_low   int NOT NULL,            -- low end of rep range (e.g. 6)
    rep_range_high  int NOT NULL,            -- high end of rep range (e.g. 12)
    load_percentage float,                   -- %1RM if 1RM exists (nullable)
    rest_seconds    int DEFAULT 120,         -- rest between sets in seconds
    superset_group  int,                     -- Exercises with same group # on same day are supersetted (null = standalone)
    notes           text,                    -- e.g. 'Pause at bottom 1 sec', coaching cues
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);

-- Unique constraint: one exercise per order position per day per split per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_wpe_unique_order
    ON public.workout_plan_exercises (user_id, split_id, split_day_name, exercise_order);

-- Fast lookup for a user's full plan
CREATE INDEX IF NOT EXISTS idx_wpe_user_split
    ON public.workout_plan_exercises (user_id, split_id);

-- Fast lookup for a specific day
CREATE INDEX IF NOT EXISTS idx_wpe_user_day
    ON public.workout_plan_exercises (user_id, split_day_name);


-- ============================================================================
-- 2. EXERCISE LOGS (The Actual Performance — Set-Level)
--    Stores what the user actually did: weight × reps × RPE per set.
--    This is the source of truth for progressive overload tracking.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.exercise_logs (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workout_log_id  uuid REFERENCES public.workout_logs(id) ON DELETE CASCADE,  -- Links to parent session
    log_date        date NOT NULL,           -- Functional day (respects 4am cutoff)
    exercise_name   text NOT NULL,           -- e.g. 'Barbell Bench Press'
    set_number      int NOT NULL,            -- 1-based set ordering
    weight_kg       float NOT NULL,          -- Actual weight used
    reps            int NOT NULL,            -- Actual reps completed
    rpe             float CHECK (rpe >= 1 AND rpe <= 10),  -- Rate of Perceived Exertion (optional, 1-10)
    is_warmup       boolean DEFAULT false,   -- Exclude from working volume calculations
    is_pr           boolean DEFAULT false,   -- Auto-flagged if this set is a PR
    volume_load     float GENERATED ALWAYS AS (weight_kg * reps) STORED,  -- Computed: weight × reps
    notes           text,                    -- Per-set notes
    created_at      timestamptz DEFAULT now()
);

-- Primary query pattern: exercise history for a user (progressive overload charts)
CREATE INDEX IF NOT EXISTS idx_exlog_user_exercise_date
    ON public.exercise_logs (user_id, exercise_name, log_date DESC);

-- PR lookups: find heaviest weight or volume for an exercise
CREATE INDEX IF NOT EXISTS idx_exlog_user_exercise_weight
    ON public.exercise_logs (user_id, exercise_name, weight_kg DESC)
    WHERE is_warmup = false;

-- Volume load lookups per date (muscle volume heatmap)
CREATE INDEX IF NOT EXISTS idx_exlog_user_date
    ON public.exercise_logs (user_id, log_date DESC);

-- Link back to session-level workout_logs
CREATE INDEX IF NOT EXISTS idx_exlog_workout_log
    ON public.exercise_logs (workout_log_id)
    WHERE workout_log_id IS NOT NULL;


-- ============================================================================
-- 3. ROW LEVEL SECURITY
-- ============================================================================

-- workout_plan_exercises RLS
ALTER TABLE public.workout_plan_exercises ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own workout plan" ON public.workout_plan_exercises;
CREATE POLICY "Users can view own workout plan" ON public.workout_plan_exercises
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own workout plan" ON public.workout_plan_exercises;
CREATE POLICY "Users can insert own workout plan" ON public.workout_plan_exercises
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own workout plan" ON public.workout_plan_exercises;
CREATE POLICY "Users can update own workout plan" ON public.workout_plan_exercises
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own workout plan" ON public.workout_plan_exercises;
CREATE POLICY "Users can delete own workout plan" ON public.workout_plan_exercises
    FOR DELETE USING (auth.uid() = user_id);

-- exercise_logs RLS
ALTER TABLE public.exercise_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own exercise logs" ON public.exercise_logs;
CREATE POLICY "Users can view own exercise logs" ON public.exercise_logs
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own exercise logs" ON public.exercise_logs;
CREATE POLICY "Users can insert own exercise logs" ON public.exercise_logs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own exercise logs" ON public.exercise_logs;
CREATE POLICY "Users can update own exercise logs" ON public.exercise_logs
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own exercise logs" ON public.exercise_logs;
CREATE POLICY "Users can delete own exercise logs" ON public.exercise_logs
    FOR DELETE USING (auth.uid() = user_id);


-- ============================================================================
-- 4. SERVICE ROLE POLICIES (for backend API operations via service_role key)
--    The backend uses supabase service_role key which bypasses RLS, but these
--    policies are added for completeness / if RLS is enforced on service calls.
-- ============================================================================

-- Allow service role full access to workout_plan_exercises
DROP POLICY IF EXISTS "Service role full access workout_plan_exercises" ON public.workout_plan_exercises;
CREATE POLICY "Service role full access workout_plan_exercises" ON public.workout_plan_exercises
    FOR ALL USING (auth.role() = 'service_role');

-- Allow service role full access to exercise_logs
DROP POLICY IF EXISTS "Service role full access exercise_logs" ON public.exercise_logs;
CREATE POLICY "Service role full access exercise_logs" ON public.exercise_logs
    FOR ALL USING (auth.role() = 'service_role');


-- ============================================================================
-- 5. HELPER FUNCTION: Estimated 1RM (Epley Formula)
--    Used in progressive overload calculations.
--    e1RM = weight × (1 + reps / 30)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.estimated_1rm(p_weight float, p_reps int)
RETURNS float AS $$
BEGIN
    IF p_reps <= 0 THEN RETURN 0; END IF;
    IF p_reps = 1 THEN RETURN p_weight; END IF;
    RETURN ROUND((p_weight * (1.0 + p_reps::float / 30.0))::numeric, 1);
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ============================================================================
-- 6. HELPER FUNCTION: Get progressive overload summary for an exercise
--    Returns weekly e1RM trend, volume trend, and PR data.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_exercise_progress(
    p_user_id uuid,
    p_exercise_name text,
    p_weeks int DEFAULT 8
)
RETURNS TABLE (
    week_start   date,
    best_e1rm    float,
    total_volume float,
    total_sets   int,
    best_weight  float,
    best_reps    int,
    has_pr       boolean
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        date_trunc('week', el.log_date::timestamp)::date AS week_start,
        MAX(public.estimated_1rm(el.weight_kg, el.reps))::float AS best_e1rm,
        SUM(el.volume_load)::float AS total_volume,
        COUNT(*)::int AS total_sets,
        MAX(el.weight_kg)::float AS best_weight,
        MAX(el.reps)::int AS best_reps,
        BOOL_OR(el.is_pr) AS has_pr
    FROM public.exercise_logs el
    WHERE el.user_id = p_user_id
      AND LOWER(el.exercise_name) = LOWER(p_exercise_name)
      AND el.is_warmup = false
      AND el.log_date >= (CURRENT_DATE - (p_weeks * 7))
    GROUP BY date_trunc('week', el.log_date::timestamp)
    ORDER BY week_start ASC;
END;
$$ LANGUAGE plpgsql STABLE;


-- ============================================================================
-- 7. HELPER FUNCTION: Get weekly muscle volume (sets per muscle group)
--    Joins exercise_logs with workout_plan_exercises to map exercises → muscles.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_weekly_muscle_volume(
    p_user_id uuid,
    p_week_offset int DEFAULT 0  -- 0 = current week, -1 = last week, etc.
)
RETURNS TABLE (
    muscle_group text,
    completed_sets bigint
) AS $$
DECLARE
    v_week_start date;
    v_week_end date;
BEGIN
    v_week_start := date_trunc('week', CURRENT_DATE + (p_week_offset * 7))::date;
    v_week_end := v_week_start + 7;

    RETURN QUERY
    SELECT
        UNNEST(wpe.target_muscles) AS muscle_group,
        COUNT(el.id) AS completed_sets
    FROM public.exercise_logs el
    INNER JOIN public.workout_plan_exercises wpe
        ON wpe.user_id = el.user_id
        AND LOWER(wpe.exercise_name) = LOWER(el.exercise_name)
    WHERE el.user_id = p_user_id
      AND el.is_warmup = false
      AND el.log_date >= v_week_start
      AND el.log_date < v_week_end
    GROUP BY UNNEST(wpe.target_muscles)
    ORDER BY completed_sets DESC;
END;
$$ LANGUAGE plpgsql STABLE;


COMMIT;
