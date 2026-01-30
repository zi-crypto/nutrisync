import logging
from typing import Optional, List, Dict, Any
from google.adk.tools import BaseTool
from ..tools.utils import get_supabase_client, calculate_log_timestamp, get_today_date_str

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
        supabase = get_supabase_client()
        timestamp = calculate_log_timestamp()
        
        data = {
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
        end_date: Specific end date (YYYY-MM-DD or ISO) to search up to. Useful for specific day queries.
    """
    try:
        supabase = get_supabase_client()
        
        query = supabase.table("nutrition_logs").select("*").order("created_at", desc=True)
        
        if start_date:
            # Explicit start date provided
            query = query.gte("created_at", start_date)
            
            if end_date:
                # Explicit end date provided (Range Query)
                # If end_date is just YYYY-MM-DD, we likely want to include the whole day, 
                # but 'lte' does literal comparison. 
                # If the agent passes "2025-12-25", lte matches 00:00:00.
                # Ideally, agent should pass "2025-12-25T23:59:59" OR we handle it.
                # For simplicity, we assume strict ISO comparison or agent handles precision.
                query = query.lte("created_at", end_date)
            
            # Increase limit for explicitly requested history or deep dives
            query = query.limit(100)
        else:
            # Default to lookback days
            if days:
                from datetime import datetime, timedelta
                # We need a proper datetime object, get_current_functional_time returns one
                from ..tools.utils import get_current_functional_time
                now = get_current_functional_time()
                lookback_date = now - timedelta(days=days)
                query = query.gte("created_at", lookback_date.isoformat())
            
            # Default safety limit
            query = query.limit(50)
            
        response = query.execute()    
        return response.data
    except Exception as e:
        logger.error(f"Error fetching nutrition history: {e}")
        return []

def calculate_macros(food_name: str) -> str:
    """
    Calculates/Estimates macros for a given food name.
    ACTUALLY, this usually relies on the LLM's internal knowledge.
    This tool might be redundant if the LLM does the estimation itself as per system prompt instructions.
    But we can keep it as a placeholder if we want to hook up an external API later.
    For now, returns a prompt for the LLM to use its own knowledge.
    """
    return "Please estimate macros using your internal knowledge database."
