"""
Test script for Google Fit integration.
Verifies that we can fetch workouts and sleep using the refresh token.
"""
import os
import sys
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from nutrisync_adk.tools.google_fit import get_fit_workouts, get_fit_sleep

def main():
    print("=" * 60)
    print("Testing Google Fit Integration")
    print("=" * 60)
    
    # Test Workouts
    print("\n[1] Fetching last 7 days of Workouts...")
    
    # DEBUG: Get credentials and token
    from nutrisync_adk.tools.google_fit import _get_credentials, _refresh_access_token, _get_sessions
    from datetime import datetime, timedelta
    
    client_id, client_secret, refresh_token = _get_credentials()
    access_token = _refresh_access_token(client_id, client_secret, refresh_token)
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    
    print(f"DEBUG: Checking for ANY sessions between {start} and {end}")
    raw_sessions = _get_sessions(access_token, start, end)
    print(f"DEBUG: Raw session count: {len(raw_sessions)}")
    if len(raw_sessions) > 0:
        print(f"DEBUG: First session sample: {raw_sessions[0]}")
    
    workouts_result = get_fit_workouts(days=7)
    
    if workouts_result["success"]:
        print(f"✅ Success! Found {workouts_result['count']} workouts.")
        for w in workouts_result["workouts"]:
            print(f"   - {w['type']} ({w['duration_minutes']}m) | HR: {w.get('avg_hear_rate', 'N/A')} bpm | {w['start_time']}")
    else:
        print(f"❌ Failed: {workouts_result.get('error')}")

    # Test Sleep
    print("\n[2] Fetching last 7 days of Sleep...")
    sleep_result = get_fit_sleep(days=7)
    
    if sleep_result["success"]:
        print(f"✅ Success! Found {sleep_result['count']} sleep sessions.")
        for s in sleep_result["sleep_sessions"]:
            print(f"   - {s['duration_hours']}h | Deep Sleep: {s.get('deep_sleep_percentage', 0)}% | {s['date']}")
    else:
        print(f"❌ Failed: {sleep_result.get('error')}")

if __name__ == "__main__":
    main()
