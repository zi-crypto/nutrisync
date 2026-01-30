"""
Google Fit Integration for NutriSync
Fetches workout and sleep data from Google Fit API
"""
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Google Fit API endpoints
GOOGLE_FIT_BASE = "https://www.googleapis.com/fitness/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Activity type mappings (Google Fit activity codes)
ACTIVITY_TYPES = {
    7: "Walking",
    8: "Running",
    9: "Aerobics",
    10: "Biking",
    13: "Badminton",
    14: "Baseball",
    15: "Basketball",
    16: "Boxing",
    17: "Calisthenics",
    18: "Cricket",
    19: "CrossFit",
    24: "Dancing",
    25: "Elliptical",
    29: "Football",
    35: "Gymnastics",
    36: "Handball",
    37: "HIIT",
    38: "Hiking",
    39: "Hockey",
    44: "Martial Arts",
    48: "Pilates",
    49: "Polo",
    52: "Rowing",
    54: "Rugby",
    57: "Skating",
    58: "Skiing",
    62: "Squash",
    64: "Stair Climbing",
    65: "Strength Training",
    67: "Surfing",
    68: "Swimming",
    70: "Tennis",
    72: "Sleep",
    73: "Treadmill Running",
    74: "Volleyball",
    76: "Walking (Treadmill)",
    80: "Weightlifting",
    82: "Yoga",
    83: "Zumba",
    112: "CrossFit",
    113: "Functional Training",
}


