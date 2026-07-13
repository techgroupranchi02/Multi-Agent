"""
Aikyam — One-time Google OAuth2 Setup
Run this script once to authorize Aikyam to create Google Docs on your behalf.

Usage:
    python setup_google_oauth.py

This will:
1. Open your browser for Google sign-in
2. Ask you to grant Docs + Drive permissions
3. Save a refresh token to 'google_oauth_token.json'

After this, the pipeline will use YOUR Google account to create docs
(not the service account, which has no Drive storage).
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    print("=" * 60)
    print("  Aikyam — Google OAuth2 Setup")
    print("=" * 60)

    # Check for OAuth client credentials
    backend_dir = Path(__file__).resolve().parent
    client_secrets_path = backend_dir / "google_oauth_client.json"

    if not client_secrets_path.is_file():
        print(f"\n[X] Missing: {client_secrets_path}")
        print("\nYou need to create OAuth2 Client credentials:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials?project=poised-space-450813-r0")
        print("2. Click '+ CREATE CREDENTIALS' -> 'OAuth client ID'")
        print("3. Application type: 'Desktop app'")
        print("4. Name: 'Aikyam Pipeline'")
        print("5. Click 'CREATE'")
        print("6. Click 'DOWNLOAD JSON'")
        print(f"7. Save the file as: {client_secrets_path}")
        print("\nThen run this script again.")

        # If OAuth consent screen hasn't been configured
        print("\n[!]  If you haven't set up the OAuth consent screen yet:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials/consent?project=poised-space-450813-r0")
        print("2. User Type: 'External'")
        print("3. App name: 'Aikyam Pipeline'")
        print("4. Add scopes: Google Docs API, Google Drive API")
        print("5. Add your email as a test user")
        print("6. Save")
        return

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[X] Missing package: pip install google-auth-oauthlib")
        return

    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]

    print(f"\n[*] Starting OAuth2 flow...")
    print(f"   Scopes: {scopes}")
    print(f"   A browser window will open for sign-in...\n")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=scopes,
    )

    credentials = flow.run_local_server(port=8090, prompt="consent")

    # Save the token
    token_path = backend_dir / "google_oauth_token.json"
    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes),
    }

    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n[OK] OAuth2 setup complete!")
    print(f"   Token saved to: {token_path}")
    print(f"   Account: {credentials.token[:20]}...")
    print(f"\n   The pipeline will now use your Google account to create docs.")
    print(f"   You only need to run this once (the refresh token is persistent).")


if __name__ == "__main__":
    main()
