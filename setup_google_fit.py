"""
One-time OAuth setup script for Google Fit integration.
Run this script once to authorize NutriSync to access your Google Fit data.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from nutrisync_adk.tools.google_fit import generate_oauth_url, exchange_code_for_tokens

def main():
    print("=" * 60)
    print("Google Fit OAuth Setup for NutriSync")
    print("=" * 60)
    
    # Step 1: Generate and display OAuth URL
    print("\n[Step 1] Open this URL in your browser and authorize access:\n")
    auth_url = generate_oauth_url()
    print(auth_url)
    
    # Step 2: Get authorization code from user
    print("\n[Step 2] After authorizing, you'll see an authorization code.")
    print("Copy and paste that code here:\n")
    auth_code = input("Authorization Code: ").strip()
    
    if not auth_code:
        print("Error: No authorization code provided.")
        return
    
    # Step 3: Exchange code for tokens
    print("\n[Step 3] Exchanging code for tokens...")
    try:
        tokens = exchange_code_for_tokens(auth_code)
        print("\n✅ Success! Here are your tokens:\n")
        print(f"Access Token: {tokens['access_token'][:50]}...")
        print(f"\n🔑 REFRESH TOKEN (save this to .env):")
        print(f"GOOGLE_FIT_REFRESH_TOKEN={tokens['refresh_token']}")
        print("\n" + "=" * 60)
        print("Add the line above to your .env file, then you're done!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
