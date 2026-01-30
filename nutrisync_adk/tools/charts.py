import logging
import json
import base64
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

QUICKCHART_API_URL = "https://quickchart.io/chart"

def draw_chart(chart_config: Dict[str, Any], caption: str = "") -> Dict[str, Any]:
    """
    Generates a chart image using QuickChart.io API from a full Chart.js configuration.
    
    Args:
        chart_config: A complete Chart.js configuration object. Must include:
            - type: Chart type ("line", "bar", "pie", "doughnut", "radar", etc.)
            - data: Object with labels and datasets
            - options: (optional) Chart.js options for customization
        caption: A witty caption to accompany the chart image.
    
    Returns:
        A dictionary with:
        - success: Boolean indicating if chart was generated
        - image_base64: Base64-encoded PNG image (if successful)
        - caption: The caption for the chart
        - error: Error message (if failed)
    
    Example chart_config:
    {
        "type": "line",
        "data": {
            "labels": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "datasets": [{
                "label": "Sleep Hours",
                "data": [6, 5, 7, 6.5, 8],
                "borderColor": "rgba(75, 192, 192, 1)",
                "fill": false
            }]
        },
        "options": {
            "plugins": {
                "title": {"display": true, "text": "Sleep This Week"}
            }
        }
    }
    """
    try:
        # Validate required fields
        if not isinstance(chart_config, dict):
            return {
                "success": False,
                "error": "chart_config must be a dictionary/object"
            }
        
        if "type" not in chart_config:
            return {
                "success": False,
                "error": "chart_config must include 'type' (e.g., 'line', 'bar', 'pie')"
            }
        
        if "data" not in chart_config:
            return {
                "success": False,
                "error": "chart_config must include 'data' with labels and datasets"
            }
        
        # Inject dark mode / neon defaults if not specified
        if "options" not in chart_config:
            chart_config["options"] = {}
        
        options = chart_config["options"]
        
        # Default plugin options for dark mode
        if "plugins" not in options:
            options["plugins"] = {}
        
        plugins = options["plugins"]
        
        # Legend styling (white text on dark bg)
        if "legend" not in plugins:
            plugins["legend"] = {}
        if "labels" not in plugins["legend"]:
            plugins["legend"]["labels"] = {"color": "#ffffff"}
        
        # Title styling
        if "title" in plugins and "color" not in plugins["title"]:
            plugins["title"]["color"] = "#ffffff"
        
        # Axis styling for dark mode
        if "scales" not in options:
            options["scales"] = {}
        
        for axis in ["x", "y"]:
            if axis not in options["scales"]:
                options["scales"][axis] = {}
            axis_opts = options["scales"][axis]
            if "ticks" not in axis_opts:
                axis_opts["ticks"] = {}
            if "color" not in axis_opts["ticks"]:
                axis_opts["ticks"]["color"] = "#aaaaaa"
            if "grid" not in axis_opts:
                axis_opts["grid"] = {}
            if "color" not in axis_opts["grid"]:
                axis_opts["grid"]["color"] = "rgba(255, 255, 255, 0.1)"
        
        # Build payload for QuickChart API
        payload = {
            "chart": chart_config,
            "width": 800,
            "height": 400,
            "backgroundColor": "#1a1a2e",  # Dark mode background
            "format": "png"
        }
        
        # Make synchronous request to QuickChart
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                QUICKCHART_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                # Encode image as base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                
                logger.info(f"Chart generated successfully ({len(response.content)} bytes)")
                
                return {
                    "success": True,
                    "image_base64": image_base64,
                    "caption": caption,
                    "message": "Chart generated successfully. The image will be sent separately."
                }
            else:
                error_msg = f"QuickChart API error: {response.status_code} - {response.text[:200]}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
                
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in chart_config: {e}")
        return {
            "success": False,
            "error": f"Invalid JSON format: {str(e)}"
        }
    except httpx.TimeoutException:
        logger.error("QuickChart API timeout")
        return {
            "success": False,
            "error": "Chart generation timed out. Try a simpler chart."
        }
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return {
            "success": False,
            "error": f"Chart generation failed: {str(e)}"
        }
