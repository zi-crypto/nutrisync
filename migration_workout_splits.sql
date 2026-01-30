-- Migration: Flexible Workout Splits Schema
-- Run this in your Supabase SQL Editor

BEGIN;

-- ============================================================================
-- 1. SCHEMA: Tables for workout splits
-- ============================================================================

-- Table to hold different workout split definitions (e.g., Arnold Split, PPL, etc.)
CREATE TABLE IF NOT EXISTS public.workout_splits (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
    name text NOT NULL,
    description text,
    is_active boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
    CONSTRAINT workout_splits_pkey PRIMARY KEY (id)
);

-- Table to hold the ordered items within a split
CREATE TABLE IF NOT EXISTS public.split_items (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    split_id uuid NOT NULL,
    order_index integer NOT NULL, -- 1-based index for order
    workout_name text NOT NULL,   -- The name to match against workout_logs.workout_type
    CONSTRAINT split_items_pkey PRIMARY KEY (id),
    CONSTRAINT split_items_split_id_fkey FOREIGN KEY (split_id) REFERENCES public.workout_splits(id) ON DELETE CASCADE,
    CONSTRAINT split_items_unique_order UNIQUE (split_id, order_index)
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_split_items_split_id ON public.split_items (split_id);
CREATE INDEX IF NOT EXISTS idx_workout_splits_active ON public.workout_splits (user_id) WHERE is_active = true;

-- ============================================================================
-- 2. FUNCTION: Get the next scheduled workout
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_next_workout(p_user_id uuid DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid)
RETURNS TABLE (
    next_workout_name text,
    split_name text,
    current_position integer,
    total_items integer
) AS $$
DECLARE
    v_split_id uuid;
    v_split_name text;
    v_total_items integer;
    v_last_workout_type text;
    v_last_order_index integer;
    v_next_order_index integer;
BEGIN
    -- 1. Find the active split for the user
    SELECT ws.id, ws.name INTO v_split_id, v_split_name
    FROM public.workout_splits ws
    WHERE ws.user_id = p_user_id AND ws.is_active = true
    LIMIT 1;

    -- If no active split, return null
    IF v_split_id IS NULL THEN
        RETURN QUERY SELECT NULL::text, NULL::text, NULL::integer, NULL::integer;
        RETURN;
    END IF;

    -- 2. Get the total number of items in the split
    SELECT COUNT(*)::integer INTO v_total_items
    FROM public.split_items si
    WHERE si.split_id = v_split_id;

    -- 3. Find the most recent workout that matches any item in the split
    SELECT wl.workout_type INTO v_last_workout_type
    FROM public.workout_logs wl
    WHERE wl.user_id = p_user_id
      AND wl.workout_type IN (SELECT si.workout_name FROM public.split_items si WHERE si.split_id = v_split_id)
    ORDER BY wl.log_date DESC, wl.created_at DESC
    LIMIT 1;

    -- 4. Determine the next workout
    IF v_last_workout_type IS NULL THEN
        -- No history matching the split, start from item 1
        v_next_order_index := 1;
    ELSE
        -- Find the order index of the last completed workout
        SELECT si.order_index INTO v_last_order_index
        FROM public.split_items si
        WHERE si.split_id = v_split_id AND si.workout_name = v_last_workout_type;

        -- Calculate the next index (cycling back to 1)
        v_next_order_index := (v_last_order_index % v_total_items) + 1;
    END IF;

    -- 5. Get the next workout name
    RETURN QUERY
    SELECT 
        si.workout_name,
        v_split_name,
        v_next_order_index,
        v_total_items
    FROM public.split_items si
    WHERE si.split_id = v_split_id AND si.order_index = v_next_order_index;

END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 3. SEED DATA: Arnold Split
-- ============================================================================

-- First, insert the split definition
INSERT INTO public.workout_splits (name, description, is_active) VALUES
('Arnold Split', '5-day rotation: Chest/Back (1st), Shoulders/Arms (1st), Legs, Chest/Back (2nd), Shoulders/Arms (2nd)', true)
ON CONFLICT DO NOTHING;

-- Then, insert the ordered items
-- We need to get the split_id first
DO $$
DECLARE
    v_arnold_split_id uuid;
BEGIN
    SELECT id INTO v_arnold_split_id FROM public.workout_splits WHERE name = 'Arnold Split';

    IF v_arnold_split_id IS NOT NULL THEN
        -- Clear existing items for this split (idempotent)
        DELETE FROM public.split_items WHERE split_id = v_arnold_split_id;

        -- Insert the 5 Arnold Split days in order
        INSERT INTO public.split_items (split_id, order_index, workout_name) VALUES
            (v_arnold_split_id, 1, 'Chest/Back (First)'),
            (v_arnold_split_id, 2, 'Shoulders/Arms (First)'),
            (v_arnold_split_id, 3, 'Legs'),
            (v_arnold_split_id, 4, 'Chest/Back (Second)'),
            (v_arnold_split_id, 5, 'Shoulders/Arms (Second)');
    END IF;
END $$;

COMMIT;

-- ============================================================================
-- 4. VERIFICATION: Test the function
-- ============================================================================
-- Uncomment and run this to test after applying the migration:
-- SELECT * FROM public.get_next_workout();
