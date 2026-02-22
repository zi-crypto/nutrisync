from dotenv import load_dotenv

load_dotenv()

from nutrisync_adk.tools.web_search import web_search

def test_tavily():
    print("Testing Tavily Web Search...")
    query = "is monk fruit keto friendly?"
    print(f"\nQuery: {query}")
    
    result = web_search(query)
    print("\nResult:")
    print("-" * 40)
    print(result)
    print("-" * 40)

if __name__ == "__main__":
    test_tavily()
