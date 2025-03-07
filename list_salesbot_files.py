from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Authenticate with Google Drive
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

# 🔹 Define your main folder name in Google Drive
FOLDER_NAME = "salesbot"

# Get the list of all files in Google Drive
file_list = drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()

# Find the salesbot folder ID
folder_id = None
for file in file_list:
    if file['title'] == FOLDER_NAME and file['mimeType'] == 'application/vnd.google-apps.folder':
        folder_id = file['id']
        break

if not folder_id:
    print(f"❌ Folder '{FOLDER_NAME}' not found in Google Drive.")
    exit()

# List all files inside the "salesbot" folder
sales_files = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()

# Print file names and IDs
print("\n📂 Files in 'salesbot' folder:\n")
for file in sales_files:
    print(f"📄 {file['title']} - ID: {file['id']}")

print("\n✅ File listing complete!")
