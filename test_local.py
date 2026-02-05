import asyncio
import logging
import os
from nutrisync_adk.runners import NutriSyncRunner
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    print("Initializing NutriSync Runner...")
    try:
        runner = NutriSyncRunner()
        
        user_id = "test_user_123" 
        # Ideally this user_id should exist in Supabase 'auth.users' if referenced by FK, 
        # but 'chat_history' table has 'user_id uuid references auth.users'.
        # So we MUST use a valid UUID from auth.users. 
        # The legacy system used 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11' or similar.
        # I will try to use the one from GetHealthScores.json as a fallback default.
        valid_user_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11" 
        
        print(f"Using User ID: {valid_user_id}")
        
        while True:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit']:
                break
            
            image_bytes = None
            mime_type = None
            text_content = user_input
            
            # Local Image Injection Protocol
            # Syntax: /img "path/to/image.jpg" optional caption
            if user_input.strip().startswith("/img "):
                try:
                    parts = user_input.split(" ", 2)
                    # parts[0] is /img
                    # parts[1] is the path (might be quoted)
                    img_path_raw = parts[1]
                    caption = parts[2] if len(parts) > 2 else ""
                    
                    # Remove quotes
                    img_path = img_path_raw.strip('"').strip("'")
                    
                    if os.path.exists(img_path):
                        with open(img_path, "rb") as img_file:
                            image_bytes = img_file.read()
                            
                        # Guess mime
                        if img_path.lower().endswith(".png"):
                            mime_type = "image/png"
                        elif img_path.lower().endswith(".jpg") or img_path.lower().endswith(".jpeg"):
                            mime_type = "image/jpeg"
                        elif img_path.lower().endswith(".webp"):
                            mime_type = "image/webp"
                        else:
                            mime_type = "image/jpeg"
                            
                        print(f"[System] Loaded image: {img_path} ({len(image_bytes)} bytes)")
                        text_content = caption or "Analyze this image."
                    else:
                        print(f"[System] Error: File not found at {img_path}")
                        continue
                        
                except Exception as e:
                    print(f"[System] Error processing image command: {e}")
                    continue

            print("Coach is thinking...")
            response = await runner.process_message(valid_user_id, text_content, image_bytes, mime_type)
            print(f"Coach: {response}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
