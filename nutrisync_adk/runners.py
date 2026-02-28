import logging
import json
import asyncio
import base64
import os
import time
from typing import Dict, Any, Optional

from google.adk.sessions import DatabaseSessionService
from google.adk.runners import Runner
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types
from dotenv import load_dotenv

from .agents.coach import coach_agent
from .services.local_context import ContextService
from .services.history_service import HistoryService
from .services.analytics import capture as posthog_capture
from .tools.utils import get_supabase_client
from .user_context import current_user_id

load_dotenv()

logger = logging.getLogger(__name__)

# ── Prompt Template ──────────────────────────────────────────────────────────
_PROMPT_TEMPLATE: str = ""

def _load_prompt_template() -> str:
    """Load the system prompt template once at module import time."""
    global _PROMPT_TEMPLATE
    if not _PROMPT_TEMPLATE:
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'system.md')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                _PROMPT_TEMPLATE = f.read()
        except Exception as e:
            logger.error(f"Error loading system prompt template: {e}")
            _PROMPT_TEMPLATE = "You are a helpful NutriSync coach."
    return _PROMPT_TEMPLATE


# ── InstructionProvider ──────────────────────────────────────────────────────
async def _build_instruction(ctx: ReadonlyContext) -> str:
    """
    ADK InstructionProvider callback — called per-request with the
    request-scoped ReadonlyContext. Reads pre-populated session.state
    values and injects them into the static prompt template.
    """
    template = _load_prompt_template()

    # Read pre-populated state (set in process_message before run_async)
    user_profile = ctx.state.get("user_profile", "{}")
    daily_totals = ctx.state.get("daily_totals", "{}")
    current_time = ctx.state.get("current_time", "Unknown")
    active_notes = ctx.state.get("active_notes", "None")
    equipment_list = ctx.state.get("equipment_list", "None")
    one_rm_records = ctx.state.get("one_rm_records", "None")
    workout_plan = ctx.state.get("workout_plan", "None")
    split_structure = ctx.state.get("split_structure", "No active split")

    # DEBUG: Log all state keys and equipment value
    all_keys = list(ctx.state.keys()) if hasattr(ctx.state, 'keys') else "NOT A DICT"
    logger.info(f"[_build_instruction] State keys: {all_keys}")
    logger.info(f"[_build_instruction] equipment_list value: '{equipment_list}'")

    # Manually substitute our known placeholders.
    # We do NOT use str.format() because the prompt contains literal {braces}
    # in JSON examples and other non-state contexts.
    result = template
    result = result.replace("{user_profile}", user_profile)
    result = result.replace("{daily_totals}", daily_totals)
    result = result.replace("{current_time}", current_time)
    result = result.replace("{active_notes}", active_notes)
    result = result.replace("{equipment_list}", equipment_list)
    result = result.replace("{one_rm_records}", one_rm_records)
    result = result.replace("{split_structure}", split_structure)
    result = result.replace("{workout_plan}", workout_plan)

    return result


# ── Database URL ─────────────────────────────────────────────────────────────
def _get_db_url() -> str:
    """Build the asyncpg connection URL for DatabaseSessionService."""
    raw_url = os.getenv("SUPABASE_DB_URL", "")
    if not raw_url:
        raise ValueError("SUPABASE_DB_URL must be set in .env")
    # Convert postgresql:// to postgresql+asyncpg://
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def _create_session_service() -> DatabaseSessionService:
    """Create DatabaseSessionService with asyncpg-compatible settings.
    
    Uses connect_args to disable prepared statement caching, which is
    required when connecting via Supabase's Supavisor connection pooler.
    """
    return DatabaseSessionService(
        db_url=_get_db_url(),
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        },
    )


# ── Runner ───────────────────────────────────────────────────────────────────
APP_NAME = "NutriSync"

