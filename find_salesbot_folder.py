from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Authenticate
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

# Find the folder ID for "salesbot"
query = "title = 'salesbot' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
folders = drive.ListFile({'q': query}).GetList()

if folders:
    print(f"\n✅ Folder 'salesbot' found! Folder ID: {folders[0]['id']}\n")
else:
    print("\n❌ Folder 'salesbot' not found in Google Drive.\n")
