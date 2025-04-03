# ✅ Ultimate SalesBOT Script – Full Drive Cleanup & Smart Sorter (Patched for Accuracy)
from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import fitz  # PyMuPDF
import docx
import os
import signal
import sys
import subprocess
import time
import json
import hashlib
import tempfile
import gc
import psutil
import requests
import threading
import traceback
from datetime import datetime

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()
processed_files_path = "processed_files.json"
processed_files = set()
processing_status = {"running": False, "last_run": None}

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

FOLDER_NAMES = {
    "docs": "Word_Documents",
    "pdf": "PDFs",
    "code": "Code_Files",
    "data": "Excel_Files",
    "slides": "PowerPoints",
    "misc": "Miscellaneous",
    "core": "SalesBOT_Core_Files"
}

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".txt": "docs",
    ".docx": "docs",
    ".csv": "data",
    ".xlsx": "data",
    ".pptx": "slides",
    ".py": "code",
    ".ipynb": "code",
    ".js": "code",
    ".json": "code"
}

BATCH_SIZE = 25

# ✅ Kill stuck servers
def kill_existing_processes():
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

# ✅ Google Drive auth
def authenticate_drive():
    try:
        json_data = os.getenv("SERVICE_ACCOUNT_JSON")
        if json_data:
            creds = service_account.Credentials.from_service_account_info(json.loads(json_data), scopes=SCOPES)
        else:
            creds = service_account.Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
        return creds
    except Exception as e:
        print(f"Auth failed: {e}")
        return None

# ✅ FAISS logic
def rebuild_faiss():
    global index
    if not knowledge_base:
        return
    embeddings = [model.encode([t], convert_to_numpy=True)[0].astype("float32") for t in knowledge_base.values()]
    index = faiss.IndexFlatL2(len(embeddings[0]))
    index.add(np.array(embeddings))
    faiss.write_index(index, "ai_search_index.faiss")
    gc.collect()

def load_faiss():
    global index
    try:
        index = faiss.read_index("ai_search_index.faiss")
        index.nprobe = 1
    except:
        index = None

def load_knowledge_base():
    global knowledge_base
    try:
        knowledge_base = dict(np.load("ai_metadata.npy", allow_pickle=True).item())
    except:
        knowledge_base = {}

# ✅ Utils
def is_duplicate(content, filename):
    h = hashlib.md5(content.encode("utf-8")).hexdigest()
    if h in file_hashes or filename in processed_files:
        return True
    file_hashes.add(h)
    processed_files.add(filename)
    return False

def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    print(f"RAM: {mem:.2f} MB")

def ensure_folder(service, name, parent_id=None):
    results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{name}'",
                                   spaces='drive', fields="files(id, name)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]['id']
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']

def move_file(service, file_id, new_folder_id):
    try:
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        service.files().update(fileId=file_id,
                               addParents=new_folder_id,
                               removeParents=previous_parents,
                               fields='id, parents').execute()

        # ✅ Verify move worked
        updated = service.files().get(fileId=file_id, fields="parents").execute()
        if new_folder_id not in updated.get("parents", []):
            print(f"❌ Move failed: {file_id} NOT in expected folder.")
        else:
            print(f"📂 Moved file {file_id} to folder {new_folder_id}")

    except Exception as e:
        print(f"⚠️ Failed to move file {file_id}: {e}")

def categorize_file(name):
    ext = os.path.splitext(name)[-1].lower()
    return EXTENSION_MAP.get(ext, "misc")

def extract_text(path, ext):
    try:
        if ext == ".pdf":
            doc = fitz.open(path)
            text = "".join([p.get_text("text") for p in doc[:10]]).strip()
            doc.close()
            return text
        elif ext == ".txt":
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        elif ext == ".docx":
            doc = docx.Document(path)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        print(f"❌ Could not extract from {path}: {e}")
    return ""

# ✅ Recursive file + folder crawl
def get_all_files_iteratively(service, parent_id="root"):
    stack = [parent_id]
    all_files = []
    folders = []
    while stack:
        current = stack.pop()
        try:
            subfolders = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and '{current}' in parents",
                                              fields="files(id, name)").execute().get("files", [])
            for f in subfolders:
                if f["name"] not in FOLDER_NAMES.values():
                    folders.append((f["id"], f["name"]))
                    stack.append(f["id"])
            files = service.files().list(q=f"not mimeType contains 'folder' and '{current}' in parents",
                                         fields="files(id, name, mimeType, size)").execute().get("files", [])
            all_files.extend(files)
        except Exception as e:
            print(f"⚠️ Folder scan error: {e}")
    return all_files, folders

