import logging
from typing import Optional, List, Dict, Any
from google.adk.tools import BaseTool
from ..tools.utils import get_supabase_client, calculate_log_timestamp, get_today_date_str
from ..user_context import current_user_id

logger = logging.getLogger(__name__)

def log_meal(
    food_item: str,
    calories: int,
    protein: int,
    carbs: int,
    fats: int,
    healthy: bool = True,
    confirmation_required: bool = True
) -> str:
    """
    Logs a meal to the nutrition_logs table.
    
    Args:
        food_item: Name of the food.
        calories: Total calories.
        protein: Protein in grams.
        carbs: Carbs in grams.
        fats: Fats in grams.
        healthy: Whether the food is considered healthy/clean.
        confirmation_required: If True, this tool call requires explicit user confirmation before execution.
                               The Agent should STOP and ask the user if this signature is correct.

    Returns:
        Status message string.
    """
    # NOTE: The 'confirmation_required' flag is handled by the ADK/Agent logic during tool selection/execution 
    # if configured, OR the agent checks this arg. 
    # Since ADK might not support 'confirmation_required' as a native metadata field easily on python functions 
    # without decorators, we define it here as a signal. 
    # If the Agent calls this with confirmation_required=True, it effectively means "I am proposing this".
    # BUT, to actually EXECUTE, the agent usually calls it. 
    # If we want the *Runner* to intercept, we'd need middleware.
    # For now, we'll assume the Agent has asked the user "Want to log X?", user says "Yes", then Agent calls this.
    
    try:
        user_id = current_user_id.get()
        if not user_id:
             return "Error: No user context found."

        supabase = get_supabase_client()
        timestamp = calculate_log_timestamp()
        
        data = {
            "user_id": user_id,
            "created_at": timestamp,
            "food_item": food_item,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fats": fats,
            "healthy": healthy
        }
        
        response = supabase.table("nutrition_logs").insert(data).execute()
        
        # Check if successful (Supabase-py usually raises error or returns data)
        if response.data:
            return f"Successfully logged {food_item} ({calories}kcal)."
        else:
            return "Error: Failed to log meal (No data returned)."

    except Exception as e:
        logger.error(f"Error logging meal: {e}")
        return f"Error logging meal: {str(e)}"

def get_nutrition_history(days: Optional[int] = 7, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches nutrition logs.
    
    Args:
        days: Number of days to look back from today (default 7).
        start_date: Specific start date (YYYY-MM-DD or ISO) to search from. Only one of 'days' or 'start_date' is needed.
        end_date: Specific end date (YYYY-MM-DD or ISO) to search up to.
    """
    from ..tools.utils import query_user_logs
    return query_user_logs("nutrition_logs", days=days, start_date=start_date, end_date=end_date)


def calculate_macros(food_name: str) -> str:
    """
    Calculates/Estimates macros for a given food name.
    ACTUALLY, this usually relies on the LLM's internal knowledge.
    This tool might be redundant if the LLM does the estimation itself as per system prompt instructions.
    But we can keep it as a placeholder if we want to hook up an external API later.
    For now, returns a prompt for the LLM to use its own knowledge.
    """
    return "Please estimate macros using your internal knowledge database."
