import uvicorn
import os
import sys
import asyncio

# Ensure the project root is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    print("Starting NutriSync ADK Server...")
    print("Open http://localhost:8000 in your browser.")
    
    # Use 'nutrisync_adk.main:app'
    uvicorn.run("nutrisync_adk.main:app", host="127.0.0.1", port=8000, reload=True)
