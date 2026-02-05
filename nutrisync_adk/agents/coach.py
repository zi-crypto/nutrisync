import logging
import os
from google.adk.agents import Agent
from google.adk.tools import google_search
from google.genai import types
from ..tools.nutrition import log_meal, get_nutrition_history, calculate_macros
from ..tools.workouts import log_workout, get_workout_history, get_next_scheduled_workout
from ..tools.sleep import log_sleep, get_sleep_history
from ..tools.body_comp import log_body_comp, get_body_comp_history
from ..tools.context_notes import set_status_note, clear_status_note, get_active_notes_tool
from ..tools.charts import draw_chart
from ..tools.utils import get_health_scores
from ..tools.google_fit import get_fit_workouts, get_fit_sleep

logger = logging.getLogger(__name__)

def load_system_prompt() -> str:
    # Load the system prompt from file
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'system.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading system prompt: {e}")
        return "You are a helpful NutriSync coach."

# Define the agent with tools bound
coach_agent = Agent(
    name="coach_agent",
    model="gemini-flash-latest", 
    generate_content_config={"temperature": 0.2},
    instruction=load_system_prompt(), # Initial static prompt, will be overridden/appended dynamically in runner
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
        # google_search,  # Built-in ADK tool for real-time search (Incompatible with tools in Gemini 1.5)
        get_fit_workouts,  # Google Fit workout sync
        get_fit_sleep  # Google Fit sleep sync
    ],
    description="Main coach agent handling nutrition, workout, sleep, body comp, and context notes logic."
)
