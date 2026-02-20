import asyncio
from google.adk.agents import Agent
from google.adk.tools import google_search
import os
from dotenv import load_dotenv

load_dotenv()

async def test_search():
    agent = Agent(
        name="test_agent",
        model="gemini-1.5-flash",
        tools=[google_search]
    )
    
    async for event in agent.run_async(new_message="Search google for the current weather in New York"):
        if getattr(event, 'is_final_response', False):
            print(event.content.parts[0].text)
        elif getattr(event, 'content', None) and event.content.parts:
            for part in event.content.parts:
                print(part)

if __name__ == "__main__":
    asyncio.run(test_search())
