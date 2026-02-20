import logging
import asyncio
from typing import List, Dict, Any, Optional
from supabase import Client
from datetime import timedelta
from ..tools.utils import get_current_functional_time

logger = logging.getLogger(__name__)

class HistoryService:
    """
    Service for fetching historical data (chat, nutrition, workouts).
    Implements generic time-series fetching to stay DRY.
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def get_recent_chat_history(self, user_id: str, limit: int = 20, after: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches recent chat messages for context window."""
        return await asyncio.to_thread(self._get_recent_chat_history_sync, user_id, limit, after)

    def _get_recent_chat_history_sync(self, user_id: str, limit: int, after: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            query = self.supabase.table("chat_history") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit)
            
            if after:
                query = query.gt("created_at", after)

            res = query.execute()
            # Reverse for chronological order
            return res.data[::-1] if res.data else []
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return []

    async def add_message(self, user_id: str, role: str, content: str, tool_calls: Optional[Dict] = None, image_data: Optional[str] = None) -> Optional[str]:
        """Adds a message to history. Returns the inserted message's UUID."""
        return await asyncio.to_thread(self._add_message_sync, user_id, role, content, tool_calls, image_data)

    def _add_message_sync(self, user_id: str, role: str, content: str, tool_calls: Optional[Dict], image_data: Optional[str]) -> Optional[str]:
        try:
            data = {
                "user_id": user_id,
                "role": role,
                "content": content,
                "tool_calls": tool_calls,
                "image_data": image_data
            }
            res = self.supabase.table("chat_history").insert(data).execute()
            if res.data and len(res.data) > 0:
                return res.data[0].get("id")
            return None
        except Exception as e:
            logger.error(f"Error adding message to history: {e}")
            return None

    # --- Generic Time Series Fetchers ---

    async def get_nutrition_history(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        return await self._fetch_time_series(user_id, "nutrition_logs", days)

    async def get_workout_history(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        return await self._fetch_time_series(user_id, "workout_logs", days)

    async def _fetch_time_series(self, user_id: str, table_name: str, days: int, limit: int = 50) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_time_series_sync, user_id, table_name, days, limit)

    def _fetch_time_series_sync(self, user_id: str, table_name: str, days: int, limit: int) -> List[Dict[str, Any]]:
        try:
            now = get_current_functional_time()
            lookback = now - timedelta(days=days)
            
            res = self.supabase.table(table_name) \
                .select("*") \
                .eq("user_id", user_id) \
                .gte("created_at", lookback.isoformat()) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return res.data if res.data else []
        except Exception as e:
            logger.error(f"Error fetching {table_name} history: {e}")
            return []
