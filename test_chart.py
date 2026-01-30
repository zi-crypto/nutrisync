"""Quick test for draw_chart tool"""
import base64
import sys
sys.stdout.reconfigure(encoding='utf-8')

from nutrisync_adk.tools.charts import draw_chart

# Test chart config with NEON colors
test_config = {
    "type": "line",
    "data": {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "datasets": [{
            "label": "Sleep Hours",
            "data": [6, 5, 7, 6.5, 8],
            "borderColor": "#00ffff",  # Neon cyan
            "backgroundColor": "rgba(0, 255, 255, 0.2)",
            "fill": True,
            "tension": 0.3,
            "borderWidth": 2
        }]
    },
    "options": {
        "plugins": {
            "title": {"display": True, "text": "Sleep This Week"}
        }
    }
}

# Call the tool
result = draw_chart(chart_config=test_config, caption="Your sleep rollercoaster!")

print(f"Success: {result.get('success')}")
print(f"Caption: {result.get('caption')}")

if result.get("success"):
    # Save the image to verify it works
    image_data = base64.b64decode(result["image_base64"])
    with open("test_chart.png", "wb") as f:
        f.write(image_data)
    print(f"Chart saved to test_chart.png ({len(image_data)} bytes)")
else:
    print(f"Error: {result.get('error')}")
