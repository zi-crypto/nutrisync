import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from supabase import Client

from ..tools.utils import get_today_date_str, get_current_functional_time, CAIRO_TZ

logger = logging.getLogger(__name__)

class ContextService:
    """
    Service for fetching and aggregating user context data.
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def get_user_context(self, user_id: str) -> Dict[str, Any]:
        """
        Fetches all necessary context for the user in parallel:
        - User Profile
        - Daily Goals (Totals)
        - Active Notes
        """
        try:
            # Plan parallel execution
            # 1. Profile
            task_profile = self._fetch_user_profile(user_id)
            # 2. Daily Goals
            task_goals = self._fetch_daily_goals(user_id)
            # 3. Active Notes
            task_notes = self._fetch_active_notes(user_id)

            # Execute
            results = await asyncio.gather(task_profile, task_goals, task_notes, return_exceptions=True)
            
            # Unpack results handling exceptions
            profile = results[0] if not isinstance(results[0], Exception) else {}
            daily_totals = results[1] if not isinstance(results[1], Exception) else self._get_empty_goals()
            active_notes = results[2] if not isinstance(results[2], Exception) else []
            
            if isinstance(results[0], Exception): logger.error(f"Error fetching profile: {results[0]}")
            if isinstance(results[1], Exception): logger.error(f"Error fetching goals: {results[1]}")
            if isinstance(results[2], Exception): logger.error(f"Error fetching notes: {results[2]}")

            # Current Time String
            now = get_current_functional_time()
            current_time_str = now.strftime('%Y-%m-%d %H:%M (%A)')

            return {
                "user_id": user_id,
                "profile": profile,
                "daily_totals": daily_totals,
                "current_time": current_time_str,
                "active_notes": active_notes
            }

        except Exception as e:
            logger.error(f"Critical error in ContextService: {e}", exc_info=True)
            return {
                "user_id": user_id,
                "profile": {},
                "daily_totals": self._get_empty_goals(),
                "current_time": "Unknown",
                "active_notes": []
            }

    async def _fetch_user_profile(self, user_id: str) -> Dict[str, Any]:
        # Using async mechanism of supabase-py if available, else standard blocking in thread if needed
        # NOTE: supabase-func calls are blocking HTTP requests. To make them truly async in python
        # without native async library support, we wrap in to_thread if they block.
        # However, supabase-py's postgrest might be synchronous.
        # For true parallelism with synchronous IO, we use asyncio.to_thread
        return await asyncio.to_thread(self._fetch_user_profile_sync, user_id)

    def _fetch_user_profile_sync(self, user_id: str) -> Dict[str, Any]:
        # NEW: Filter by user_id, not id=1
        res = self.supabase.table("user_profile").select("*").eq("user_id", user_id).execute()
        return res.data[0] if res.data else {}

    async def _fetch_daily_goals(self, user_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._fetch_daily_goals_sync, user_id)

    def _fetch_daily_goals_sync(self, user_id: str) -> Dict[str, Any]:
        today_str = get_today_date_str()
        # NEW: Filter by user_id AND goal_date
        res = self.supabase.table("daily_goals").select("*").eq("user_id", user_id).eq("goal_date", today_str).execute()
        
        data = self._get_empty_goals()
        if res.data:
            row = res.data[0]
            data.update({
                "calories": row.get("calories_consumed", 0),
                "workouts": row.get("workouts_completed", 0),
                "calorie_target_met": row.get("calorie_target_met", False),
                "workout_target_met": row.get("workout_target_met", False)
            })
        return data

    async def _fetch_active_notes(self, user_id: str) -> List[str]:
        return await asyncio.to_thread(self._fetch_active_notes_sync, user_id)

    def _fetch_active_notes_sync(self, user_id: str) -> List[str]:
        # NEW: Filter by user_id
        res = self.supabase.table("persistent_context").select("note_content, created_at").eq("user_id", user_id).eq("is_active", True).execute()
        notes = []
        if res.data:
            for n in res.data:
                content = n['note_content']
                created_at = n.get('created_at')
                time_suffix = ""
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        dt_cairo = dt.astimezone(CAIRO_TZ)
                        time_suffix = f" (Added: {dt_cairo.strftime('%Y-%m-%d %H:%M')})"
                    except Exception:
                        pass
                notes.append(f"{content}{time_suffix}")
        return notes

    def _get_empty_goals(self) -> Dict[str, Any]:
        return {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fats": 0,
            "workouts": 0,
            "calorie_target_met": False,
            "workout_target_met": False
        }
