import logging
import json
from typing import Optional, List, Dict, Any
from ..tools.utils import get_supabase_client, calculate_log_timestamp, get_today_date_str
from ..user_context import current_user_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session-level workout logging (existing, enhanced to return workout_log_id)
# ---------------------------------------------------------------------------

def log_workout(
    workout_type: str,
    duration_minutes: int,
    calories_burned: int,
    avg_heart_rate: Optional[int] = None,
    heart_rate_recovery_dropped: Optional[int] = None,
    aerobic_training_stress: float = 0.0,
    confirmation_required: bool = True
) -> str:
    """
    Logs a workout session and returns the workout_log_id for linking exercise sets.

    Args:
        workout_type: Type of workout (e.g., 'Running', 'Lifting', 'Push', 'Pull', 'Legs').
        duration_minutes: Duration in minutes.
        calories_burned: Calories burned.
        avg_heart_rate: Average heart rate during workout.
        heart_rate_recovery_dropped: Heart rate beats dropped in 1 minute recovery.
        aerobic_training_stress: Training stress score (optional).
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return "Error: No user context."

        supabase = get_supabase_client()
        timestamp = calculate_log_timestamp()
        log_date = get_today_date_str()

        data = {
            "user_id": user_id,
            "created_at": timestamp,
            "log_date": log_date,
            "workout_type": workout_type,
            "duration_minutes": duration_minutes,
            "calories_burned": calories_burned,
            "avg_heart_rate": avg_heart_rate,
            "heart_rate_recovery_dropped": heart_rate_recovery_dropped,
            "aerobic_training_stress": aerobic_training_stress
        }

        response = supabase.table("workout_logs").insert(data).execute()

        if response.data:
            row = response.data[0]
            workout_log_id = row.get("id")
            return (
                f"Successfully logged {workout_type} ({duration_minutes} min, {calories_burned} kcal). "
                f"workout_log_id={workout_log_id} — use this to link exercise sets via log_exercise_sets."
            )
        else:
            return "Error: Failed to log workout."

    except Exception as e:
        logger.error(f"Error logging workout: {e}")
        return f"Error logging workout: {str(e)}"

def get_workout_history(days: Optional[int] = 7, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches workout logs.
    
    Args:
        days: Number of days to look back from today (default 7).
        start_date: Specific start date (YYYY-MM-DD or ISO) to search from. Only one of 'days' or 'start_date' is needed.
        end_date: Specific end date to search up to.
    """
    from ..tools.utils import query_user_logs
    return query_user_logs("workout_logs", days=days, start_date=start_date, end_date=end_date)


def calculate_workout_volume() -> str:
    """
    Helper to analyze workout volume.
    Currently just a placeholder that the Agent can use to justify advice.
    """
    return "Analysis: Volume calculation should be done by the Agent using 'get_workout_history'."

