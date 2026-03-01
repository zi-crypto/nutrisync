import os
import json
import logging
from pywebpush import webpush, WebPushException
from supabase import create_client, Client

logger = logging.getLogger("NutriSync-Notifications")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@nutrisync.com"}

def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    return create_client(url, key)

def send_push_message(subscription: dict, payload: str):
    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
    except WebPushException as ex:
        logger.error(f"Push response code: {ex.response.status_code}")
        logger.error(f"Push response info: {ex.response.text}")
        # If the subscription is no longer valid, we should theoretically delete it
        if ex.response.status_code in [404, 410]:
            try:
                sb = get_supabase()
                sb.table("push_subscriptions").delete().eq("endpoint", subscription["endpoint"]).execute()
            except Exception as e:
                logger.error(f"Failed to delete stale subscription: {e}")
    except Exception as e:
        logger.error(f"Error in webpush: {e}")

def get_users_with_subscriptions(sb: Client):
    resp = sb.table("push_subscriptions").select("user_id, endpoint, p256dh, auth").execute()
    return resp.data or []

def get_user_language(sb: Client, user_id: str) -> str:
    try:
        res = sb.table("user_profile").select("language").eq("user_id", user_id).limit(1).execute()
        if res.data and res.data[0].get("language"):
            return res.data[0]["language"]
    except Exception as e:
        logger.error(f"Error fetching language for {user_id}: {e}")
    return "en"

