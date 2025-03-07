import os
import zipfile
import shutil
import py7zr

# ✅ Define Google Drive Path
drive_path = r"I:\My Drive"
extracted_path = os.path.join(drive_path, "extracted_files")

# ✅ Create the extracted folder if it doesn't exist
if not os.path.exists(extracted_path):
    os.makedirs(extracted_path)

# ✅ Function to unzip files
def unzip_file(zip_path, output_folder):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_folder)
        print(f"✅ Extracted: {zip_path}")
    except zipfile.BadZipFile:
        print(f"❌ Corrupt ZIP: {zip_path}")

# ✅ Function to extract 7z files
def extract_7z(file_path, output_folder):
    try:
        with py7zr.SevenZipFile(file_path, mode='r') as archive:
            archive.extractall(output_folder)
        print(f"✅ Extracted: {file_path}")
    except Exception as e:
        print(f"❌ Failed to extract {file_path}: {e}")

# ✅ Scan Drive for ZIP & 7z Files
for root, _, files in os.walk(drive_path):
    for file in files:
        file_path = os.path.join(root, file)
        file_ext = file.lower().split(".")[-1]

        # ✅ Unzip ZIP files
        if file_ext == "zip":
            unzip_file(file_path, extracted_path)
        
        # ✅ Extract 7z files
        elif file_ext == "7z":
            extract_7z(file_path, extracted_path)

print("✅ All ZIP and 7z files extracted!")
