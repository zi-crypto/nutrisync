import os
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import pytz
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Single instance/factory for Supabase
_supabase_client = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _supabase_client = create_client(url, key)
    return _supabase_client

# Constants
CAIRO_TZ = pytz.timezone('Africa/Cairo')
FUNCTIONAL_DAY_OFFSET_HOURS = 4

def get_current_functional_time() -> datetime:
    """
    Returns the current time in Cairo, adjusted for the 'Functional Day'.
    If the time is between 00:00 and 04:00, it counts as the PREVIOUS day.
    """
    now_cairo = datetime.now(CAIRO_TZ)
    return now_cairo

def calculate_log_timestamp(functional_check: bool = True) -> str:
    """
    Calculates the ISO-8601 timestamp for a log entry.
    If functional_check is True and time is 00:00-04:00, returns 23:59:59 of yesterday.
    Otherwise returns current Cairo time.
    """
    now = get_current_functional_time()
    
    if functional_check and 0 <= now.hour < FUNCTIONAL_DAY_OFFSET_HOURS:
        # It's late night (e.g., 2 AM), belongs to yesterday
        yesterday = now - timedelta(days=1)
        # Set to end of yesterday
        adjusted_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
        logger.info(f"Functional Day Adjustment: {now} -> {adjusted_time}")
        return adjusted_time.isoformat()
    
    return now.isoformat()

def get_today_date_str() -> str:
    """
    Returns the 'functional' today date string (YYYY-MM-DD).
    If it's 2 AM Tuesday, returns Monday's date for daily queries.
    """
    now = get_current_functional_time()
    if 0 <= now.hour < FUNCTIONAL_DAY_OFFSET_HOURS:
        functional_now = now - timedelta(days=1)
        return functional_now.strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def get_health_scores(user_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", persist: bool = False) -> Dict[str, Any]:
    """
    Calls the Supabase Edge Function 'user-improvement-scorer' to get health scores.
    
    Args:
        user_id: The UUID of the user. (Defaults to hardcoded ID from legacy system for now)
        persist: Whether to persist the scores in the database or just calculate them.
    """
    try:
        supabase = get_supabase_client()
        # Using functions.invoke 
        response = supabase.functions.invoke(
            "user-improvement-scorer",
            invoke_options={"body": {"user_id": user_id, "persist": persist}}
        )
        
        # Checking if data is available
        if hasattr(response, 'data') and response.data:
            return response.data if isinstance(response.data, dict) else {} 
            
        return {} # Fallback
        
    except Exception as e:
        logger.error(f"Error fetching health scores: {e}")
        return {"error": str(e)}
