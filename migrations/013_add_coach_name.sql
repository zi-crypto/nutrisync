-- Add coach_name column so users can name their AI coach
ALTER TABLE user_profile
ADD COLUMN IF NOT EXISTS coach_name TEXT DEFAULT 'NutriSync';
