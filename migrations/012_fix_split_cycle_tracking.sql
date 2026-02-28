-- Migration 012: Fix split cycle tracking
-- Replaces error-prone name-based matching with position-based tracking.
-- Adds column, rewrites get_next_workout, adds advance_split_position, backfills.

BEGIN;

-- ============================================================================
-- 1. Add position tracking column to workout_splits
-- ============================================================================
ALTER TABLE public.workout_splits
    ADD COLUMN IF NOT EXISTS last_completed_order_index integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.workout_splits.last_completed_order_index IS
    'Tracks the order_index of the last completed split workout. 0 = no workouts logged yet (start from position 1).';

-- ============================================================================
-- 2. Rewrite get_next_workout — pure position-based, no name matching
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_next_workout(
    p_user_id uuid DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
)
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
    v_last_order_index integer;
    v_next_order_index integer;
BEGIN
    -- 1. Find the active split for the user
    SELECT ws.id, ws.name, ws.last_completed_order_index
    INTO v_split_id, v_split_name, v_last_order_index
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

    IF v_total_items = 0 THEN
        RETURN QUERY SELECT NULL::text, v_split_name, NULL::integer, 0;
        RETURN;
    END IF;

    -- 3. Compute next position (pure arithmetic — no name matching)
    v_next_order_index := (v_last_order_index % v_total_items) + 1;

    -- 4. Return the workout at that position
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
-- 3. New RPC: advance_split_position — called by log_workout in Python
-- ============================================================================
CREATE OR REPLACE FUNCTION public.advance_split_position(
    p_user_id uuid,
    p_order_index integer
)
RETURNS void AS $$
BEGIN
    UPDATE public.workout_splits
    SET last_completed_order_index = p_order_index
    WHERE user_id = p_user_id AND is_active = true;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Backfill: seed last_completed_order_index for existing active splits
--    Uses the OLD name-matching logic ONE TIME to derive the current position.
-- ============================================================================
DO $$
DECLARE
    r RECORD;
    v_last_workout_type text;
    v_last_order_index integer;
    v_total_items integer;
BEGIN
    FOR r IN
        SELECT ws.id AS split_id, ws.user_id
        FROM public.workout_splits ws
        WHERE ws.is_active = true AND ws.last_completed_order_index = 0
    LOOP
        -- Count items in this split
        SELECT COUNT(*)::integer INTO v_total_items
        FROM public.split_items si
        WHERE si.split_id = r.split_id;

        IF v_total_items = 0 THEN
            CONTINUE;
        END IF;

        -- Find most recent workout matching any split item (old logic)
        SELECT wl.workout_type INTO v_last_workout_type
        FROM public.workout_logs wl
        WHERE wl.user_id = r.user_id
          AND wl.workout_type IN (
              SELECT si.workout_name
              FROM public.split_items si
              WHERE si.split_id = r.split_id
          )
        ORDER BY wl.log_date DESC, wl.created_at DESC
        LIMIT 1;

        IF v_last_workout_type IS NOT NULL THEN
            -- Resolve order_index (pick lowest in case of duplicates)
            SELECT MIN(si.order_index) INTO v_last_order_index
            FROM public.split_items si
            WHERE si.split_id = r.split_id
              AND si.workout_name = v_last_workout_type;

            IF v_last_order_index IS NOT NULL THEN
                UPDATE public.workout_splits
                SET last_completed_order_index = v_last_order_index
                WHERE id = r.split_id;
            END IF;
        END IF;
    END LOOP;
END $$;

COMMIT;
