import logging
import json
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

class PromptService:
    """
    Service for rendering system prompts using Jinja2.
    """
    
    def __init__(self, template_dir: str):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape()
        )
        
        # Add custom filters
        self.env.filters['json_indent'] = self._json_filter

    def _json_filter(self, value):
        return json.dumps(value, indent=2)

    def render_system_prompt(self, context_data: Dict[str, Any], chat_history_str: str) -> str:
        """
        Renders the 'system.j2' template with provided context.
        """
        try:
            template = self.env.get_template("system.j2")
            
            # Unpack context data safely
            profile = context_data.get("profile", {})
            daily_totals = context_data.get("daily_totals", {})
            active_notes = context_data.get("active_notes", [])
            current_time = context_data.get("current_time", "Unknown")
            
            return template.render(
                user_profile=profile,
                daily_totals=daily_totals,
                active_notes=active_notes,
                chat_history=chat_history_str,
                current_time=current_time
            )
        except Exception as e:
            logger.error(f"Error rendering system prompt: {e}")
            return "Error generating system prompt. Proceed with caution."
