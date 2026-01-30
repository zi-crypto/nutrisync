import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    from nutrisync_adk.agents.coach import coach_agent
    print("SUCCESS: coach_agent instantiated.")
    print(f"Config: {coach_agent.generate_content_config}")
except Exception as e:
    print(f"FAILED: {e}")
