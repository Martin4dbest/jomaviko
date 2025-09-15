
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# The ID of your Google Sheet
SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# Optional local service account file (only for local dev)
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE") 

# Google Sheets API scope
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def authenticate_google_sheets():
    """
    Authenticate with Google Sheets API using:
    - SERVICE_ACCOUNT_JSON (Render environment)
    - SERVICE_ACCOUNT_FILE (local file)
    """
    try:
        service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
        credentials = None

        # 🔹 Render: JSON string from environment variable
        if service_account_json:
            # Step 1: load as raw JSON string safely
            info = json.loads(service_account_json)

            # Step 2: fix private_key newline
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")

            credentials = Credentials.from_service_account_info(info, scopes=SCOPES)

        # 🔹 Local: use the file
        elif SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        else:
            raise ValueError("No SERVICE_ACCOUNT_JSON or SERVICE_ACCOUNT_FILE found")

        service = build("sheets", "v4", credentials=credentials)
        return service

    except Exception as e:
        print(f"❌ Error during Google Sheets authentication: {e}")
        return None

# Initialize
service = authenticate_google_sheets()
if service:
    print("✅ Google Sheets service ready")
else:
    print("❌ Google Sheets service failed to initialize")