# ✅ Main Processor (Batch-safe on boot + Cleanup)
def run_drive_processing():
    global knowledge_base, processing_status
    processing_status["running"] = True
    processing_status["last_run"] = datetime.utcnow().isoformat()

    try:
        creds = authenticate_drive()
        if not creds:
            print("❌ Drive auth failed")
            return

        service = build("drive", "v3", credentials=creds)
        folder_ids = {k: ensure_folder(service, v) for k, v in FOLDER_NAMES.items()}
        files, all_folders = get_all_files_iteratively(service)

        files_to_process = [f for f in files if f["name"] not in processed_files]
        new_knowledge = {}
        total = len(files_to_process)
        print(f"📦 {total} unprocessed files found. Processing first {BATCH_SIZE}...")

        for i, file in enumerate(files_to_process[:BATCH_SIZE]):
            try:
                file_id, name = file["id"], file["name"]
                ext = os.path.splitext(name)[-1].lower()
                print(f"▶️ [{i+1}/{BATCH_SIZE}] {name}")
                request = service.files().get_media(fileId=file_id)
                path = os.path.join(tempfile.gettempdir(), name)
                with open(path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request, chunksize=512*1024)
                    done = False
                    counter = 0
                    while not done and counter < 20:
                        _, done = downloader.next_chunk()
                        counter += 1
                    if not done:
                        print(f"⚠️ Timeout: {name}")
                        continue

                text = extract_text(path, ext)
                category = categorize_file(name)
                if text and not is_duplicate(text, name):
                    if category == "docs":
                        new_knowledge[name] = text
                move_file(service, file_id, folder_ids[category])
                os.remove(path)
                gc.collect()
                log_memory()
                print(f"✅ Done with {name}")
                time.sleep(0.25)
            except Exception as e:
                print(f"❌ Error with {file.get('name')}: {e}")
                traceback.print_exc()

        # Delete empty folders (excluding core folders)
        for folder_id, name in all_folders:
            if name in FOLDER_NAMES.values():
                continue
            res = service.files().list(q=f"'{folder_id}' in parents",
                                       fields="files(id)").execute().get("files", [])
            if not res:
                try:
                    service.files().delete(fileId=folder_id).execute()
                    print(f"🗑️ Deleted empty folder: {name}")
                except Exception as e:
                    print(f"⚠️ Could not delete folder {name}: {e}")

        knowledge_base.update(new_knowledge)
        np.save("ai_metadata.npy", knowledge_base)
        with open(processed_files_path, "w") as f:
            json.dump(list(processed_files), f)

        if new_knowledge:
            rebuild_faiss()

    except Exception as top:
        print("🔥 TOP-LEVEL CRASH 🔥")
        traceback.print_exc()
    finally:
        processing_status["running"] = False

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "SalesBOT is live", "sorted": len(knowledge_base)})

@app.route("/mem", methods=["GET"])
def memory_status():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    return jsonify({"memory_MB": mem})

@app.route("/status", methods=["GET"])
def status():
    return jsonify(processing_status)

@app.route("/process_drive", methods=["POST"])
def process_drive():
    threading.Thread(target=run_drive_processing, daemon=True).start()
    return jsonify({"message": "Drive processing started in background."}), 202

@app.route("/query")
def query():
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400
    if index is None:
        load_faiss()
    if not knowledge_base:
        load_knowledge_base()
    if index is None:
        return jsonify({"error": "No FAISS index"}), 500

    query_embedding = model.encode([question], convert_to_numpy=True).astype("float32")
    D, I = index.search(query_embedding, 3)
    keys = list(knowledge_base.keys())
    results = []
    for idx in I[0]:
        if idx == -1 or idx >= len(keys):
            continue
        results.append({"source": keys[idx], "insight": knowledge_base[keys[idx]][:500] + "..."})
    return jsonify(results)

signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting SalesBOT on port {port}")
    kill_existing_processes()
    load_faiss()
    load_knowledge_base()
    run_drive_processing()  # ✅ Run sorting immediately on startup for debug
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
