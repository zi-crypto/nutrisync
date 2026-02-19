-- Migration: Add Weight Columns to User Profile
ALTER TABLE public.user_profile
ADD COLUMN IF NOT EXISTS weight_kg float,
ADD COLUMN IF NOT EXISTS starting_weight_kg float;