class NutriSyncRunner:
    def __init__(self):
        self.supabase = get_supabase_client()

        # Services (still needed for context fetching and dual-write to chat_history)
        self.history_service = HistoryService(self.supabase)
        self.context_service = ContextService(self.supabase)

        # ADK DatabaseSessionService — persists sessions in Supabase PostgreSQL
        self.session_service = _create_session_service()

        # Static Agent — instruction is an InstructionProvider callback,
        # so the Agent object is immutable config while instructions are
        # built dynamically per-request from session.state.
        self.agent = Agent(
            name=coach_agent.name,
            model=coach_agent.model,
            generate_content_config=coach_agent.generate_content_config,
            instruction=_build_instruction,
            tools=coach_agent.tools,
            description=coach_agent.description,
        )

        # Static Runner — shared across all requests
        self.runner = Runner(
            agent=self.agent,
            session_service=self.session_service,
            app_name=APP_NAME,
        )

        # Per-user asyncio locks to prevent stale session errors on rapid messages
        self._user_locks: Dict[str, asyncio.Lock] = {}

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def _get_or_create_session(self, user_id: str, state: dict = None):
        """Get existing session for user, or create a new one."""
        session_id = f"session_{user_id}"
        session = await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            session = await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state=state or {},
            )
        return session

    async def process_message(self, user_id: str, text: str, image_bytes: bytes = None, mime_type: str = None) -> dict:
        """Process a user message and return the response."""
        try:
            # 0. Set Context Variable for Tools
            token = current_user_id.set(user_id)
            try:
                # Acquire per-user lock to prevent stale session errors
                async with self._get_user_lock(user_id):
                    return await self._process_message_impl(user_id, text, image_bytes, mime_type)
            finally:
                current_user_id.reset(token)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "text": "Error: Something went wrong in the cognitive engine.",
                "chart": None,
                "message_id": None,
            }

    async def _process_message_impl(self, user_id: str, text: str, image_bytes: bytes = None, mime_type: str = None) -> dict:
        """Internal implementation — runs under per-user lock."""
        process_start = time.time()

        # 1. Fetch Dynamic Context (Parallel DB queries inside ContextService)
        ctx_start = time.time()
        context_data = await self.context_service.get_user_context(user_id)
        ctx_duration_ms = int((time.time() - ctx_start) * 1000)

        # 2. Prepare session state with fresh context
        state_updates = {
            "user_profile": json.dumps(context_data.get("profile", {}), indent=2, default=str),
            "daily_totals": json.dumps(context_data.get("daily_totals", {}), indent=2, default=str),
            "current_time": context_data.get("current_time", "Unknown"),
            "active_notes": self._format_notes(context_data.get("active_notes", [])),
            "equipment_list": ", ".join(context_data.get("equipment_list", [])) or "None specified",
            "one_rm_records": json.dumps(context_data.get("one_rm_records", []), indent=2, default=str) if context_data.get("one_rm_records") else "None recorded",
            "split_structure": self._format_split_structure(context_data.get("split_structure", [])),
            "workout_plan": json.dumps(context_data.get("workout_plan", []), indent=2, default=str) if context_data.get("workout_plan") else "No plan generated yet",
        }
        logger.info(f"Equipment context for {user_id}: {state_updates['equipment_list']}")
        logger.info(f"1RM records for {user_id}: {state_updates['one_rm_records'][:100]}")
        logger.info(f"Workout plan for {user_id}: {state_updates['workout_plan'][:100]}")

        # 3. Get or create session (state_updates applied via state_delta in run_async)
        session = await self._get_or_create_session(user_id, state=state_updates)

        # 4. Dual-write: Save User Message to chat_history table (for frontend)
        img_b64 = None
        if image_bytes and mime_type:
            img_b64 = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

        await self.history_service.add_message(user_id, "user", text, image_data=img_b64)

        # 5. Build message parts
        parts = [types.Part(text=text)] if text else []
        if image_bytes and mime_type:
            logger.info(f"Appending image ({len(image_bytes)} bytes).")
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        if not parts:
            parts = [types.Part(text="[Empty Message]")]

        user_msg = types.Content(role='user', parts=parts)

        # 6. Run agent with reused runner + session
        final_response_text = ""
        collected_tool_calls = []
        chart_data = None
        tool_call_count = 0
        tool_names_used = []

        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=user_msg,
            state_delta=state_updates,
        ):
            # Capture tool calls from events for logging
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_call_count += 1
                        tool_names_used.append(part.function_call.name)
                        collected_tool_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {}
                        })
                        # ── PostHog: Track each AI tool invocation ──
                        posthog_capture(user_id, "ai_tool_called", {
                            "tool_name": part.function_call.name,
                            "has_args": bool(part.function_call.args),
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

        # 7. Dual-write: Save Model Response to chat_history table (for frontend)
        model_message_id = None
        if final_response_text:
            model_message_id = await self.history_service.add_message(
                user_id,
                "model",
                final_response_text,
                tool_calls=collected_tool_calls if collected_tool_calls else None
            )

        # ── PostHog: Track full agent run metrics ──
        total_duration_ms = int((time.time() - process_start) * 1000)
        posthog_capture(user_id, "ai_agent_run_completed", {
            "context_load_ms": ctx_duration_ms,
            "total_duration_ms": total_duration_ms,
            "tool_call_count": tool_call_count,
            "tools_used": tool_names_used,
            "has_image_input": image_bytes is not None,
            "has_chart_output": chart_data is not None,
            "response_length": len(final_response_text),
        })

        return {
            "text": final_response_text,
            "chart": chart_data,
            "message_id": model_message_id,
        }

    @staticmethod
    def _format_notes(notes: list) -> str:
        """Format active notes list into a string for the prompt."""
        if not notes:
            return "None"
        return "\n".join(f"- {note}" for note in notes)

    @staticmethod
    def _format_split_structure(split_items: list) -> str:
        """Format split_items list into a readable string for the prompt.
        
        Example output:
            Split: PPL
            1. Push
            2. Pull
            3. Legs
            4. Rest
        """
        if not split_items:
            return "No active split"
        split_name = split_items[0].get("split_name", "Custom Split") if split_items else ""
        lines = [f"Split: {split_name}"]
        for item in split_items:
            lines.append(f"{item['position']}. {item['day']}")
        return "\n".join(lines)
