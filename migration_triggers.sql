-- 1. Safely add log_date to workout_logs & Fix daily_goals schema
-- We use a transaction to ensure data integrity during the schema change
BEGIN;

DO $$
BEGIN
    -- A. Add log_date to workout_logs
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'workout_logs' AND column_name = 'log_date') THEN
        ALTER TABLE workout_logs ADD COLUMN log_date DATE;
        UPDATE workout_logs SET log_date = DATE(created_at AT TIME ZONE 'UTC');
        ALTER TABLE workout_logs ALTER COLUMN log_date SET DEFAULT CURRENT_DATE, ALTER COLUMN log_date SET NOT NULL;
    END IF;

    -- B. Add updated_at to daily_goals (Trigger depends on it)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'daily_goals' AND column_name = 'updated_at') THEN
        ALTER TABLE daily_goals ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;
    
    -- C. Ensure calorie_target has default (Trigger inserts without it)
    ALTER TABLE daily_goals ALTER COLUMN calorie_target SET DEFAULT 2500;
END $$;

COMMIT;

-- 2. Robust Trigger Function for Nutrition (Handles Date Changes & Status Updates)
CREATE OR REPLACE FUNCTION update_daily_nutrition_totals()
RETURNS TRIGGER AS $$
DECLARE
    target_date DATE;
    current_val INT;
    profile_target INT;
BEGIN
    -- Case A: Handle the OLD date
    IF (TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.log_date <> NEW.log_date)) THEN
        target_date := OLD.log_date;
        SELECT COALESCE(SUM(calories), 0) INTO current_val FROM nutrition_logs WHERE log_date = target_date;
        
        INSERT INTO daily_goals (goal_date, calories_consumed)
        VALUES (target_date, current_val)
        ON CONFLICT (goal_date) DO UPDATE SET
            calories_consumed = EXCLUDED.calories_consumed,
            calorie_target_met = (EXCLUDED.calories_consumed >= daily_goals.calorie_target),
            updated_at = NOW();
    END IF;

    -- Case B: Handle the NEW date
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') THEN
        target_date := NEW.log_date;
        SELECT COALESCE(SUM(calories), 0) INTO current_val FROM nutrition_logs WHERE log_date = target_date;
        
        -- Get Profile Target for Insert Default
        SELECT daily_calorie_target INTO profile_target FROM user_profile LIMIT 1;
        IF profile_target IS NULL THEN profile_target := 2500; END IF;

        INSERT INTO daily_goals (goal_date, calories_consumed, calorie_target, calorie_target_met)
        VALUES (
            target_date, 
            current_val,
            profile_target,
            (current_val >= profile_target)
        )
        ON CONFLICT (goal_date) DO UPDATE SET
            calories_consumed = EXCLUDED.calories_consumed,
            calorie_target_met = (EXCLUDED.calories_consumed >= daily_goals.calorie_target),
            updated_at = NOW();
    END IF;
        
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 3. Apply Nutrition Trigger
DROP TRIGGER IF EXISTS trg_update_daily_nutrition ON nutrition_logs;
CREATE TRIGGER trg_update_daily_nutrition
AFTER INSERT OR UPDATE OR DELETE ON nutrition_logs
FOR EACH ROW EXECUTE FUNCTION update_daily_nutrition_totals();

-- 4. Robust Trigger Function for Workouts (Handles Status Updates)
CREATE OR REPLACE FUNCTION update_daily_workout_totals()
RETURNS TRIGGER AS $$
DECLARE
    target_date DATE;
    current_val INT;
    profile_target INT; 
BEGIN
    profile_target := 1; -- Default daily workout target

    -- Case A: Handle the OLD date
    IF (TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.log_date <> NEW.log_date)) THEN
        target_date := OLD.log_date;
        SELECT COUNT(*) INTO current_val FROM workout_logs WHERE log_date = target_date;
        
        INSERT INTO daily_goals (goal_date, workouts_completed)
        VALUES (target_date, current_val)
        ON CONFLICT (goal_date) DO UPDATE SET
            workouts_completed = EXCLUDED.workouts_completed,
            workout_target_met = (EXCLUDED.workouts_completed >= daily_goals.workout_target),
            updated_at = NOW();
    END IF;

    -- Case B: Handle the NEW date
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') THEN
        target_date := NEW.log_date;
        SELECT COUNT(*) INTO current_val FROM workout_logs WHERE log_date = target_date;
        
        INSERT INTO daily_goals (goal_date, workouts_completed, workout_target, workout_target_met)
        VALUES (
            target_date, 
            current_val,
            profile_target,
            (current_val >= profile_target)
        )
        ON CONFLICT (goal_date) DO UPDATE SET
            workouts_completed = EXCLUDED.workouts_completed,
            workout_target_met = (EXCLUDED.workouts_completed >= daily_goals.workout_target),
            updated_at = NOW();
    END IF;
        
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 5. Apply Workout Trigger
DROP TRIGGER IF EXISTS trg_update_daily_workouts ON workout_logs;
CREATE TRIGGER trg_update_daily_workouts
AFTER INSERT OR UPDATE OR DELETE ON workout_logs
FOR EACH ROW EXECUTE FUNCTION update_daily_workout_totals();
