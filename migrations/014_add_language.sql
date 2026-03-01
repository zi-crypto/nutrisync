-- 014: Add language preference column to user_profiles
-- Default 'en' for all existing users

ALTER TABLE user_profile
ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';

COMMENT ON COLUMN user_profile.language IS 'UI language preference: en, ar';
