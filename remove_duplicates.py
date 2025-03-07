import os
import hashlib

# ✅ Fixed Google Drive Path
drive_path = r"I:\My Drive\salesbot"  # Ensure proper formatting

hashes = {}
duplicates = []

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
    print("✅ Google Drive is accessible! Scanning for duplicates...")

    for root, dirs, files in os.walk(drive_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_hash = get_file_hash(file_path)

            if file_hash:  # Ensure hash was generated
                if file_hash in hashes:
                    print(f"🗑 Deleting Duplicate: {file_path}")
                    os.remove(file_path)
                    duplicates.append(file_path)
                else:
                    hashes[file_hash] = file_path

    print(f"✅ Removed {len(duplicates)} duplicate files!")
else:
    print("❌ Google Drive path not found. Check if it's mounted correctly.")