def get_next_scheduled_workout() -> Dict[str, Any]:
    """
    Returns the next scheduled workout based on the user's active workout split.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return {"message": "Error: User context missing."}

        supabase = get_supabase_client()
        
        # Call the PostgreSQL function - we need to ensure the RPC function accepts user_id if we modified it
        # Assuming the RPC function might NOT take user_id yet, but let's check. 
        # Actually, looking at migration_workout_splits.sql (which I can't see but assume exists), 
        # it probably assumes 'everyone' or specific ID?
        # IMPORTANT: If the RPC is hardcoded to a user, this breaks. 
        # For now, pass user_id to RPC if possible, or assume RPC handles it via current_setting if RLS?
        # Supabase RPC: .rpc('name', {params})
        
        response = supabase.rpc('get_next_workout', {"p_user_id": user_id}).execute()
        
        if response.data and len(response.data) > 0:
            row = response.data[0]
            next_workout = row.get('next_workout_name')
            split_name = row.get('split_name')
            position = row.get('current_position')
            total = row.get('total_items')
            
            if next_workout:
                return {
                    "next_workout": next_workout,
                    "split_name": split_name,
                    "position": position,
                    "total": total,
                    "message": f"Next scheduled: {next_workout} ({position}/{total} in {split_name})"
                }
            else:
                return {
                    "next_workout": None,
                    "split_name": None,
                    "position": None,
                    "total": None,
                    "message": "No active workout split configured."
                }
        else:
            return {
                "next_workout": None,
                "message": "No active workout split configured."
            }
            
    except Exception as e:
        logger.error(f"Error fetching next scheduled workout: {e}")
        # Try fallback without params if RPC signature mismatch
        return {
            "next_workout": None,
            "message": f"Error fetching schedule: {str(e)}"
        }


# ============================================================================
# WORKOUT PLAN MANAGEMENT TOOLS
# ============================================================================

# ---------------------------------------------------------------------------
# Volume & rep-range science tables (Schoenfeld dose-response / RP landmarks)
# ---------------------------------------------------------------------------

# Weekly sets per muscle group by experience level
VOLUME_TABLE = {
    "beginner":     {"default": 6,  "quads": 6,  "chest": 6,  "back": 6,  "hamstrings": 6,
                     "shoulders": 6, "biceps": 4, "triceps": 4, "glutes": 6,
                     "calves": 4, "core": 4, "forearms": 2, "traps": 4, "rear_delts": 4},
    "intermediate": {"default": 12, "quads": 12, "chest": 12, "back": 14, "hamstrings": 10,
                     "shoulders": 12, "biceps": 10, "triceps": 10, "glutes": 10,
                     "calves": 8,  "core": 8,  "forearms": 4,  "traps": 8, "rear_delts": 8},
    "advanced":     {"default": 18, "quads": 18, "chest": 16, "back": 20, "hamstrings": 14,
                     "shoulders": 16, "biceps": 14, "triceps": 14, "glutes": 14,
                     "calves": 12, "core": 10, "forearms": 6,  "traps": 10, "rear_delts": 10},
}

# Rep ranges and load % by fitness goal
GOAL_REP_RANGES = {
    "build muscle":        {"rep_low": 6,  "rep_high": 12, "load_low": 0.60, "load_high": 0.80},
    "hypertrophy":         {"rep_low": 6,  "rep_high": 12, "load_low": 0.60, "load_high": 0.80},
    "lose weight":         {"rep_low": 8,  "rep_high": 15, "load_low": 0.50, "load_high": 0.70},
    "improve endurance":   {"rep_low": 12, "rep_high": 20, "load_low": 0.30, "load_high": 0.60},
    "strength":            {"rep_low": 1,  "rep_high": 6,  "load_low": 0.80, "load_high": 1.00},
    "maintain":            {"rep_low": 8,  "rep_high": 12, "load_low": 0.55, "load_high": 0.75},
}

# Muscle groups expected per split day type
SPLIT_MUSCLE_MAP = {
    "push":       ["chest", "front_delts", "side_delts", "triceps"],
    "pull":       ["back", "rear_delts", "biceps", "forearms", "traps"],
    "legs":       ["quads", "hamstrings", "glutes", "calves", "core"],
    "upper":      ["chest", "back", "shoulders", "front_delts", "side_delts", "rear_delts", "biceps", "triceps"],
    "lower":      ["quads", "hamstrings", "glutes", "calves", "core"],
    "full body":  ["chest", "back", "shoulders", "quads", "hamstrings", "glutes", "biceps", "triceps", "core"],
    "chest/back": ["chest", "back", "traps", "rear_delts", "core"],
    "shoulders/arms": ["shoulders", "front_delts", "side_delts", "rear_delts", "biceps", "triceps", "forearms", "traps"],
    "arms":       ["biceps", "triceps", "forearms"],
    "chest":      ["chest", "front_delts", "triceps"],
    "back":       ["back", "rear_delts", "biceps", "traps"],
    "shoulders":  ["shoulders", "front_delts", "side_delts", "rear_delts"],
    # Arnold Split day name aliases
    "chest & back":     ["chest", "back", "traps", "rear_delts", "core"],
    "shoulders & arms": ["shoulders", "front_delts", "side_delts", "rear_delts", "biceps", "triceps", "forearms", "traps"],
    # Full Body variants
    "full body a":      ["chest", "back", "shoulders", "quads", "hamstrings", "glutes", "biceps", "triceps", "core"],
    "full body b":      ["chest", "back", "shoulders", "quads", "hamstrings", "glutes", "biceps", "triceps", "core"],
}


def _get_user_plan_context() -> Dict[str, Any]:
    """Shared helper: fetches user profile, equipment, 1RM records, and active split for plan generation."""
    user_id = current_user_id.get()
    if not user_id:
        raise ValueError("No user context.")

    supabase = get_supabase_client()

    # Fetch profile
    profile_resp = supabase.table("user_profile").select("*").eq("user_id", user_id).limit(1).execute()
    profile = profile_resp.data[0] if profile_resp.data else {}

    # Fetch equipment
    equip_resp = supabase.table("user_equipment").select("equipment_name, category").eq("user_id", user_id).execute()
    equipment = [row["equipment_name"] for row in (equip_resp.data or [])]

    # Fetch 1RM records
    orm_resp = supabase.table("user_1rm_records").select("exercise_name, weight_kg").eq("user_id", user_id).execute()
    one_rm = {row["exercise_name"]: row["weight_kg"] for row in (orm_resp.data or [])}

    # Fetch active split + items
    split_resp = supabase.table("workout_splits").select("id, name").eq("user_id", user_id).eq("is_active", True).limit(1).execute()
    active_split = split_resp.data[0] if split_resp.data else None

    split_items = []
    if active_split:
        items_resp = (supabase.table("split_items")
                      .select("order_index, workout_name")
                      .eq("split_id", active_split["id"])
                      .order("order_index")
                      .execute())
        split_items = items_resp.data or []

    return {
        "user_id": user_id,
        "profile": profile,
        "equipment": equipment,
        "one_rm": one_rm,
        "active_split": active_split,
        "split_items": split_items,
    }


def _compute_volume_and_reps(experience_level: str, fitness_goal: str, muscle_group: str, sessions_per_week: int) -> Dict[str, Any]:
    """Computes target sets per session and rep range for a muscle group."""
    exp = (experience_level or "intermediate").lower()
    goal = (fitness_goal or "build muscle").lower()

    vol_map = VOLUME_TABLE.get(exp, VOLUME_TABLE["intermediate"])
    weekly_sets = vol_map.get(muscle_group, vol_map["default"])
    sets_per_session = max(2, min(8, -(-weekly_sets // max(1, sessions_per_week))))  # ceiling div, clamp 2-8

    rep_cfg = GOAL_REP_RANGES.get(goal, GOAL_REP_RANGES["build muscle"])

    return {
        "weekly_sets": weekly_sets,
        "sets_per_session": sets_per_session,
        "rep_low": rep_cfg["rep_low"],
        "rep_high": rep_cfg["rep_high"],
        "load_low": rep_cfg["load_low"],
        "load_high": rep_cfg["load_high"],
    }


def generate_workout_plan(
    exercises_json: str,
) -> str:
    """
    Persists an AI-generated workout plan to the database.
    The AI agent MUST call this tool with the full plan after intelligently selecting exercises.

    IMPORTANT - The AI agent should determine the exercises based on:
      1. The user's active workout split (split_items tell you the day names like Push/Pull/Legs)
      2. The user's available equipment (from user_equipment in session state)
      3. The user's experience level and fitness goal (from profile in session state)
      4. The user's 1RM records (from session state) to compute load percentages
      5. Scientific volume guidelines (provided in system prompt)

    Args:
        exercises_json: A JSON string containing the full workout plan. Must be an array of objects, each with:
            - split_day_name (str): The split day this exercise belongs to — MUST match a workout_name in split_items (e.g., 'Push', 'Pull', 'Legs')
            - exercise_order (int): 1-based order within the day (compounds first, then isolations)
            - exercise_name (str): Specific exercise name (e.g., 'Barbell Bench Press')
            - exercise_type (str): 'compound' or 'isolation'
            - target_muscles (list[str]): Muscles targeted (e.g., ['chest', 'front_delts', 'triceps'])
            - sets (int): Number of working sets (typically 3-4 for compounds, 2-3 for isolations)
            - rep_range_low (int): Low end of rep range
            - rep_range_high (int): High end of rep range
            - load_percentage (float|null): %1RM if available (e.g., 0.75 for 75%)
            - rest_seconds (int): Rest between sets (120-180 for compounds, 60-90 for isolations)
            - superset_group (int|null): Group number for supersets — exercises with the same group number
              on the same day are performed as a superset. null = standalone exercise.
              Critical for Arnold Split (e.g., Bench Press + Barbell Row share group 1 on Chest & Back day).
            - notes (str|null): Optional coaching cues

    Returns:
        Confirmation message with the saved plan summary.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return "Error: No user context."

        supabase = get_supabase_client()

        # Parse the plan JSON
        try:
            exercises = json.loads(exercises_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON — {str(e)}"

        if not isinstance(exercises, list) or len(exercises) == 0:
            return "Error: exercises_json must be a non-empty array of exercise objects."

        # Validate required fields
        required_fields = ["split_day_name", "exercise_order", "exercise_name", "exercise_type",
                           "target_muscles", "sets", "rep_range_low", "rep_range_high"]
        for i, ex in enumerate(exercises):
            missing = [f for f in required_fields if f not in ex]
            if missing:
                return f"Error: Exercise #{i+1} missing fields: {missing}"

        # Fetch active split to get split_id
        split_resp = (supabase.table("workout_splits")
                      .select("id")
                      .eq("user_id", user_id)
                      .eq("is_active", True)
                      .limit(1)
                      .execute())
        if not split_resp.data:
            return "Error: No active workout split found. Please set up a workout split first."

        split_id = split_resp.data[0]["id"]

        # Delete existing plan for this split (full replacement)
        supabase.table("workout_plan_exercises").delete().eq("user_id", user_id).eq("split_id", split_id).execute()

        # Build insert rows
        now_iso = calculate_log_timestamp(functional_check=False)
        rows = []
        for ex in exercises:
            rows.append({
                "user_id": user_id,
                "split_id": split_id,
                "split_day_name": ex["split_day_name"],
                "exercise_order": ex["exercise_order"],
                "exercise_name": ex["exercise_name"],
                "exercise_type": ex["exercise_type"],
                "target_muscles": ex["target_muscles"],
                "sets": ex["sets"],
                "rep_range_low": ex["rep_range_low"],
                "rep_range_high": ex["rep_range_high"],
                "load_percentage": ex.get("load_percentage"),
                "rest_seconds": ex.get("rest_seconds", 120),
                "superset_group": ex.get("superset_group"),
                "notes": ex.get("notes"),
                "created_at": now_iso,
                "updated_at": now_iso,
            })

        # Batch insert
        insert_resp = supabase.table("workout_plan_exercises").insert(rows).execute()

        if not insert_resp.data:
            return "Error: Failed to save workout plan."

        # Build summary
        days = {}
        for ex in exercises:
            day = ex["split_day_name"]
            if day not in days:
                days[day] = []
            days[day].append(ex["exercise_name"])

        summary_parts = []
        for day, exs in days.items():
            summary_parts.append(f"  {day}: {len(exs)} exercises ({', '.join(exs)})")

        return (
            f"✅ Workout plan saved successfully! ({len(exercises)} exercises across {len(days)} days)\n"
            + "\n".join(summary_parts)
        )

    except Exception as e:
        logger.error(f"Error generating workout plan: {e}")
        return f"Error saving workout plan: {str(e)}"


def get_workout_plan(split_day_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns the current AI-generated workout plan for the user's active split.
    If split_day_name is provided, returns only exercises for that specific day.
    Otherwise returns the full plan for all days.

    Args:
        split_day_name: Optional day name filter (e.g., 'Push', 'Pull', 'Legs'). If omitted, returns full plan.

    Returns:
        List of exercise plan objects including exercise_name, sets, rep_range, target_muscles, etc.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return [{"error": "No user context."}]

        supabase = get_supabase_client()

        # Get active split
        split_resp = (supabase.table("workout_splits")
                      .select("id, name")
                      .eq("user_id", user_id)
                      .eq("is_active", True)
                      .limit(1)
                      .execute())
        if not split_resp.data:
            return [{"message": "No active workout split found. Set one up first."}]

        split_id = split_resp.data[0]["id"]
        split_name = split_resp.data[0]["name"]

        # Fetch plan exercises
        query = (supabase.table("workout_plan_exercises")
                 .select("split_day_name, exercise_order, exercise_name, exercise_type, "
                         "target_muscles, sets, rep_range_low, rep_range_high, "
                         "load_percentage, rest_seconds, superset_group, notes")
                 .eq("user_id", user_id)
                 .eq("split_id", split_id)
                 .order("split_day_name")
                 .order("exercise_order"))

        if split_day_name:
            query = query.eq("split_day_name", split_day_name)

        resp = query.execute()

        if not resp.data:
            return [{"message": f"No workout plan found for split '{split_name}'. "
                     "Ask me to generate one based on your profile and equipment!"}]

        # Group by day for clean output
        result = []
        for row in resp.data:
            result.append({
                "split_day_name": row["split_day_name"],
                "order": row["exercise_order"],
                "exercise": row["exercise_name"],
                "type": row["exercise_type"],
                "muscles": row["target_muscles"],
                "sets": row["sets"],
                "reps": f"{row['rep_range_low']}-{row['rep_range_high']}",
                "load_%1RM": f"{int(row['load_percentage']*100)}%" if row.get("load_percentage") else None,
                "rest": f"{row['rest_seconds']}s",
                "superset_group": row.get("superset_group"),
                "notes": row.get("notes"),
            })

        return result

    except Exception as e:
        logger.error(f"Error fetching workout plan: {e}")
        return [{"error": f"Error fetching workout plan: {str(e)}"}]


# ============================================================================
# SET-LEVEL EXERCISE LOGGING (Progressive Overload Foundation)
# ============================================================================

def log_exercise_sets(
    exercise_name: str,
    sets_json: str,
    workout_log_id: Optional[str] = None,
) -> str:
    """
    Logs individual exercise sets (weight × reps × RPE) for progressive overload tracking.
    Call this AFTER log_workout to link sets to a session, or standalone.

    IMPORTANT: After logging a workout session with log_workout, pass the returned workout_log_id here
    to link these exercise sets to that session.

    Args:
        exercise_name: Name of the exercise (e.g., 'Barbell Bench Press'). Must match the plan.
        sets_json: JSON array of set objects. Each object must have:
            - weight_kg (float): Weight used for this set
            - reps (int): Repetitions completed
            Optional fields per set:
            - rpe (float): Rate of Perceived Exertion 1-10 (how hard it felt)
            - is_warmup (bool): True if this is a warm-up set (excluded from volume stats)
            - notes (str): Per-set notes
        workout_log_id: UUID from log_workout to link these sets to a session. Highly recommended.

    Returns:
        Confirmation message with volume summary and PR detection.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return "Error: No user context."

        supabase = get_supabase_client()
        log_date = get_today_date_str()

        # Parse sets
        try:
            sets_data = json.loads(sets_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON — {str(e)}"

        if not isinstance(sets_data, list) or len(sets_data) == 0:
            return "Error: sets_json must be a non-empty array of set objects."

        # Fetch existing PR for this exercise (best volume_load = weight × reps, excluding warmups)
        pr_resp = (supabase.table("exercise_logs")
                   .select("weight_kg, reps, volume_load")
                   .eq("user_id", user_id)
                   .ilike("exercise_name", exercise_name)
                   .eq("is_warmup", False)
                   .order("volume_load", desc=True)
                   .limit(1)
                   .execute())
        existing_best_volume = pr_resp.data[0]["volume_load"] if pr_resp.data else 0

        # Fetch existing best weight for PR detection
        weight_pr_resp = (supabase.table("exercise_logs")
                          .select("weight_kg")
                          .eq("user_id", user_id)
                          .ilike("exercise_name", exercise_name)
                          .eq("is_warmup", False)
                          .order("weight_kg", desc=True)
                          .limit(1)
                          .execute())
        existing_best_weight = weight_pr_resp.data[0]["weight_kg"] if weight_pr_resp.data else 0

        # Build insert rows & track PRs
        rows = []
        prs_detected = []
        total_volume = 0
        working_sets = 0

        for i, s in enumerate(sets_data, start=1):
            weight = s.get("weight_kg", 0)
            reps = s.get("reps", 0)
            rpe = s.get("rpe")
            is_warmup = s.get("is_warmup", False)
            notes = s.get("notes")
            vol = weight * reps

            # PR detection (only for working sets)
            is_pr = False
            if not is_warmup and vol > 0:
                if vol > existing_best_volume:
                    is_pr = True
                    existing_best_volume = vol  # Update running best
                    prs_detected.append(f"Set {i}: {weight}kg × {reps} = {vol:.0f}kg volume (NEW PR!)")
                elif weight > existing_best_weight:
                    is_pr = True
                    existing_best_weight = weight
                    prs_detected.append(f"Set {i}: {weight}kg (NEW weight PR!)")

            if not is_warmup:
                total_volume += vol
                working_sets += 1

            row = {
                "user_id": user_id,
                "workout_log_id": workout_log_id,
                "log_date": log_date,
                "exercise_name": exercise_name,
                "set_number": i,
                "weight_kg": weight,
                "reps": reps,
                "rpe": rpe,
                "is_warmup": is_warmup,
                "is_pr": is_pr,
                "notes": notes,
            }
            rows.append(row)

        # Batch insert
        insert_resp = supabase.table("exercise_logs").insert(rows).execute()

        if not insert_resp.data:
            return "Error: Failed to log exercise sets."

        # Auto-update 1RM if a 1-rep max was logged
        for s in sets_data:
            if s.get("reps") == 1 and not s.get("is_warmup", False) and s.get("weight_kg", 0) > 0:
                _try_update_1rm(supabase, user_id, exercise_name, s["weight_kg"])

        # Build response summary
        msg = f"✅ Logged {exercise_name}: {len(rows)} sets ({working_sets} working), total volume {total_volume:.0f}kg"
        if workout_log_id:
            msg += f" (linked to session #{workout_log_id})"
        if prs_detected:
            msg += "\n🏆 " + "\n🏆 ".join(prs_detected)

        return msg

    except Exception as e:
        logger.error(f"Error logging exercise sets: {e}")
        return f"Error logging exercise sets: {str(e)}"


def _try_update_1rm(supabase, user_id: str, exercise_name: str, weight_kg: float):
    """Auto-update 1RM record if the logged weight exceeds the existing record.
    Uses LOWER() matching to find existing records and normalizes to title case on write."""
    try:
        # Case-insensitive lookup
        existing = (supabase.table("user_1rm_records")
                    .select("exercise_name, weight_kg")
                    .eq("user_id", user_id)
                    .ilike("exercise_name", exercise_name)
                    .limit(1)
                    .execute())

        if existing.data and existing.data[0]["weight_kg"] >= weight_kg:
            return  # Existing 1RM is higher or equal, no update needed

        # Use the canonical (existing) exercise name to avoid case-sensitive unique index duplication.
        # If no record exists yet, use title-case normalization.
        canonical_name = existing.data[0]["exercise_name"] if existing.data else exercise_name.title()

        # Upsert the 1RM record
        supabase.table("user_1rm_records").upsert({
            "user_id": user_id,
            "exercise_name": canonical_name,
            "weight_kg": weight_kg,
            "updated_at": calculate_log_timestamp(functional_check=False),
        }, on_conflict="user_id,exercise_name").execute()

        logger.info(f"Auto-updated 1RM for {canonical_name}: {weight_kg}kg")
    except Exception as e:
        logger.warning(f"Failed to auto-update 1RM for {exercise_name}: {e}")


# ============================================================================
# PROGRESSIVE OVERLOAD QUERYING
# ============================================================================

def get_exercise_history(
    exercise_name: str,
    days: Optional[int] = 30,
) -> List[Dict[str, Any]]:
    """
    Fetches the set-level history for a specific exercise, ordered by date descending.
    This is the data source for the progressive overload tracker charts.

    Args:
        exercise_name: Name of the exercise (e.g., 'Barbell Bench Press').
        days: Number of days to look back (default 30).

    Returns:
        List of logged sets with date, weight, reps, RPE, volume, and PR flags.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return [{"error": "No user context."}]

        supabase = get_supabase_client()
        from datetime import timedelta
        from ..tools.utils import get_current_functional_time

        cutoff = get_current_functional_time() - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d')

        resp = (supabase.table("exercise_logs")
                .select("log_date, set_number, weight_kg, reps, rpe, is_warmup, is_pr, volume_load, notes")
                .eq("user_id", user_id)
                .ilike("exercise_name", exercise_name)
                .gte("log_date", cutoff_str)
                .order("log_date", desc=True)
                .order("set_number")
                .limit(200)
                .execute())

        return resp.data if resp.data else []

    except Exception as e:
        logger.error(f"Error fetching exercise history: {e}")
        return [{"error": str(e)}]


def get_progressive_overload_summary(
    exercise_name: Optional[str] = None,
    weeks: int = 8,
) -> Dict[str, Any]:
    """
    Returns progressive overload metrics for one or all exercises.
    Includes estimated 1RM trends, volume trends, and PR history.
    Uses the Epley formula: e1RM = weight × (1 + reps / 30).

    Args:
        exercise_name: Specific exercise name. If omitted, returns summaries for all logged exercises.
        weeks: Number of weeks to analyze (default 8).

    Returns:
        Dictionary with per-exercise overload data:
        - weekly_trend: [{week, best_e1rm, total_volume, total_sets, has_pr}]
        - all_time_pr: {best_weight, best_volume_set, best_e1rm}
        - recent_session: last logged sets for this exercise
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
            return {"error": "No user context."}

        supabase = get_supabase_client()

        # If exercise_name specified, use the DB function for efficiency
        if exercise_name:
            progress_resp = supabase.rpc("get_exercise_progress", {
                "p_user_id": user_id,
                "p_exercise_name": exercise_name,
                "p_weeks": weeks,
            }).execute()

            weekly_trend = progress_resp.data if progress_resp.data else []

            # Fetch all-time PRs
            pr_resp = (supabase.table("exercise_logs")
                       .select("weight_kg, reps, volume_load, log_date")
                       .eq("user_id", user_id)
                       .ilike("exercise_name", exercise_name)
                       .eq("is_warmup", False)
                       .eq("is_pr", True)
                       .order("log_date", desc=True)
                       .limit(20)
                       .execute())

            # Best stats
            best_weight_resp = (supabase.table("exercise_logs")
                                .select("weight_kg, reps, log_date")
                                .eq("user_id", user_id)
                                .ilike("exercise_name", exercise_name)
                                .eq("is_warmup", False)
                                .order("weight_kg", desc=True)
                                .limit(1)
                                .execute())

            best_vol_resp = (supabase.table("exercise_logs")
                             .select("weight_kg, reps, volume_load, log_date")
                             .eq("user_id", user_id)
                             .ilike("exercise_name", exercise_name)
                             .eq("is_warmup", False)
                             .order("volume_load", desc=True)
                             .limit(1)
                             .execute())

            best_weight = best_weight_resp.data[0] if best_weight_resp.data else None
            best_volume = best_vol_resp.data[0] if best_vol_resp.data else None

            # Compute best e1RM from best_weight
            best_e1rm = None
            if best_weight:
                w, r = best_weight["weight_kg"], best_weight["reps"]
                best_e1rm = round(w * (1 + r / 30.0), 1) if r > 0 else w

            # Fetch last session
            latest_date_resp = (supabase.table("exercise_logs")
                                .select("log_date")
                                .eq("user_id", user_id)
                                .ilike("exercise_name", exercise_name)
                                .order("log_date", desc=True)
                                .limit(1)
                                .execute())

            recent_session = []
            if latest_date_resp.data:
                latest_date = latest_date_resp.data[0]["log_date"]
                session_resp = (supabase.table("exercise_logs")
                                .select("set_number, weight_kg, reps, rpe, is_warmup, is_pr, volume_load")
                                .eq("user_id", user_id)
                                .ilike("exercise_name", exercise_name)
                                .eq("log_date", latest_date)
                                .order("set_number")
                                .execute())
                recent_session = session_resp.data or []

            return {
                "exercise": exercise_name,
                "weekly_trend": weekly_trend,
                "all_time_pr": {
                    "best_weight": best_weight,
                    "best_volume_set": best_volume,
                    "best_e1rm": best_e1rm,
                },
                "pr_history": pr_resp.data or [],
                "recent_session": recent_session,
            }

        else:
            # Get summary for ALL exercises the user has logged
            from datetime import timedelta
            from ..tools.utils import get_current_functional_time

            cutoff = get_current_functional_time() - timedelta(weeks=weeks)
            cutoff_str = cutoff.strftime('%Y-%m-%d')

            # Get distinct exercises
            all_resp = (supabase.table("exercise_logs")
                        .select("exercise_name, weight_kg, reps, volume_load, is_pr, log_date")
                        .eq("user_id", user_id)
                        .eq("is_warmup", False)
                        .gte("log_date", cutoff_str)
                        .order("log_date", desc=True)
                        .limit(500)
                        .execute())

            if not all_resp.data:
                return {"exercises": [], "message": "No exercise sets logged yet."}

            # Group by exercise
            exercise_map = {}
            for row in all_resp.data:
                name = row["exercise_name"]
                if name not in exercise_map:
                    exercise_map[name] = {
                        "total_sets": 0,
                        "total_volume": 0,
                        "best_weight": 0,
                        "best_volume_set": 0,
                        "pr_count": 0,
                        "last_date": row["log_date"],
                    }
                entry = exercise_map[name]
                entry["total_sets"] += 1
                entry["total_volume"] += (row["volume_load"] or 0)
                entry["best_weight"] = max(entry["best_weight"], row["weight_kg"])
                entry["best_volume_set"] = max(entry["best_volume_set"], row["volume_load"] or 0)
                if row.get("is_pr"):
                    entry["pr_count"] += 1

            exercises_summary = [
                {"exercise": name, **data}
                for name, data in exercise_map.items()
            ]

            return {
                "exercises": exercises_summary,
                "total_exercises_tracked": len(exercises_summary),
            }

    except Exception as e:
        logger.error(f"Error fetching progressive overload summary: {e}")
        return {"error": str(e)}
