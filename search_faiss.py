# ✅ Ultimate SalesBOT Script – Auto-sorts All Files on Startup
from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import fitz  # PyMuPDF
import os
import signal
import sys
import subprocess
import time
import json
import zipfile
import hashlib
import tempfile
import gc
import psutil
import requests
import threading

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()
processed_files_path = "processed_files.json"
processed_files = set()

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

FOLDER_NAMES = {
    "docs": "documents",
    "code": "code_files",
    "misc": "miscellaneous"
}

TEXT_TYPES = [".pdf", ".txt"]
CODE_TYPES = [".py", ".ipynb", ".js", ".json"]

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
    file = service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    service.files().update(fileId=file_id,
                           addParents=new_folder_id,
                           removeParents=previous_parents,
                           fields='id, parents').execute()

def categorize_file(name):
    ext = os.path.splitext(name)[-1].lower()
    if ext in TEXT_TYPES:
        return "docs"
    if ext in CODE_TYPES:
        return "code"
    return "misc"

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
    except Exception as e:
        print(f"❌ Could not extract from {path}: {e}")
    return ""

# ✅ Main Processor

def run_drive_processing(limit=25):
    global knowledge_base
    creds = authenticate_drive()
    if not creds:
        print("❌ Drive auth failed")
        return

    service = build("drive", "v3", credentials=creds)
    folder_ids = {k: ensure_folder(service, v) for k, v in FOLDER_NAMES.items()}
    results = service.files().list(q="not mimeType contains 'folder'",
                                   fields="files(id, name, mimeType)").execute()
    files = results.get("files", [])

    new_knowledge = {}
    processed = 0

    for file in files:
        if processed >= limit:
            break
        try:
            file_id, name = file["id"], file["name"]
            ext = os.path.splitext(name)[-1].lower()
            request = service.files().get_media(fileId=file_id)
            path = os.path.join(tempfile.gettempdir(), name)
            with open(path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            text = extract_text(path, ext)
            category = categorize_file(name)
            if text and not is_duplicate(text, name):
                if category == "docs":
                    new_knowledge[name] = text
                processed += 1
            move_file(service, file_id, folder_ids[category])
            os.remove(path)
        except Exception as e:
            print(f"❌ Failed: {file['name']} — {e}")

    knowledge_base.update(new_knowledge)
    np.save("ai_metadata.npy", knowledge_base)
    with open(processed_files_path, "w") as f:
        json.dump(list(processed_files), f)
    rebuild_faiss()

@app.route("/process_drive", methods=["POST"])
def process_drive():
    run_drive_processing()
    return jsonify({"message": "Drive processed and sorted."})

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

# ✅ Auto-sync

def auto_sync_drive(interval=5):
    def loop():
        while True:
            try:
                with app.test_request_context():
                    print("🔁 Auto-sorting Google Drive...")
                    run_drive_processing()
            except Exception as e:
                print(f"Auto-sync error: {e}")
            time.sleep(interval * 60)
    threading.Thread(target=loop, daemon=True).start()

signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting SalesBOT on port {port}")
    if os.system(f"netstat -an | grep {port}") == 0:
        kill_existing_processes()
    load_faiss()
    load_knowledge_base()
    run_drive_processing()  # 🚨 Auto-sort immediately on startup
    auto_sync_drive()
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
