-- Migration: Add Sport Type to User Profile
ALTER TABLE public.user_profile
ADD COLUMN IF NOT EXISTS sport_type text;
