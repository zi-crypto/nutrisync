import logging
import os
from typing import List, Optional
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

@app.on_event("startup")
async def startup_event():
    logger.info("NutriSync ADK is starting up...")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

# Chat API
# Chat API
from typing import Optional
import base64

class ChatRequest(BaseModel):
    message: str
    guest_id: str
    image: Optional[str] = None

class FeedbackRequest(BaseModel):
    message_id: int
    guest_id: str
    feedback_value: int
    feedback_comment: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    image_bytes = None
    mime_type = None

    if request.image:
        try:
            # Handle data URI scheme if present (e.g. data:image/jpeg;base64,....)
            if "," in request.image:
                header, encoded = request.image.split(",", 1)
                if ":" in header and ";" in header:
                    mime_type = header.split(":")[1].split(";")[0]
            else:
                encoded = request.image
                mime_type = "image/jpeg" # Fallback

            image_bytes = base64.b64decode(encoded)
        except Exception as e:
            logger.error(f"Failed to decode image: {e}")

    # Process
    response = await runner.process_message(request.guest_id, request.message, image_bytes=image_bytes, mime_type=mime_type)
    return response

@app.get("/api/history/{guest_id}")
async def get_history(guest_id: str, after: Optional[str] = None):
    # Fetch history
    history = await runner.history_service.get_recent_chat_history(guest_id, limit=50, after=after)
    return history

@app.post("/api/chat/feedback")
async def submit_feedback(request: FeedbackRequest):
    try:
        if len(request.feedback_comment.strip()) < 10:
            raise HTTPException(status_code=400, detail="Feedback comment must be at least 10 characters long.")
        
        if request.feedback_value not in (1, -1):
            raise HTTPException(status_code=400, detail="Feedback value must be 1 (like) or -1 (dislike).")
            
        data = {
            "message_id": request.message_id,
            "user_id": request.guest_id,
            "feedback_value": request.feedback_value,
            "feedback_comment": request.feedback_comment
        }
        
        # Upsert: On conflict with unique message_id, update the feedback fields
        # Note: supabase-py doesn't have a direct upsert that maps exactly to ON CONFLICT UPDATE without specifying the conflict fields if not PK,
        # but since message_id is the primary target of uniqueness for this, we can try insert/update logic
        
        # Check if exists
        existing = runner.supabase.table("message_feedback").select("id").eq("message_id", request.message_id).execute()
        
        if existing.data and len(existing.data) > 0:
            runner.supabase.table("message_feedback").update(data).eq("message_id", request.message_id).execute()
        else:
            runner.supabase.table("message_feedback").insert(data).execute()
            
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Profile API
class ProfileRequest(BaseModel):
    user_id: str
    name: str 
    gender: str
    dob: str
    height_cm: int
    weight_kg: float
    target_weight_kg: Optional[int] = None
    fitness_goal: str
    experience_level: str
    equipment_access: str
    workout_days_per_week: int
    typical_daily_calories: Optional[int] = None
    typical_diet_type: Optional[str] = None
    allergies: Optional[str] = None
    sport_type: Optional[str] = None
    split_schedule: Optional[List[str]] = None # List of day names e.g. ["Push", "Pull", "Legs"]

def calculate_targets(data: dict) -> dict:
    """
    Calculates daily calorie and macro targets based on user stats.
    """
    try:
        # 1. Parse Data
        weight = float(data.get('weight_kg', 70))
        height = int(data.get('height_cm', 175))
        age = 25 # Default
        if data.get('dob'):
            from datetime import datetime
            dob = datetime.strptime(data['dob'], '%Y-%m-%d')
            today = datetime.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
        gender = data.get('gender', 'Male')
        activity_days = int(data.get('workout_days_per_week', 3))
        goal = data.get('fitness_goal', 'Maintain')

        # 2. BMR (Mifflin-St Jeor)
        if gender == 'Male':
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
        else:
            bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

        # 3. TDEE (Activity Multiplier)
        # 1-2 days -> 1.2
        # 3-4 days -> 1.375
        # 5-6 days -> 1.55
        # 7 days -> 1.725
        if activity_days <= 2: multiplier = 1.2
        elif activity_days <= 4: multiplier = 1.375
        elif activity_days <= 6: multiplier = 1.55
        else: multiplier = 1.725
        
        tdee = bmr * multiplier

        # 4. Goal Adjustment
        if goal == 'Lose Weight':
            target_cals = int(tdee - 500)
            protein_g = 2.2 * weight
            fat_pct = 0.25
        elif goal == 'Build Muscle':
            target_cals = int(tdee + 300)
            protein_g = 2.0 * weight
            fat_pct = 0.25
        elif goal == 'Improve Endurance':
            target_cals = int(tdee + 200)
            protein_g = 1.6 * weight
            fat_pct = 0.20
        else: # Maintain / Default
            target_cals = int(tdee)
            protein_g = 1.6 * weight
            fat_pct = 0.30

        # Calculate Fats and Carbs based on percentages and remainder
        fats_cals = target_cals * fat_pct
        fats_g = fats_cals / 9
        
        protein_cals = protein_g * 4
        
        remaining_cals = target_cals - (protein_cals + fats_cals)
        carbs_g = max(0, remaining_cals / 4)

        return {
            "daily_calorie_target": int(target_cals),
            "daily_protein_target_gm": int(protein_g),
            "daily_fats_target_gm": int(fats_g),
            "daily_carbs_target_gm": int(carbs_g)
        }
    except Exception as e:
        logger.error(f"Error calculating macros: {e}")
        return {
            "daily_calorie_target": 2500,
            "daily_protein_target_gm": 150,
            "daily_fats_target_gm": 80,
            "daily_carbs_target_gm": 300
        }

