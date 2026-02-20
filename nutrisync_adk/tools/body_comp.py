import logging
from typing import Optional, List, Dict, Any
from google.adk.tools import BaseTool
from ..tools.utils import get_supabase_client, calculate_log_timestamp
from ..user_context import current_user_id

logger = logging.getLogger(__name__)

def log_body_comp(
    weight_kg: float,
    muscle_kg: Optional[float] = None,
    bf_percent: Optional[float] = None,
    resting_hr: Optional[int] = None,
    notes: Optional[str] = None,
    confirmation_required: bool = True
) -> str:
    """
    Logs body composition metrics (weight, body fat, etc).
    
    Args:
        weight_kg: Body weight in KG.
        muscle_kg: Muscle mass in KG.
        bf_percent: Body fat percentage.
        resting_hr: Resting heart rate.
        notes: Any text notes.
        confirmation_required: Signal for confirmation.

    Returns:
        Status message.
    """
    try:
        user_id = current_user_id.get()
        if not user_id: return "Error: No user context."

        supabase = get_supabase_client()
        created_at = calculate_log_timestamp()
        
        data = {
            "user_id": user_id,
            "created_at": created_at,
            "weight_kg": weight_kg,
            "muscle_kg": muscle_kg,
            "bf_percent": bf_percent,
            "resting_hr": resting_hr,
            "notes": notes
        }
        
        # Remove None
        data = {k: v for k, v in data.items() if v is not None}
        
        response = supabase.table("body_composition_logs").insert(data).execute()
        
        # Sync with user_profile
        supabase.table("user_profile").update({"weight_kg": weight_kg}).eq("user_id", user_id).execute()
        
        if response.data:
            return f"Successfully logged body comp: {weight_kg}kg."
        else:
            return "Error: Failed to log body comp."

    except Exception as e:
        logger.error(f"Error logging body comp: {e}")
        return f"Error logging body comp: {str(e)}"

def get_body_comp_history(limit: Optional[int] = 10, days: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches body composition logs.
    """
    from ..tools.utils import query_user_logs
    return query_user_logs("body_composition_logs", days=days, start_date=start_date, end_date=end_date, default_limit=limit or 10)

