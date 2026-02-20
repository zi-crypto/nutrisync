import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def get_weather(location: str) -> str:
    """Gets the weather for a location."""
    return "Sunny"

client = genai.Client()

try:
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents='What is the weather in New York and also who won the super bowl?',
        config=types.GenerateContentConfig(
            tools=[get_weather, {"google_search": {}}],
            temperature=0.2
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", str(e))
