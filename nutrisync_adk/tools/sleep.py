import logging
import uuid
from typing import Optional, List, Dict, Any
from google.adk.tools import BaseTool
from ..tools.utils import get_supabase_client, calculate_log_timestamp, get_today_date_str
from ..user_context import current_user_id

logger = logging.getLogger(__name__)

def log_sleep(
    night_sleep_hours: float,
    sleep_score: int,
    sleep_start_time: Optional[str] = None,
    deep_sleep_percentage: Optional[int] = None,
    rem_sleep_percentage: Optional[int] = None,
    light_sleep_percentage: Optional[int] = None,
    times_woke_up: Optional[int] = None,
    confirmation_required: bool = True
) -> str:
    """
    Logs a sleep session to the sleep_logs table.
    
    Args:
        night_sleep_hours: Duration of sleep in hours.
        sleep_score: Sleep quality score (0-100).
        sleep_start_time: Bed time (ISO or HH:MM format).
        deep_sleep_percentage: Percentage of deep sleep.
        rem_sleep_percentage: Percentage of REM sleep.
        light_sleep_percentage: Percentage of light sleep.
        times_woke_up: Number of times woke up.
        confirmation_required: Signal for the agent to ask confirmation.

    Returns:
        Status message string.
    """
    try:
        user_id = current_user_id.get()
        if not user_id:
             return "Error: No user context."

        supabase = get_supabase_client()
        # "Created At" is the time of logging (now)
        created_at = calculate_log_timestamp()
        
        # "Sleep Date" is the functional day (e.g. woke up Tuesday morning -> Monday night sleep)
        sleep_date = get_today_date_str()
        
        # Handle sleep_start_time formatting (HH:MM -> Full ISO)
        if sleep_start_time and len(sleep_start_time) <= 5:
            # Assume HH:MM format
            try:
                from datetime import datetime, timedelta
                # Parse the time
                h, m = map(int, sleep_start_time.split(':'))
                
                # Parse the sleep date
                date_obj = datetime.strptime(sleep_date, "%Y-%m-%d")
                
                # Logic: If time is 00:00-12:00, it's likely the "next day" relative to the functional sleep date
                # e.g. Sleep Date = Jan 1 (Monday), Bed Time = 01:00 (Tuesday AM)
                if h < 12:
                     date_obj += timedelta(days=1)
                
                # Combine
                start_dt = date_obj.replace(hour=h, minute=m, second=0)
                
                from ..tools.utils import CAIRO_TZ
                start_dt = CAIRO_TZ.localize(start_dt)
                
                sleep_start_time = start_dt.isoformat()
            except Exception as e:
                logger.warning(f"Could not parse sleep_start_time '{sleep_start_time}', passing as is. Error: {e}")
        
        # Generate UUID locally since schema has no default
        record_id = str(uuid.uuid4())

        data = {
            "id": record_id,
            "user_id": user_id,
            "created_at": created_at,
            "sleep_date": sleep_date,
            "night_sleep_hours": night_sleep_hours,
            "sleep_score": sleep_score,
            "sleep_start_time": sleep_start_time,
            "deep_sleep_percentage": deep_sleep_percentage,
            "rem_sleep_percentage": rem_sleep_percentage,
            "light_sleep_percentage": light_sleep_percentage,
            "times_woke_up": times_woke_up
        }
        
        # Filter out None values to let DB handle nulls if any (though schema seems permissive or handled)
        data = {k: v for k, v in data.items() if v is not None}
        
        response = supabase.table("sleep_logs").insert(data).execute()
        
        if response.data:
            return f"Successfully logged sleep: {night_sleep_hours} hrs (Score: {sleep_score})."
        else:
            return "Error: Failed to log sleep (No data returned)."

    except Exception as e:
        logger.error(f"Error logging sleep: {e}")
        return f"Error logging sleep: {str(e)}"

def get_sleep_history(days: Optional[int] = 7, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches sleep logs.
    
    Args:
        days: Lookback days.
        start_date: Specific start date (YYYY-MM-DD).
        end_date: Specific end date.
    """
    from ..tools.utils import query_user_logs
    return query_user_logs("sleep_logs", date_column="sleep_date", days=days, start_date=start_date, end_date=end_date, default_limit=20)

