import logging
import json
import base64
from typing import Dict, Any, Optional
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.agents import Agent
from google.genai import types

from .agents.coach import coach_agent
from .services.local_context import ContextService
from .services.history_service import HistoryService
from .services.prompt_service import PromptService
from .tools.utils import get_supabase_client
from .user_context import current_user_id  # Initialize this context var

import os

logger = logging.getLogger(__name__)

class NutriSyncRunner:
    def __init__(self):
        self.supabase = get_supabase_client()
        
        # Inject Services
        self.history_service = HistoryService(self.supabase)
        self.context_service = ContextService(self.supabase)
        self.prompt_service = PromptService(os.path.join(os.path.dirname(__file__), 'prompts'))
        
        self.session_service = InMemorySessionService()

    async def initialize_session(self, user_id: str):
        # We rely on persistent DB history, but ADK needs a session object.
        session = await self.session_service.create_session(
            app_name="NutriSync",
            user_id=user_id
        )
        return session

    async def process_message(self, user_id: str, text: str, image_bytes: bytes = None, mime_type: str = None) -> dict:
        """
        Process a user message and return the response.
        """
        try:
            # 0. Set Context Variable for Tools
            token = current_user_id.set(user_id)
            
            try:
                # 1. Fetch Dynamic Context & History in Parallel? 
                # Actually, context fetching itself is parallelized inside ContextService.
                # We can fetch history concurrently with context if we want max speed.
                import asyncio
                
                # Create Tasks
                task_context = self.context_service.get_user_context(user_id)
                task_history = self.history_service.get_recent_chat_history(user_id, limit=20)
                
                # Execute concurrently
                results = await asyncio.gather(task_context, task_history, return_exceptions=True)
                
                context_data = results[0] if not isinstance(results[0], Exception) else {}
                history_data = results[1] if not isinstance(results[1], Exception) else []
                
                if isinstance(results[0], Exception): logger.error(f"Context fetch failed: {results[0]}")
                if isinstance(results[1], Exception): logger.error(f"History fetch failed: {results[1]}")

                # 2. Format Chat History String
                history_str = self._format_history_for_prompt(history_data)

                # 3. Render System Prompt
                dynamic_instruction = self.prompt_service.render_system_prompt(context_data, history_str)
                
                # 4. Create Agent Instance
                run_agent = Agent(
                    name=coach_agent.name,
                    model=coach_agent.model,
                    generate_content_config=coach_agent.generate_content_config,
                    instruction=dynamic_instruction,
                    tools=coach_agent.tools,
                    description=coach_agent.description
                )
                
                session = await self.initialize_session(user_id)
                
                # 5. Run Runner
                runner = Runner(agent=run_agent, session_service=self.session_service, app_name="NutriSync")
                
                # Save User Message to DB
                # If image exists, we store it in the new image_data column
                img_b64 = None
                if image_bytes and mime_type:
                     img_b64 = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

                await self.history_service.add_message(user_id, "user", text, image_data=img_b64)
                
                # Build Message Parts
                parts = [types.Part(text=text)] if text else []
                if image_bytes and mime_type:
                    logger.info(f"Appending image ({len(image_bytes)} bytes).")
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
                
                if not parts:
                    parts = [types.Part(text="[Empty Message]")]

                user_msg = types.Content(role='user', parts=parts)
                
                final_response_text = ""
                collected_tool_calls = []
                chart_data = None
                
                async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=user_msg):
                    # Capture tool calls from events for logging
                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                collected_tool_calls.append({
                                    "name": part.function_call.name,
                                    "args": dict(part.function_call.args) if part.function_call.args else {}
                                })
                            if hasattr(part, 'function_response') and part.function_response:
                                response_val = part.function_response.response
                                tool_name = part.function_response.name
                                
                                # Chart Detection
                                if tool_name == "draw_chart" and isinstance(response_val, dict) and response_val.get("success"):
                                    chart_data = {
                                        "image_base64": response_val.get("image_base64"),
                                        "caption": response_val.get("caption", "")
                                    }
                                
                                # Log response (truncate unless chart/critical)
                                log_resp = response_val
                                if "draw_chart" not in tool_name:
                                    log_resp = str(response_val)[:500]
                                
                                collected_tool_calls.append({
                                    "name": tool_name,
                                    "response": log_resp
                                })
                    
                    if event.is_final_response():
                        final_response_text = event.content.parts[0].text
                
                # 6. Save Model Response
                if final_response_text:
                    await self.history_service.add_message(
                        user_id, 
                        "model", 
                        final_response_text, 
                        tool_calls=collected_tool_calls if collected_tool_calls else None
                    )
                
                return {
                    "text": final_response_text,
                    "chart": chart_data
                }
                
            finally:
                # Reset Context Var
                current_user_id.reset(token)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "text": "Error: Something went wrong in the cognitive engine.",
                "chart": None
            }

    def _format_history_for_prompt(self, history: list) -> str:
        lines = []
        from .tools.utils import CAIRO_TZ
        from datetime import datetime
        
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            created_at = msg.get("created_at")
            
            if role and content:
                label = "User" if role == "user" else "Coach"
                time_str = ""
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        dt_cairo = dt.astimezone(CAIRO_TZ)
                        time_str = f"[{dt_cairo.strftime('%Y-%m-%d %H:%M')}] "
                    except Exception:
                        pass
                lines.append(f"{time_str}{label}: {content}")
        return "\n".join(lines)

