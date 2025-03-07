from googleapiclient.discovery import build
from google.oauth2 import service_account
import os

# ✅ Path to service account JSON file
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# ✅ Authenticate Google Drive using Service Account
def authenticate_drive():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return creds

# ✅ List Google Drive Files
def list_drive_files():
    creds = authenticate_drive()
    service = build("drive", "v3", credentials=creds)

    results = service.files().list(pageSize=10, fields="files(id, name, mimeType)").execute()
    files = results.get("files", [])

    if not files:
        print("⚠️ No files found in Google Drive.")
    else:
        print("✅ Found files in Google Drive:")
        for file in files:
            print(f"📂 {file['name']} (Type: {file['mimeType']}, ID: {file['id']})")

    return files

if __name__ == "__main__":
    list_drive_files()