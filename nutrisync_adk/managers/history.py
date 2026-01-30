import logging
from typing import List, Dict, Any
from supabase import Client

logger = logging.getLogger(__name__)

class HistoryManager:
    """
    Manages chat history persistence in Supabase.
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def get_recent_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches the last N messages for the user.
        """
        try:
            response = self.supabase.table("chat_history") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            # Reverse to get chronological order for the context window
            data = response.data or []
            return data[::-1]
            
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return []

    async def add_message(self, user_id: str, role: str, content: str, tool_calls: Dict = None):
        """
        Adds a message to the history.
        """
        try:
            data = {
                "user_id": user_id,
                "role": role,
                "content": content,
                "tool_calls": tool_calls
            }
            self.supabase.table("chat_history").insert(data).execute()
        except Exception as e:
            logger.error(f"Error saving message to history: {e}")