def _get_credentials():
    """Get Google Fit OAuth credentials from environment"""
    client_id = os.getenv("GOOGLE_FIT_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_FIT_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_FIT_REFRESH_TOKEN")
    
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_FIT_CLIENT_ID and GOOGLE_FIT_CLIENT_SECRET must be set in .env")
    
    return client_id, client_secret, refresh_token


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange refresh token for a new access token"""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        })
        
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            raise Exception(f"Failed to refresh token: {response.text}")


def _get_sessions(access_token: str, start_time: datetime, end_time: datetime, activity_type: Optional[int] = None) -> List[Dict]:
    """Fetch sessions from Google Fit API"""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Convert to nanoseconds (Google Fit uses nanosecond timestamps)
    start_ns = int(start_time.timestamp() * 1e9)
    end_ns = int(end_time.timestamp() * 1e9)
    
    url = f"{GOOGLE_FIT_BASE}/users/me/sessions"
    params = {
        "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    }
    
    if activity_type:
        params["activityType"] = activity_type
    
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            return response.json().get("session", [])
        else:
            logger.error(f"Failed to fetch sessions: {response.text}")
            return []



def _get_dataset(access_token: str, data_source_id: str, start_ns: int, end_ns: int) -> Dict[str, Any]:
    """Fetch dataset for a specific data source and time range"""
    headers = {"Authorization": f"Bearer {access_token}"}
    dataset_id = f"{start_ns}-{end_ns}"
    url = f"{GOOGLE_FIT_BASE}/users/me/dataSources/{data_source_id}/datasets/{dataset_id}"
    
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return {}

def _calculate_avg_hr(access_token: str, start_time: datetime, end_time: datetime) -> int:
    """Calculate average heart rate for a time range"""
    start_ns = int(start_time.timestamp() * 1e9)
    end_ns = int(end_time.timestamp() * 1e9)
    
    # Use derived merge_heart_rate_bpm data source
    data_source = "derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm"
    dataset = _get_dataset(access_token, data_source, start_ns, end_ns)
    
    total_bpm = 0
    count = 0
    
    for point in dataset.get("point", []):
        for value in point.get("value", []):
            if "fpVal" in value:
                total_bpm += value["fpVal"]
                count += 1
            elif "intVal" in value: # Sometimes older data
                total_bpm += value["intVal"]
                count += 1
                
    return int(total_bpm / count) if count > 0 else 0

def _calculate_deep_sleep_pct(access_token: str, start_time: datetime, end_time: datetime) -> int:
    """Calculate deep sleep percentage from sleep segments"""
    start_ns = int(start_time.timestamp() * 1e9)
    end_ns = int(end_time.timestamp() * 1e9)
    
    # Use derived sleep segment data source
    data_source = "derived:com.google.sleep.segment:com.google.android.gms:merged"
    dataset = _get_dataset(access_token, data_source, start_ns, end_ns)
    
    total_sleep_ns = 0
    deep_sleep_ns = 0
    
    for point in dataset.get("point", []):
        pt_start = int(point.get("startTimeNanos", 0))
        pt_end = int(point.get("endTimeNanos", 0))
        duration = pt_end - pt_start
        
        for value in point.get("value", []):
            segment_type = value.get("intVal")
            # Types: 2 (Sleep), 4 (Light), 5 (Deep), 6 (REM)
            # We count all sleep types towards total
            if segment_type in [2, 4, 5, 6]:
                total_sleep_ns += duration
            
            if segment_type == 5: # Deep sleep
                deep_sleep_ns += duration
                
    if total_sleep_ns == 0:
        return 0
        
    return int((deep_sleep_ns / total_sleep_ns) * 100)


def get_fit_workouts(days: int = 7) -> Dict[str, Any]:
    """
    Fetches workout sessions from Google Fit for the specified number of days.
    
    Args:
        days: Number of days to look back (default 7)
    
    Returns:
        Dictionary with workouts list and metadata
    """
    try:
        client_id, client_secret, refresh_token = _get_credentials()
        
        if not refresh_token:
            return {
                "success": False,
                "error": "GOOGLE_FIT_REFRESH_TOKEN not set. Run the OAuth flow first.",
                "workouts": []
            }
        
        access_token = _refresh_access_token(client_id, client_secret, refresh_token)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        sessions = _get_sessions(access_token, start_time, end_time)
        
        workouts = []
        for session in sessions:
            activity_type = session.get("activityType", 0)
            
            # Skip sleep (we handle that separately)
            if activity_type == 72:
                continue
            
            start_ms = int(session.get("startTimeMillis", 0))
            end_ms = int(session.get("endTimeMillis", 0))
            duration_minutes = (end_ms - start_ms) / (1000 * 60)
            
            # Calculate Avg HR for this session
            sess_start = datetime.fromtimestamp(start_ms / 1000)
            sess_end = datetime.fromtimestamp(end_ms / 1000)
            avg_hr = _calculate_avg_hr(access_token, sess_start, sess_end)
            
            workout = {
                "name": session.get("name", ACTIVITY_TYPES.get(activity_type, "Unknown Workout")),
                "type": ACTIVITY_TYPES.get(activity_type, f"Activity {activity_type}"),
                "activity_code": activity_type,
                "start_time": sess_start.isoformat(),
                "duration_minutes": round(duration_minutes, 1),
                "calories": session.get("activeTimeMillis", 0) / 60000 * 5,  # Rough estimate
                "avg_hear_rate": avg_hr,
                "source": session.get("application", {}).get("name", "Unknown")
            }
            workouts.append(workout)
        
        return {
            "success": True,
            "workouts": workouts,
            "count": len(workouts),
            "period": f"Last {days} days"
        }
        
    except Exception as e:
        logger.error(f"Error fetching Google Fit workouts: {e}")
        return {
            "success": False,
            "error": str(e),
            "workouts": []
        }


def get_fit_sleep(days: int = 7) -> Dict[str, Any]:
    """
    Fetches sleep sessions from Google Fit for the specified number of days.
    
    Args:
        days: Number of days to look back (default 7)
    
    Returns:
        Dictionary with sleep sessions and metadata
    """
    try:
        client_id, client_secret, refresh_token = _get_credentials()
        
        if not refresh_token:
            return {
                "success": False,
                "error": "GOOGLE_FIT_REFRESH_TOKEN not set. Run the OAuth flow first.",
                "sleep_sessions": []
            }
        
        access_token = _refresh_access_token(client_id, client_secret, refresh_token)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        # Activity type 72 = Sleep
        sessions = _get_sessions(access_token, start_time, end_time, activity_type=72)
        
        sleep_records = []
        for session in sessions:
            start_ms = int(session.get("startTimeMillis", 0))
            end_ms = int(session.get("endTimeMillis", 0))
            duration_hours = (end_ms - start_ms) / (1000 * 60 * 60)
            
            sleep_start = datetime.fromtimestamp(start_ms / 1000)
            sleep_end = datetime.fromtimestamp(end_ms / 1000)
            
            # Calculate Deep Sleep %
            deep_sleep_pct = _calculate_deep_sleep_pct(access_token, sleep_start, sleep_end)
            
            record = {
                "date": sleep_start.strftime("%Y-%m-%d"),
                "start_time": sleep_start.isoformat(),
                "duration_hours": round(duration_hours, 2),
                "deep_sleep_percentage": deep_sleep_pct,
                "source": session.get("application", {}).get("name", "Unknown")
            }
            sleep_records.append(record)
        
        return {
            "success": True,
            "sleep_sessions": sleep_records,
            "count": len(sleep_records),
            "period": f"Last {days} days"
        }
        
    except Exception as e:
        logger.error(f"Error fetching Google Fit sleep: {e}")
        return {
            "success": False,
            "error": str(e),
            "sleep_sessions": []
        }


# OAuth helper script (run once to get refresh token)
def generate_oauth_url() -> str:
    """
    Generates the OAuth URL for user authorization.
    User visits this URL, authorizes, and gets an authorization code.
    """
    client_id, _, _ = _get_credentials()
    
    scopes = [
        "https://www.googleapis.com/auth/fitness.activity.read",
        "https://www.googleapis.com/auth/fitness.sleep.read",
        "https://www.googleapis.com/auth/fitness.body.read"
    ]
    
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        "redirect_uri=urn:ietf:wg:oauth:2.0:oob&"
        "response_type=code&"
        f"scope={' '.join(scopes)}&"
        "access_type=offline&"
        "prompt=consent"
    )
    
    return auth_url


def exchange_code_for_tokens(auth_code: str) -> Dict[str, str]:
    """
    Exchange authorization code for access and refresh tokens.
    Run this once after user authorizes via the OAuth URL.
    """
    client_id, client_secret, _ = _get_credentials()
    
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
        })
        
        if response.status_code == 200:
            tokens = response.json()
            return {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "message": "Save the refresh_token to your .env as GOOGLE_FIT_REFRESH_TOKEN"
            }
        else:
            raise Exception(f"Token exchange failed: {response.text}")
