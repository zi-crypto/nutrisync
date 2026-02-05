import logging
import asyncio
from supabase import Client
from ..tools.utils import get_today_date_str, get_current_functional_time

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Loads user profile and daily totals from Supabase to inject into the system prompt.
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def get_user_context(self, user_id: str = "1") -> dict:
        """
        Fetches:
        - User Profile (Goals, Targets)
        - Daily Totals (Calories, Macros consumed today)
        """
        try:
            # 1. Fetch User Profile
            # Assuming 'id' is 1 as per legacy n8n logic or we use the UUID if mapping exists.
            # Legacy N8N used 'id=1' for user_profile.
            profile_response = self.supabase.table("user_profile").select("*").eq("id", 1).execute()
            profile = profile_response.data[0] if profile_response.data else {}

            # 2. Fetch Daily Goals (Pre-aggregated via Triggers)
            today_str = get_today_date_str()
            
            # Default structure
            daily_totals = {
                "calories": 0,
                "protein": 0, # Not currently aggregated in daily_goals
                "carbs": 0,   # Not currently aggregated in daily_goals
                "fats": 0,    # Not currently aggregated in daily_goals
                "workouts": 0,
                "calorie_target_met": False,
                "workout_target_met": False
            }

            try:
                # Optimized: Read from 'daily_goals' instead of summing raw logs
                goals_res = self.supabase.table("daily_goals").select("*").eq("goal_date", today_str).execute()
                
                if goals_res.data:
                    goal_data = goals_res.data[0]
                    daily_totals["calories"] = goal_data.get("calories_consumed", 0)
                    daily_totals["workouts"] = goal_data.get("workouts_completed", 0)
                    daily_totals["calorie_target_met"] = goal_data.get("calorie_target_met", False)
                    daily_totals["workout_target_met"] = goal_data.get("workout_target_met", False)
                    
            except Exception as e:
                logger.error(f"Error fetching daily goals: {e}")
            
            # Format: 'YYYY-MM-DD HH:MM (DayName)'
            now = get_current_functional_time()
            current_time_str = now.strftime('%Y-%m-%d %H:%M (%A)')
            
            # Fetch Persistent Context (Active Notes)
            active_notes = []
            try:
                res = self.supabase.table("persistent_context").select("note_content, created_at").eq("is_active", True).execute()
                if res.data:
                    from datetime import datetime
                    from ..tools.utils import CAIRO_TZ
                    
                    for n in res.data:
                        content = n['note_content']
                        created_at = n.get('created_at')
                        if created_at:
                            try:
                                # Parse ISO string (handle Z if present)
                                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                # Convert to Cairo time
                                dt_cairo = dt.astimezone(CAIRO_TZ)
                                time_str = dt_cairo.strftime("%Y-%m-%d %H:%M")
                                active_notes.append(f"{content} (Added: {time_str})")
                            except Exception:
                                active_notes.append(content)
                        else:
                            active_notes.append(content)

            except Exception as e:
                logger.error(f"Error fetching active notes: {e}")

            return {
                "profile": profile,
                "daily_totals": daily_totals,
                "current_time": current_time_str,
                "active_notes": active_notes
            }
            
        except Exception as e:
            logger.error(f"Error fetching user context: {e}")
            return {
                "profile": {},
                "daily_totals": {"calories": 0, "protein": 0, "carbs": 0, "fats": 0}
            }
