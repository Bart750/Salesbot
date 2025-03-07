import os
import shutil
import hashlib

# ✅ Google Drive Path
drive_path = r"I:\My Drive\salesbot"

# ✅ Define Folders for Sorting
SORT_FOLDERS = {
    "PDFs": [".pdf"],
    "PowerPoints": [".pptx", ".ppt"],
    "WordDocs": [".docx", ".doc"],
    "ExcelFiles": [".xls", ".xlsx", ".csv"],
    "TextFiles": [".txt"],
    "OtherFiles": []  # Anything not categorized
}

hashes = {}
duplicates = []
sorted_files = 0

def get_file_hash(file_path):
    """Generate a hash for a file"""
    hasher = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
        return None  # Skip unreadable files

# ✅ Ensure Drive Path Exists Before Running
if os.path.exists(drive_path):
    print("✅ Google Drive is accessible! Sorting and removing duplicates...")

    for root, dirs, files in os.walk(drive_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[1].lower()
            file_hash = get_file_hash(file_path)

            # 🗑 Remove Duplicates
            if file_hash:
                if file_hash in hashes:
                    print(f"🗑 Deleting Duplicate: {file_path}")
                    os.remove(file_path)
                    duplicates.append(file_path)
                    continue  # Skip to next file
                else:
                    hashes[file_hash] = file_path

            # 📂 Move Files into Sorted Folders
            destination_folder = None
            for folder, extensions in SORT_FOLDERS.items():
                if file_ext in extensions:
                    destination_folder = os.path.join(drive_path, folder)
                    break
            if not destination_folder:
                destination_folder = os.path.join(drive_path, "OtherFiles")

            # ✅ Create folder if it doesn't exist
            if not os.path.exists(destination_folder):
                os.makedirs(destination_folder)

            # ✅ Move file
            new_file_path = os.path.join(destination_folder, file)
            shutil.move(file_path, new_file_path)
            sorted_files += 1
            print(f"📂 Moved: {file} → {destination_folder}")

    # 🗑 Remove Empty Folders
    for root, dirs, _ in os.walk(drive_path, topdown=False):
        for folder in dirs:
            folder_path = os.path.join(root, folder)
            if not os.listdir(folder_path):  # If folder is empty
                os.rmdir(folder_path)
                print(f"🗑 Removed Empty Folder: {folder_path}")

    print(f"✅ Removed {len(duplicates)} duplicates.")
    print(f"✅ Sorted {sorted_files} files into categories.")
else:
    print("❌ Google Drive path not found. Check if it's mounted correctly.")