@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    try:
        # Fetch Profile
        res = runner.supabase.table("user_profile").select("*").eq("user_id", user_id).execute()
        profile_data = {}
        if res.data:
            profile_data = res.data[0]
            
        # Fetch Active Split
        split_res = runner.supabase.table("workout_splits").select("id, name").eq("user_id", user_id).eq("is_active", True).execute()
        
        split_schedule = []
        if split_res.data:
            split_id = split_res.data[0]['id']
            # Fetch Items
            items_res = runner.supabase.table("split_items").select("workout_name").eq("split_id", split_id).order("order_index").execute()
            if items_res.data:
                split_schedule = [item['workout_name'] for item in items_res.data]
        
        profile_data['split_schedule'] = split_schedule
        return profile_data
        
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/profile")
async def update_profile(request: ProfileRequest):
    try:
        # Check if profile exists
        res = runner.supabase.table("user_profile").select("*").eq("user_id", request.user_id).execute()
        
        data = request.dict(exclude_unset=True)
        current_weight = data.get("weight_kg", None) # Don't pop, keep in data for profile update
        
        # Extract Split Schedule
        split_schedule = data.pop("split_schedule", None)
        
        # Calculate Targets
        targets = calculate_targets(data) 
        data.update(targets)

        # Force Target Weight to Current Weight if goal is Maintain
        if data.get('fitness_goal') == 'Maintain' and current_weight is not None:
            data['target_weight_kg'] = current_weight

        if res.data:
            # Update
            # Check if starting_weight_kg is set, if not and we have a weight, set it (for legacy)
            if current_weight and not res.data[0].get('starting_weight_kg'):
                 data['starting_weight_kg'] = current_weight
            
            runner.supabase.table("user_profile").update(data).eq("user_id", request.user_id).execute()
        else:
            # Insert
            data["user_id"] = request.user_id
            if current_weight:
                data['starting_weight_kg'] = current_weight
            runner.supabase.table("user_profile").insert(data).execute()
            
        # If weight provided, ALSO log it to body_composition_logs for history
        if current_weight:
            runner.supabase.table("body_composition_logs").insert({
                "user_id": request.user_id,
                "weight_kg": current_weight
            }).execute()
        
        # Handle Custom Split
        if split_schedule and len(split_schedule) > 0:
            # 1. Deactivate old splits
            runner.supabase.table("workout_splits").update({"is_active": False}).eq("user_id", request.user_id).execute()
            
            # 2. Create new split
            # Using specific name if provided or generic 'Custom Split'
            split_name = f"{data.get('sport_type', 'Gym')} Split"
            split_res = runner.supabase.table("workout_splits").insert({
                "user_id": request.user_id,
                "name": split_name,
                "is_active": True
            }).execute()
            
            if split_res.data:
                split_id = split_res.data[0]['id']
                items_data = []
                for idx, workout_name in enumerate(split_schedule):
                    items_data.append({
                        "split_id": split_id,
                        "order_index": idx + 1,
                        "workout_name": workout_name
                    })
                
                if items_data:
                    runner.supabase.table("split_items").insert(items_data).execute()

        return {"status": "success", "message": "Profile updated", "targets": targets}
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Serve Static Files (Frontend)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount static directory
app.mount("/static", StaticFiles(directory="nutrisync_adk/static"), name="static")

# Serve index.html at root
@app.get("/")
async def serve_index():
    return FileResponse("nutrisync_adk/static/index.html")
