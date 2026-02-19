-- Migration: 002_add_images_column.sql
-- Description: Adds 'image_data' column to chat_history to store user-uploaded images separately from tool_calls.

DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'chat_history' AND column_name = 'image_data') THEN
        ALTER TABLE chat_history ADD COLUMN image_data TEXT;
    END IF;
END $$;
