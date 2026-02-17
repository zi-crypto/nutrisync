import logging
import os
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

from .runners import NutriSyncRunner

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NutriSync")

app = FastAPI()
runner = NutriSyncRunner()

TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Using Bot Token as secret for now, or X-Telegram-Bot-Api-Secret-Token

class TelegramUpdate(BaseModel):
    update_id: int
    message: dict = None

@app.on_event("startup")
async def startup_event():
    logger.info("NutriSync ADK is starting up...")

@app.post("/webhook")
async def telegram_webhook(update: TelegramUpdate, request: Request, background_tasks: BackgroundTasks):
    # Security Check
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    # if secret_token != TELEGRAM_SECRET_TOKEN:
    #     logger.warning("Unauthorized webhook attempt")
    #     raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not update.message:
        return {"status": "ignored", "reason": "no_message"}

    user_id = str(update.message.get("from", {}).get("id"))
    text = update.message.get("text", "") or update.message.get("caption", "")
    message_id = update.message.get("message_id")
    
    # Idempotency Check
    logger.info(f"Received message {message_id} from {user_id}")

    image_data = None
    mime_type = None

    # Handle Photos
    if update.message.get("photo"):
        try:
            # Get largest photo
            photos = update.message.get("photo")
            largest_photo = photos[-1] # Last is usually largest
            file_id = largest_photo.get("file_id")
            
            # Use httpx to get file path
            import httpx
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            
            # 1. Get File Path
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                if res.status_code == 200:
                    file_path = res.json()["result"]["file_path"]
                    
                    # 2. Download Content
                    image_res = await client.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}")
                    if image_res.status_code == 200:
                        image_data = image_res.content
                        mime_type = "image/jpeg"
                        logger.info("Successfully downloaded photo.")
        
        except Exception as e:
            logger.error(f"Error downloading photo: {e}")

    # Process
    response = await runner.process_message(user_id, text, image_bytes=image_data, mime_type=mime_type)
    
    if response:
        # TODO: Send response back to Telegram via API
        logger.info(f"Agent Response: {response}")

    return {"status": "ok"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Chat API
class ChatRequest(BaseModel):
    message: str
    guest_id: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Process
    response = await runner.process_message(request.guest_id, request.message)
    return response

# Serve Static Files (Frontend)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount static directory
app.mount("/static", StaticFiles(directory="nutrisync_adk/static"), name="static")

# Serve index.html at root
@app.get("/")
async def serve_index():
    return FileResponse("nutrisync_adk/static/index.html")
