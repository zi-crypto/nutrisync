-- Migration: Add Onboarding V2 Fields
-- This adds the new fields requested for the wizard if they are missing.

ALTER TABLE public.user_profile
ADD COLUMN IF NOT EXISTS typical_daily_calories integer,
ADD COLUMN IF NOT EXISTS typical_diet_type text,
ADD COLUMN IF NOT EXISTS allergies text,
ADD COLUMN IF NOT EXISTS daily_protein_target_gm integer,
ADD COLUMN IF NOT EXISTS daily_fats_target_gm integer,
ADD COLUMN IF NOT EXISTS daily_carbs_target_gm integer;
