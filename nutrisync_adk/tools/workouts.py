import logging
from typing import Optional, List, Dict, Any
from ..tools.utils import get_supabase_client, calculate_log_timestamp

logger = logging.getLogger(__name__)

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
    Logs a workout session.
    
    Args:
        workout_type: Type of workout (e.g., 'Running', 'Lifting').
        duration_minutes: Duration in minutes.
        calories_burned: Calories burned.
        avg_heart_rate: Average heart rate during workout.
        heart_rate_recovery_dropped: Heart rate beats dropped in 1 minute recovery.
        aerobic_training_stress: Training stress score (optional).
    """
    try:
        supabase = get_supabase_client()
        timestamp = calculate_log_timestamp()
        
        # Determine functional day
        from ..tools.utils import get_today_date_str
        log_date = get_today_date_str()
        
        data = {
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
            return f"Successfully logged {workout_type} ({duration_minutes} min, {calories_burned} kcal)."
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
    try:
        supabase = get_supabase_client()
        query = supabase.table("workout_logs").select("*").order("created_at", desc=True)
        
        if start_date:
            query = query.gte("created_at", start_date)
            if end_date:
                query = query.lte("created_at", end_date)
            query = query.limit(100)
        else:
            if days:
                from datetime import timedelta
                from ..tools.utils import get_current_functional_time
                now = get_current_functional_time()
                lookback_date = now - timedelta(days=days)
                query = query.gte("created_at", lookback_date.isoformat())
            query = query.limit(50)
            
        response = query.execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching workout history: {e}")
        return []

def calculate_workout_volume() -> str:
    """
    Helper to analyze workout volume.
    Currently just a placeholder that the Agent can use to justify advice.
    """
    return "Analysis: Volume calculation should be done by the Agent using 'get_workout_history'."

def get_next_scheduled_workout() -> Dict[str, Any]:
    """
    Returns the next scheduled workout based on the user's active workout split.
    
    The function queries the database for the active split and determines
    the next workout based on the last completed workout that matches the split.
    If a day is missed, the schedule simply shifts forward.
    
    Returns:
        A dictionary with:
        - next_workout: The name of the next scheduled workout
        - split_name: The name of the active split (e.g., "Arnold Split")
        - position: Current position in the cycle (e.g., 3 of 5)
        - total: Total workouts in the cycle
        - message: A human-readable status message
    """
    try:
        supabase = get_supabase_client()
        
        # Call the PostgreSQL function
        response = supabase.rpc('get_next_workout').execute()
        
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
        return {
            "next_workout": None,
            "message": f"Error fetching schedule: {str(e)}"
        }
