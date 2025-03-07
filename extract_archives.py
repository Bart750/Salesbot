import os
import zipfile
import patoolib
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Authenticate and create the PyDrive client
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

# 🔹 Updated "salesbot" Folder ID
SALESBOT_FOLDER_ID = "1jnvN5qSJSjbNpKrpO6C87Shj5LgRHENy"

# Create a local folder to store extracted files
EXTRACTION_FOLDER = "C:/Users/Simon/Desktop/salesbot/extracted_files"
os.makedirs(EXTRACTION_FOLDER, exist_ok=True)

# Get the list of all files in "salesbot" folder
sales_files = drive.ListFile({'q': f"'{SALESBOT_FOLDER_ID}' in parents and trashed=false"}).GetList()

# Process each file
for file in sales_files:
    file_title = file["title"]
    file_id = file["id"]
    file_path = os.path.join(EXTRACTION_FOLDER, file_title)

    if file_title.endswith(".zip") or file_title.endswith(".7z"):
        print(f"📥 Downloading {file_title} from Google Drive...")
        file.GetContentFile(file_path)

        # Extract ZIP files
        if file_title.endswith(".zip"):
            print(f"📂 Extracting {file_title}...")
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(EXTRACTION_FOLDER)

        # Extract 7Z files
        elif file_title.endswith(".7z"):
            print(f"📂 Extracting {file_title}...")
            patoolib.extract_archive(file_path, outdir=EXTRACTION_FOLDER)

        print(f"✅ {file_title} extracted successfully!\n")

print("🚀 All archives have been extracted!")
