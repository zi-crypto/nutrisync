import logging
import json
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types
from .agents.coach import coach_agent, load_system_prompt
from .managers.history import HistoryManager
from .managers.context import ContextManager
from .tools.utils import get_supabase_client

logger = logging.getLogger(__name__)

class NutriSyncRunner:
    def __init__(self):
        self.supabase = get_supabase_client()
        self.history_manager = HistoryManager(self.supabase)
        self.context_manager = ContextManager(self.supabase)
        self.session_service = InMemorySessionService()
        
        # We hold the base agent instructions to format dynamically
        self.base_system_prompt = load_system_prompt()

    async def initialize_session(self, user_id: str):
        # In ADK, sessions might just be ID containers or state. 
        # We use a persistent ID based on user_id to keep it simple, 
        # or generate a new one per conversation thread. 
        # For a Telegram bot, usually one long running session per user.
        # But ADK In-Memory session might clear on restart. 
        # So we trust HistoryManager for persistence and just use user_id as session_id effectively.
        session = await self.session_service.create_session(
            app_name="NutriSync",
            user_id=user_id
        )
        return session

    async def process_message(self, user_id: str, text: str, image_bytes: bytes = None, mime_type: str = None) -> dict:
        """
        Process a user message and return the response.
        
        Returns:
            dict with:
            - text: The agent's text response
            - chart: Optional dict with {"image_base64": str, "caption": str} if a chart was generated
        """
        try:
            # 1. Fetch Dynamic Context
            context_data = await self.context_manager.get_user_context(user_id)
            
            # 4. Load History & Format for Prompt Injection
            history = await self.history_manager.get_recent_history(user_id, limit=20)
            
            history_text_lines = []
            for msg in history:
                role = msg.get("role")
                content = msg.get("content")
                if role and content:
                    label = "User" if role == "user" else "Coach"
                    history_text_lines.append(f"{label}: {content}")
            
            # Join with newlines
            chat_history_str = "\n".join(history_text_lines)

            # 2. Format System Prompt with History
            # Convert list of notes to bullet string
            active_notes_list = context_data.get("active_notes", [])
            active_notes_str = "\n".join([f"- {note}" for note in active_notes_list]) if active_notes_list else "None"

            dynamic_instruction = self.base_system_prompt.format(
                user_profile=json.dumps(context_data.get("profile", {}), indent=2),
                daily_totals=json.dumps(context_data.get("daily_totals", {}), indent=2),
                active_notes=active_notes_str,
                chat_history=chat_history_str,
                current_time=context_data.get("current_time", "Unknown")
            )
            
            # 3. Create Agent with Dynamic Instruction
            from google.adk.agents import Agent
            run_agent = Agent(
                name=coach_agent.name,
                model=coach_agent.model,
                generate_content_config=coach_agent.generate_content_config,  # Pass the config dict directly
                instruction=dynamic_instruction, # INJECTED HERE
                tools=coach_agent.tools,
                description=coach_agent.description
            )
            
            session = await self.initialize_session(user_id)
            
            # 5. Run Agent
            runner = Runner(agent=run_agent, session_service=self.session_service, app_name="NutriSync")
            
            # Save User Message to DB (Async ideally)
            await self.history_manager.add_message(user_id, "user", text)
            
            # Prepare Message Parts
            parts = [types.Part(text=text)] if text else []
            
            if image_bytes and mime_type:
                logger.info(f"Appending image ({len(image_bytes)} bytes) to message parts.")
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
            
            # If explicit text was empty but image exists, prompt needs something? 
            # ADK handles multimodal content.
            if not parts:
                parts = [types.Part(text="[Empty Message]")]

            user_msg = types.Content(role='user', parts=parts)
            
            final_response_text = ""
            collected_tool_calls = []  # Track tool calls during execution
            chart_data = None  # Track chart if generated
            
            # Run
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=user_msg
            ):
                # Capture tool calls from events
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            tool_call_info = {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args) if part.function_call.args else {}
                            }
                            collected_tool_calls.append(tool_call_info)
                        if hasattr(part, 'function_response') and part.function_response:
                            response_data = part.function_response.response
                            
                            # Check if this is a chart response
                            if part.function_response.name == "draw_chart":
                                if isinstance(response_data, dict) and response_data.get("success"):
                                    chart_data = {
                                        "image_base64": response_data.get("image_base64"),
                                        "caption": response_data.get("caption", "")
                                    }
                                    logger.info("Chart generated successfully, will be sent as photo")
                            
                            # Track responses (truncate for history)
                            tool_response_info = {
                                "name": part.function_response.name,
                                "response": str(response_data)[:500]  # Truncate long responses
                            }
                            collected_tool_calls.append(tool_response_info)
                
                # We need to capture the model's response
                if event.is_final_response():
                    final_response_text = event.content.parts[0].text
                    
            # 6. Save Model Response to DB (with tool calls if any)
            if final_response_text:
                tool_calls_data = collected_tool_calls if collected_tool_calls else None
                await self.history_manager.add_message(user_id, "model", final_response_text, tool_calls=tool_calls_data)
            
            # Return structured response
            return {
                "text": final_response_text,
                "chart": chart_data  # None if no chart was generated
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "text": "Error: Something went wrong in the cognitive engine.",
                "chart": None
            }

