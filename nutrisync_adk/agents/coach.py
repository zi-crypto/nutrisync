import logging
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.genai import types
from ..tools.nutrition import log_meal, get_nutrition_history, calculate_macros
from ..tools.workouts import log_workout, get_workout_history, get_next_scheduled_workout
from ..tools.sleep import log_sleep, get_sleep_history
from ..tools.body_comp import log_body_comp, get_body_comp_history
from ..tools.context_notes import set_status_note, clear_status_note, get_active_notes_tool
from ..tools.charts import draw_chart
from ..tools.web_search import web_search
from ..tools.utils import get_health_scores

logger = logging.getLogger(__name__)

# Agent config — instruction is set by the runner's InstructionProvider callback.
# This object serves as a static config holder for model, tools, and description.
coach_agent = Agent(
    name="coach_agent",
    model="gemini-flash-latest",
    generate_content_config={"temperature": 0.2},
    instruction="You are a helpful NutriSync coach.",  # Placeholder — overridden by InstructionProvider in runner
    tools=[
        log_meal,
        get_nutrition_history,
        calculate_macros,
        log_workout,
        get_workout_history,
        get_next_scheduled_workout,
        get_health_scores,
        log_sleep,
        get_sleep_history,
        log_body_comp,
        get_body_comp_history,
        set_status_note,
        clear_status_note,
        get_active_notes_tool,
        draw_chart,
        web_search,
    ],
    description="Main coach agent handling nutrition, workout, sleep, body comp, context notes logic, and up-to-date internet searches."
)
