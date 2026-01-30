try:
    from google.adk.model import GoogleModelSettings
    from google.adk.agents import Agent
    from google.genai import types
    print("Environment Verification: SUCCESS - All modules imported.")
except ImportError as e:
    print(f"Environment Verification: FAILED - {e}")
except Exception as e:
    print(f"Environment Verification: ERROR - {e}")