def run_morning_check():
    """Morning heuristics (e.g., 9:00 AM) - Check for sleep logs from yesterday."""
    logger.info("Running morning notification check...")
    try:
        sb = get_supabase()
        subs = get_users_with_subscriptions(sb)
        if not subs: return
        
        from nutrisync_adk.tools.utils import get_today_date_str
        today = get_today_date_str() # We can improve this by using yesterday, but sleep logs handles time offset implicitly
        
        for sub in subs:
            user_id = sub["user_id"]
            lang = get_user_language(sb, user_id)
            # Check if sleep was logged
            sleep_resp = sb.table("sleep_logs").select("id").eq("user_id", user_id).eq("log_date", today).limit(1).execute()
            if not sleep_resp.data:
                # Send notification
                if lang == "ar":
                    title = "صباح الخير! ☀️"
                    body = "هل نمت جيداً؟ سجل نومك لليلة الماضية للحفاظ على دقة إحصائياتك."
                else:
                    title = "Good morning! ☀️"
                    body = "Did you sleep well? Log your sleep from last night to keep your stats accurate."
                    
                payload = json.dumps({"title": title, "body": body})
                send_push_message({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, payload)
    except Exception as e:
        logger.error(f"Morning check error: {e}")

def run_afternoon_check():
    """Afternoon heuristics (e.g., 2:00 PM) - Check for nutrition logs today."""
    logger.info("Running afternoon notification check...")
    try:
        sb = get_supabase()
        subs = get_users_with_subscriptions(sb)
        if not subs: return
        
        from nutrisync_adk.tools.utils import get_today_date_str
        today = get_today_date_str()
        
        for sub in subs:
            user_id = sub["user_id"]
            lang = get_user_language(sb, user_id)
            nut_resp = sb.table("nutrition_logs").select("id").eq("user_id", user_id).eq("log_date", today).limit(1).execute()
            if not nut_resp.data:
                if lang == "ar":
                    title = "استمر على المسار الصحيح! 🥗"
                    body = "لا تنسَ تسجيل غدائك للبقاء على اطلاع دائم بالسعرات الحرارية."
                else:
                    title = "Stay on track! 🥗"
                    body = "Don't forget to track your lunch to stay on top of your macros."
                
                payload = json.dumps({"title": title, "body": body})
                send_push_message({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, payload)
    except Exception as e:
        logger.error(f"Afternoon check error: {e}")

def run_evening_check():
    """Evening heuristics (e.g., 8:00 PM) - Check for workout logs today, respecting schedule."""
    logger.info("Running evening notification check...")
    try:
        sb = get_supabase()
        subs = get_users_with_subscriptions(sb)
        if not subs: return
        
        from nutrisync_adk.tools.utils import get_today_date_str
        today = get_today_date_str()
        
        for sub in subs:
            user_id = sub["user_id"]
            lang = get_user_language(sb, user_id)
            
            # 1. Does the user have a workout log today?
            log_resp = sb.table("workout_logs").select("id").eq("user_id", user_id).eq("log_date", today).limit(1).execute()
            if log_resp.data:
                continue # They already worked out
                
            # 2. What is their next scheduled split day?
            split_resp = sb.table("workout_splits").select("id").eq("user_id", user_id).eq("is_active", True).limit(1).execute()
            if not split_resp.data:
                continue # No active split
                
            split_id = split_resp.data[0]["id"]
            items_resp = sb.table("split_items").select("workout_name").eq("split_id", split_id).order("order_index").execute()
            if not items_resp.data:
                continue
                
            schedule = [item["workout_name"] for item in items_resp.data]
            
            # Find the last logged workout day to determine where they are in the cycle.
            # Simplified heuristic: just ask the database what they did last time.
            last_log = sb.table("workout_logs").select("workout_type").eq("user_id", user_id).order("start_time", desc=True).limit(1).execute()
            
            next_workout = schedule[0]
            if last_log.data:
                last_type = last_log.data[0]["workout_type"]
                try:
                    # Find exactly where they are in the exact string match schedule
                    idx = schedule.index(last_type)
                    next_workout = schedule[(idx + 1) % len(schedule)]
                except ValueError:
                    # If the last logged wasn't strictly in schedule, assume first item.
                    next_workout = schedule[0]
                    
            if next_workout.strip().lower() in ("rest", "rest day"):
                continue # It's a rest day, no notification needed
                
            if lang == "ar":
                title = f"حان الوقت لسحق تمرين {next_workout}! 🏋️"
                body = f"هل أنجزت تمرين {next_workout} الخاص بك اليوم؟ سجله الآن للحفاظ على الزخم!"
            else:
                title = f"Time to crush {next_workout}! 🏋️"
                body = f"Did you hit your {next_workout} workout today? Log it now to keep up the momentum!"
                
            payload = json.dumps({"title": title, "body": body})
            send_push_message({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, payload)
            
    except Exception as e:
        logger.error(f"Evening check error: {e}")

def run_night_check():
    """Night heuristics (e.g., 10:00 PM) - Check for remaining macro goals today."""
    logger.info("Running night notification check...")
    try:
        sb = get_supabase()
        subs = get_users_with_subscriptions(sb)
        if not subs: return
        
        from nutrisync_adk.tools.utils import get_today_date_str
        today_date = get_today_date_str()
        
        for sub in subs:
            user_id = sub["user_id"]
            
            # 1. Fetch user targets and language
            profile_resp = sb.table("user_profile").select("daily_calorie_target, daily_protein_target_gm, language").eq("user_id", user_id).execute()
            if not profile_resp.data:
                continue
            
            target_cals = profile_resp.data[0].get("daily_calorie_target") or 0
            target_protein = profile_resp.data[0].get("daily_protein_target_gm") or 0
            lang = profile_resp.data[0].get("language") or "en"
            
            if target_cals == 0 and target_protein == 0:
                continue
                
            # 2. Fetch logged nutrition for today
            nut_resp = sb.table("nutrition_logs").select("calories, protein").eq("user_id", user_id).eq("log_date", today_date).execute()
            
            consumed_cals = sum((log.get("calories") or 0) for log in nut_resp.data) if nut_resp.data else 0
            consumed_protein = sum((log.get("protein") or 0) for log in nut_resp.data) if nut_resp.data else 0
            
            remaining_cals = max(0, target_cals - consumed_cals)
            remaining_protein = max(0, target_protein - consumed_protein)
            
            # Send notification if significantly under target
            if remaining_cals > 150 or remaining_protein > 15:
                if lang == "ar":
                    body = f"ما زلت بحاجة إلى {int(remaining_cals)} سعرة حرارية" if remaining_cals > 150 else ""
                    if remaining_protein > 15:
                        if body: body += f" و {int(remaining_protein)} جرام بروتين"
                        else: body = f"ما زلت بحاجة إلى {int(remaining_protein)} جرام بروتين"
                    body += " اليوم! خذ وجبة خفيفة غنية بالبروتين قبل النوم."
                    title = "التحقق من السعرات الحرارية ليلاً 🌙"
                else:
                    body = f"You still need {int(remaining_cals)} kcal" if remaining_cals > 150 else ""
                    if remaining_protein > 15:
                        if body: body += f" and {int(remaining_protein)}g protein"
                        else: body = f"You still need {int(remaining_protein)}g protein"
                    body += " today! Grab a high-protein snack before bed."
                    title = "Late-Night Macro Check 🌙"
                
                payload = json.dumps({"title": title, "body": body})
                send_push_message({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, payload)
                
    except Exception as e:
        logger.error(f"Night check error: {e}")

def run_body_comp_check():
    """Bi-weekly heuristic (e.g., Wed/Sun 8:00 AM) - Check for missing body weight logs in last 3.5 days."""
    logger.info("Running bi-weekly body composition notification check...")
    try:
        sb = get_supabase()
        subs = get_users_with_subscriptions(sb)
        if not subs: return
        
        from datetime import datetime, timedelta
        # 3 days ago string
        cutoff_date = (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d')
        
        for sub in subs:
            user_id = sub["user_id"]
            lang = get_user_language(sb, user_id)
            
            # Query if they have logged weight since the cutoff
            comp_resp = sb.table("body_composition_logs").select("id").eq("user_id", user_id).gte("log_date", cutoff_date).limit(1).execute()
            if not comp_resp.data:
                if lang == "ar":
                    title = "حان وقت قياس الوزن! ⚖️"
                    body = "سجل وزن جسمك الحالي للحفاظ على دقة مخططات التقدم وتحديث أهداف السعرات الحرارية الخاصة بك."
                else:
                    title = "Time for a weigh-in! ⚖️"
                    body = "Log your current body weight to keep your progress charts accurate and your calorie targets updated."
                
                payload = json.dumps({"title": title, "body": body})
                send_push_message({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, payload)
                
    except Exception as e:
        logger.error(f"Body comp check error: {e}")
