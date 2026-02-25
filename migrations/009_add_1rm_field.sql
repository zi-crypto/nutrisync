-- Migration: Add user_1rm_records table
CREATE TABLE IF NOT EXISTS public.user_1rm_records (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid REFERENCES public.user_profile(user_id) ON DELETE CASCADE,
    exercise_name text NOT NULL,
    weight_kg float NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

-- Index for faster queries per user
CREATE INDEX IF NOT EXISTS idx_user_1rm_records_user_id ON public.user_1rm_records(user_id);
-- Unique constraint to ensure one record per exercise per user (can be upserted)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_1rm_unique_exercise ON public.user_1rm_records(user_id, exercise_name);
