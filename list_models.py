
import asyncio
import os
from google.genai import Client

# Load env safely
from dotenv import load_dotenv
load_dotenv()

async def list_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment.")
        return

    client = Client(api_key=api_key)
    
    try:
        # Pager object, need to iterate
        pager = await client.aio.models.list(config={"page_size": 100})
        async for model in pager:
            if "gemini" in model.name:
                print(f"- {model.name} (DisplayName: {model.display_name})")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
