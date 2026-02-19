-- Migration: Add Onboarding Fields to User Profile
ALTER TABLE public.user_profile
ADD COLUMN IF NOT EXISTS name text,
ADD COLUMN IF NOT EXISTS experience_level text, -- e.g. 'Beginner', 'Intermediate', 'Advanced'
ADD COLUMN IF NOT EXISTS equipment_access text; -- e.g. 'Gym', 'Home', 'None'
