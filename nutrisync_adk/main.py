import logging
import os
import time
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .runners import NutriSyncRunner
from .services.analytics import capture as posthog_capture, identify as posthog_identify, shutdown as posthog_shutdown

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NutriSync")

app = FastAPI()
runner = NutriSyncRunner()

@app.on_event("startup")
async def startup_event():
    logger.info("NutriSync ADK is starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    posthog_shutdown()
    logger.info("PostHog analytics flushed and shut down.")

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
    language: Optional[str] = "en"

class FeedbackRequest(BaseModel):
    message_id: int
    guest_id: str
    feedback_value: int
    feedback_comment: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    start_time = time.time()
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
    response = await runner.process_message(request.guest_id, request.message, image_bytes=image_bytes, mime_type=mime_type, language=request.language)

    # ── PostHog: Track chat API call ──
    latency_ms = int((time.time() - start_time) * 1000)
    posthog_capture(request.guest_id, "api_chat_processed", {
        "message_length": len(request.message),
        "has_image": request.image is not None,
        "response_length": len(response.get("text", "") or ""),
        "has_chart": response.get("chart") is not None,
        "latency_ms": latency_ms,
    })

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
            raise HTTPException(status_code=400, detail="error.feedback_comment_short")
        
        if request.feedback_value not in (1, -1):
            raise HTTPException(status_code=400, detail="error.feedback_value_invalid")
            
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
            
        # ── PostHog: Track feedback ──
        posthog_capture(request.guest_id, "api_feedback_submitted", {
            "feedback_value": "like" if request.feedback_value == 1 else "dislike",
            "comment_length": len(request.feedback_comment),
        })

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Profile API
class ProfileRequest(BaseModel):
    user_id: str
    name: str
    coach_name: Optional[str] = "NutriSync"
    language: Optional[str] = "en"
    gender: str
    dob: str
    height_cm: int
    weight_kg: float
    target_weight_kg: Optional[float] = None
    fitness_goal: str
    experience_level: str
    equipment_access: str
    workout_days_per_week: int = Field(ge=1, le=14)
    typical_daily_calories: Optional[int] = None
    typical_diet_type: Optional[str] = None
    allergies: Optional[str] = None
    sport_type: Optional[str] = None
    split_schedule: Optional[List[str]] = None # List of day names e.g. ["Push", "Pull", "Legs"]
    one_rm_records: Optional[list[dict]] = None # List of {"exercise_name": "Squat", "weight_kg": 100}
    equipment_list: Optional[List[str]] = None # List of specific equipment names e.g. ["Barbell", "Cable Machine"]

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
        
        # Fetch 1RM Records
        records_res = runner.supabase.table("user_1rm_records").select("exercise_name, weight_kg").eq("user_id", user_id).execute()
        profile_data['one_rm_records'] = records_res.data if records_res.data else []
        
        # Fetch User Equipment
        equip_res = runner.supabase.table("user_equipment").select("equipment_name").eq("user_id", user_id).execute()
        profile_data['equipment_list'] = [e['equipment_name'] for e in equip_res.data] if equip_res.data else []
        
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
        
        # Extract Split Schedule and 1RM Records
        split_schedule = data.pop("split_schedule", None)
        one_rm_records = data.pop("one_rm_records", None)
        equipment_list = data.pop("equipment_list", None)

        # Server-side: derive workout_days_per_week from split schedule for Gym users
        if split_schedule and data.get("sport_type") == "Gym":
            non_rest = [d for d in split_schedule if d.strip().lower() not in ("rest", "rest day")]
            data["workout_days_per_week"] = len(non_rest) if non_rest else 1

        # Clamp workout_days_per_week to at least 1
        if data.get("workout_days_per_week", 1) < 1:
            data["workout_days_per_week"] = 1

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
        
        # Handle Custom Split (Upsert pattern: reuse existing active split)
        if split_schedule and len(split_schedule) > 0:
            split_name = f"{data.get('sport_type', 'Gym')} Split"

            # Check for existing active split
            existing_split_resp = (runner.supabase.table("workout_splits")
                                   .select("id, name")
                                   .eq("user_id", request.user_id)
                                   .eq("is_active", True)
                                   .limit(1)
                                   .execute())

            if existing_split_resp.data:
                # Reuse existing split — update name if changed
                split_id = existing_split_resp.data[0]["id"]
                if existing_split_resp.data[0]["name"] != split_name:
                    (runner.supabase.table("workout_splits")
                     .update({"name": split_name})
                     .eq("id", split_id)
                     .execute())

                # Replace split_items (lightweight day names, no FKs depend on them)
                runner.supabase.table("split_items").delete().eq("split_id", split_id).execute()
            else:
                # No active split — deactivate any stale ones and create new
                runner.supabase.table("workout_splits").update({"is_active": False}).eq("user_id", request.user_id).execute()
                split_res = runner.supabase.table("workout_splits").insert({
                    "user_id": request.user_id,
                    "name": split_name,
                    "is_active": True
                }).execute()
                split_id = split_res.data[0]['id'] if split_res.data else None

            if split_id:
                items_data = [
                    {"split_id": split_id, "order_index": idx + 1, "workout_name": workout_name}
                    for idx, workout_name in enumerate(split_schedule)
                ]
                if items_data:
                    runner.supabase.table("split_items").insert(items_data).execute()

        # Handle 1RM Records
        if one_rm_records is not None:
            # Upsert records using unique constraint
            for record in one_rm_records:
                record_data = {
                    "user_id": request.user_id,
                    "exercise_name": record.get("exercise_name"),
                    "weight_kg": record.get("weight_kg")
                }
                
                # Check for existing
                existing = runner.supabase.table("user_1rm_records").select("id").eq("user_id", request.user_id).eq("exercise_name", record_data["exercise_name"]).execute()
                
                if existing.data and len(existing.data) > 0:
                    runner.supabase.table("user_1rm_records").update({"weight_kg": record_data["weight_kg"]}).eq("id", existing.data[0]["id"]).execute()
                else:
                    runner.supabase.table("user_1rm_records").insert(record_data).execute()

        # Handle Equipment List
        if equipment_list is not None:
            # Delete old equipment for this user
            runner.supabase.table("user_equipment").delete().eq("user_id", request.user_id).execute()
            # Insert new equipment selections
            if equipment_list:
                equip_rows = [
                    {"user_id": request.user_id, "equipment_name": name, "category": "User Selected"}
                    for name in equipment_list
                ]
                runner.supabase.table("user_equipment").insert(equip_rows).execute()

        # ── PostHog: Track profile save and set person properties ──
        posthog_capture(request.user_id, "api_profile_saved", {
            "fitness_goal": request.fitness_goal,
            "experience_level": request.experience_level,
            "sport_type": request.sport_type,
            "equipment_access": request.equipment_access,
            "workout_days": request.workout_days_per_week,
            "has_split": bool(split_schedule),
            "equipment_count": len(equipment_list) if equipment_list else 0,
            "rm_count": len(one_rm_records) if one_rm_records else 0,
        })
        posthog_identify(request.user_id, {
            "name": request.name,
            "fitness_goal": request.fitness_goal,
            "experience_level": request.experience_level,
            "sport_type": request.sport_type,
            "equipment_access": request.equipment_access,
        })

        return {"status": "success", "message": "Profile updated", "targets": targets}
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Live Coach Exercise Logging ─────────────────────────────────────────────

LIVE_COACH_EXERCISE_MAP = {
    "squat": "Bodyweight Squats",
    "pushup": "Push-ups",
    "pullup": "Pull-ups",
}

class LiveCoachLogRequest(BaseModel):
    user_id: str
    exercise_key: str  # squat, pushup, pullup
    reps: int
    weight_kg: Optional[float] = None  # If null, uses body weight from profile

@app.post("/api/live-coach/log")
async def log_live_coach_exercise(request: LiveCoachLogRequest):
    """Logs a single set from the Live Coach pose tracker into exercise_logs."""
    try:
        from .tools.utils import get_today_date_str

        exercise_name = LIVE_COACH_EXERCISE_MAP.get(
            request.exercise_key, request.exercise_key.title()
        )

        if request.reps <= 0:
            raise HTTPException(status_code=400, detail="error.reps_zero")

        # Resolve weight — use provided value or fallback to user's body weight
        weight_kg = request.weight_kg
        if weight_kg is None:
            profile_resp = (runner.supabase.table("user_profile")
                            .select("weight_kg")
                            .eq("user_id", request.user_id)
                            .limit(1)
                            .execute())
            weight_kg = profile_resp.data[0]["weight_kg"] if profile_resp.data else 0

        log_date = get_today_date_str()

        # Determine next set_number for this exercise today
        existing_sets = (runner.supabase.table("exercise_logs")
                         .select("set_number")
                         .eq("user_id", request.user_id)
                         .eq("log_date", log_date)
                         .ilike("exercise_name", exercise_name)
                         .order("set_number", desc=True)
                         .limit(1)
                         .execute())
        set_number = (existing_sets.data[0]["set_number"] + 1) if existing_sets.data else 1

        # ── PR Detection (volume PR & weight PR) ───────────────────────────
        pr_resp = (runner.supabase.table("exercise_logs")
                   .select("volume_load")
                   .eq("user_id", request.user_id)
                   .ilike("exercise_name", exercise_name)
                   .eq("is_warmup", False)
                   .order("volume_load", desc=True)
                   .limit(1)
                   .execute())
        existing_best_volume = pr_resp.data[0]["volume_load"] if pr_resp.data else 0

        weight_pr_resp = (runner.supabase.table("exercise_logs")
                          .select("weight_kg")
                          .eq("user_id", request.user_id)
                          .ilike("exercise_name", exercise_name)
                          .eq("is_warmup", False)
                          .order("weight_kg", desc=True)
                          .limit(1)
                          .execute())
        existing_best_weight = weight_pr_resp.data[0]["weight_kg"] if weight_pr_resp.data else 0

        vol = weight_kg * request.reps
        is_pr = False
        pr_type = None
        if vol > 0 and vol > existing_best_volume:
            is_pr = True
            pr_type = "volume"
        elif weight_kg > 0 and weight_kg > existing_best_weight:
            is_pr = True
            pr_type = "weight"

        # ── Insert ──────────────────────────────────────────────────────────
        row = {
            "user_id": request.user_id,
            "log_date": log_date,
            "exercise_name": exercise_name,
            "set_number": set_number,
            "weight_kg": weight_kg,
            "reps": request.reps,
            "is_warmup": False,
            "is_pr": is_pr,
            "notes": "Logged via Live Coach",
        }

        insert_resp = runner.supabase.table("exercise_logs").insert(row).execute()
        if not insert_resp.data:
            raise HTTPException(status_code=500, detail="error.exercise_log_failed")

        # ── PostHog: Track live coach exercise log ──
        posthog_capture(request.user_id, "api_live_coach_logged", {
            "exercise": exercise_name,
            "reps": request.reps,
            "weight_kg": weight_kg,
            "set_number": set_number,
            "is_pr": is_pr,
            "pr_type": pr_type,
            "volume_load": vol,
        })

        return {
            "success": True,
            "exercise_name": exercise_name,
            "set_number": set_number,
            "reps": request.reps,
            "weight_kg": weight_kg,
            "volume_load": vol,
            "is_pr": is_pr,
            "pr_type": pr_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging live coach exercise: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Workout Plan & Progress API (Phase 4) ──────────────────────────────────

@app.get("/api/workout-plan/{user_id}")
async def get_workout_plan(user_id: str):
    """Returns the user's current AI-generated workout plan grouped by day."""
    try:
        # Get active split
        split_resp = (runner.supabase.table("workout_splits")
                      .select("id, name")
                      .eq("user_id", user_id)
                      .eq("is_active", True)
                      .limit(1)
                      .execute())
        if not split_resp.data:
            return {"plan": [], "split_name": None, "message": "No active split found."}

        split_id = split_resp.data[0]["id"]
        split_name = split_resp.data[0]["name"]

        plan_resp = (runner.supabase.table("workout_plan_exercises")
                     .select("split_day_name, exercise_order, exercise_name, exercise_type, "
                             "target_muscles, sets, rep_range_low, rep_range_high, "
                             "load_percentage, rest_seconds, superset_group, notes")
                     .eq("user_id", user_id)
                     .eq("split_id", split_id)
                     .order("split_day_name")
                     .order("exercise_order")
                     .execute())

        return {"split_name": split_name, "plan": plan_resp.data or []}
    except Exception as e:
        logger.error(f"Error fetching workout plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/progress/{user_id}")
async def get_progress(user_id: str, exercise: Optional[str] = None, weeks: int = 8):
    """Returns progressive overload data for one exercise or all exercises."""
    try:
        if exercise:
            # Weekly trend via DB function
            progress_resp = runner.supabase.rpc("get_exercise_progress", {
                "p_user_id": user_id,
                "p_exercise_name": exercise,
                "p_weeks": weeks,
            }).execute()

            # All-time best weight
            best_weight_resp = (runner.supabase.table("exercise_logs")
                                .select("weight_kg, reps, volume_load, log_date")
                                .eq("user_id", user_id)
                                .ilike("exercise_name", exercise)
                                .eq("is_warmup", False)
                                .order("weight_kg", desc=True)
                                .limit(1)
                                .execute())

            # All-time best volume set
            best_vol_resp = (runner.supabase.table("exercise_logs")
                             .select("weight_kg, reps, volume_load, log_date")
                             .eq("user_id", user_id)
                             .ilike("exercise_name", exercise)
                             .eq("is_warmup", False)
                             .order("volume_load", desc=True)
                             .limit(1)
                             .execute())

            best_weight = best_weight_resp.data[0] if best_weight_resp.data else None
            best_e1rm = None
            if best_weight:
                w, r = best_weight["weight_kg"], best_weight["reps"]
                best_e1rm = round(w * (1 + r / 30.0), 1) if r > 0 else w

            return {
                "exercise": exercise,
                "weekly_trend": progress_resp.data or [],
                "all_time_pr": {
                    "best_weight": best_weight,
                    "best_volume_set": best_vol_resp.data[0] if best_vol_resp.data else None,
                    "best_e1rm": best_e1rm,
                },
            }
        else:
            # Summary for all exercises
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).strftime('%Y-%m-%d')

            all_resp = (runner.supabase.table("exercise_logs")
                        .select("exercise_name, weight_kg, reps, volume_load, is_pr, log_date")
                        .eq("user_id", user_id)
                        .eq("is_warmup", False)
                        .gte("log_date", cutoff)
                        .order("log_date", desc=True)
                        .limit(500)
                        .execute())

            if not all_resp.data:
                return {"exercises": [], "message": "No exercise data yet."}

            exercise_map = {}
            for row in all_resp.data:
                name = row["exercise_name"]
                if name not in exercise_map:
                    exercise_map[name] = {
                        "total_sets": 0, "total_volume": 0,
                        "best_weight": 0, "best_volume_set": 0,
                        "pr_count": 0, "last_date": row["log_date"],
                    }
                entry = exercise_map[name]
                entry["total_sets"] += 1
                entry["total_volume"] += (row["volume_load"] or 0)
                entry["best_weight"] = max(entry["best_weight"], row["weight_kg"])
                entry["best_volume_set"] = max(entry["best_volume_set"], row["volume_load"] or 0)
                if row.get("is_pr"):
                    entry["pr_count"] += 1

            exercises = [{"exercise": name, **data} for name, data in exercise_map.items()]
            return {"exercises": exercises, "total_tracked": len(exercises)}
    except Exception as e:
        logger.error(f"Error fetching progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/muscle-volume/{user_id}")
async def get_muscle_volume(user_id: str, week_offset: int = 0):
    """Returns weekly completed sets per muscle group for the given week."""
    try:
        resp = runner.supabase.rpc("get_weekly_muscle_volume", {
            "p_user_id": user_id,
            "p_week_offset": week_offset,
        }).execute()

        return {"week_offset": week_offset, "muscle_volumes": resp.data or []}
    except Exception as e:
        logger.error(f"Error fetching muscle volume: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Serve Static Files (Frontend)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

# Jinja2 environment for template rendering (index.html)
_jinja_env = Environment(
    loader=FileSystemLoader("nutrisync_adk/static"),
    autoescape=True,
)

# PostHog config read once from environment
_POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
_POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com")

# Mount static directory
app.mount("/static", StaticFiles(directory="nutrisync_adk/static"), name="static")

# Serve index.html at root — rendered via Jinja2 to inject server-side config
@app.get("/")
async def serve_index():
    template = _jinja_env.get_template("index.html")
    html = template.render(
        posthog_api_key=_POSTHOG_API_KEY,
        posthog_host=_POSTHOG_HOST,
    )
    return HTMLResponse(content=html)
