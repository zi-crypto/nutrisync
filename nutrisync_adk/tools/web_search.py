import os
import logging
from typing import Dict, Any
from tavily import TavilyClient
import httpx

logger = logging.getLogger(__name__)

def web_search(query: str) -> str:
    """
    Searches the live internet for up-to-date information, news, facts, and specific nutrition data 
    that might be missing from the static database. 
    Use this tool whenever you need to verify a fact, look up a specific branded food product, 
    or check current events.
    
    Args:
        query: The search query, e.g., "how much protein in 100g of Fage Total 0% greek yogurt?"
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY is not set. Web search is currently unavailable."
        
    try:
        tavily_client = TavilyClient(api_key=api_key)
        
        # We request an AI-generated answer specifically optimized for LLM consumption
        response = tavily_client.search(
            query=query,
            search_depth="basic",
            include_answer=True,
            include_images=False,
            include_raw_content=False,
            max_results=3
        )
        
        answer = response.get("answer", "")
        results = response.get("results", [])
        
        output = []
        if answer:
            output.append(f"AI Summary: {answer}\n")
            
        if results:
            output.append("Search Results:")
            for i, res in enumerate(results, 1):
                output.append(f"{i}. Title: {res.get('title')}")
                output.append(f"   URL: {res.get('url')}")
                output.append(f"   Snippet: {res.get('content')}\n")
                
        if not output:
            return "No useful results found for this query."
            
        return "\n".join(output)
        
    except Exception as e:
        logger.error(f"Error connecting to Tavily search service: {e}")
        return f"Error executing web search: {str(e)}"
