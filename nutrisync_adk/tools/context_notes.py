import logging
import uuid
from typing import Optional, List, Dict, Any
from google.adk.tools import BaseTool
from ..tools.utils import get_supabase_client, calculate_log_timestamp
from ..user_context import current_user_id

logger = logging.getLogger(__name__)

def set_status_note(
    note_content: str,
    confirmation_required: bool = True
) -> str:
    """
    Sets a persistent context note (e.g. "Fasting for Ramadan", "Sick with Flu").
    This note will remain active and influence ALL future agent responses until cleared.
    
    Args:
        note_content: The content of the note. Be specific.
        confirmation_required: Signal for confirmation.
    """
    try:
        user_id = current_user_id.get()
        if not user_id: return "Error: No user context."

        supabase = get_supabase_client()
        
        data = {
            "user_id": user_id,
            "note_content": note_content,
            "is_active": True
        }
        
        # We just insert a new active note. 
        # (Optionally we could deactivate old conflicting ones, but stackable notes are fine).
        response = supabase.table("persistent_context").insert(data).execute()
        
        if response.data:
            return f"Successfully set status: '{note_content}'. I will keep this in mind."
        else:
            return "Error: Failed to set status."

    except Exception as e:
        logger.error(f"Error setting status: {e}")
        return f"Error setting status: {str(e)}"

def clear_status_note(
    note_id: Optional[str] = None,
    clear_all: bool = False,
    confirmation_required: bool = True
) -> str:
    """
    Clears/Deactivates a persistent context note.
    
    Args:
        note_id: The specific ID of the note to clear (if known).
        clear_all: If True, clears ALL active notes.
    """
    try:
        user_id = current_user_id.get()
        if not user_id: return "Error: No user context."

        supabase = get_supabase_client()
        
        query = supabase.table("persistent_context").update({"is_active": False}).eq("user_id", user_id)
        
        if clear_all:
             response = query.eq("is_active", True).execute()
             return "Successfully cleared all active status notes."
        
        if note_id:
            response = query.eq("id", note_id).execute()
            return f"Successfully cleared note {note_id}."
            
        return "Error: Must specify note_id or clear_all=True."

    except Exception as e:
        logger.error(f"Error clearing status: {e}")
        return f"Error clearing status: {str(e)}"

def get_active_notes_tool() -> List[Dict[str, Any]]:
    """
    Fetches currently active persistent notes. 
    (Mostly for internal use or debugging, the ContextManager does this automatically).
    """
    try:
        user_id = current_user_id.get()
        if not user_id: return []

        supabase = get_supabase_client()
        response = supabase.table("persistent_context") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .order("created_at", desc=True) \
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching active notes: {e}")
        return []
