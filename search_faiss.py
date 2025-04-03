# ✅ Ultimate SalesBOT Script – Full Drive Cleanup & Smart Sorter (Smart Logging & Dynamic Folders)
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
processing_status = {
    "running": False,
    "last_run": None,
    "log": {}
}

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

EXTENSION_MAP = {
    ".pdf": "PDFs",
    ".txt": "Word_Documents",
    ".docx": "Word_Documents",
    ".csv": "Excel_Files",
    ".xlsx": "Excel_Files",
    ".pptx": "PowerPoints",
    ".py": "Code_Files",
    ".ipynb": "Code_Files",
    ".js": "Code_Files",
    ".json": "Code_Files"
}

BASE_FOLDERS = set(["Word_Documents", "PDFs", "Excel_Files", "PowerPoints", "Code_Files", "Miscellaneous", "SalesBOT_Core_Files"])

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

def ensure_folder(service, name):
    results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{name}'",
                                   spaces='drive', fields="files(id, name)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]['id']
    file_metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']

def move_file(service, file_id, new_folder_id, move_log):
    try:
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        service.files().update(fileId=file_id, addParents=new_folder_id, removeParents=previous_parents, fields='id, parents').execute()
        move_log.append(file_id)
    except Exception as e:
        print(f"⚠️ Failed to move file {file_id}: {e}")

# ✅ Recursive crawler
def get_all_files_iteratively(service):
    stack = ["root"]
    all_files, folders = [], []
    while stack:
        current = stack.pop()
        try:
            subs = service.files().list(q=f"'{current}' in parents", fields="files(id, name, mimeType)").execute().get("files", [])
            for item in subs:
                if item['mimeType'] == 'application/vnd.google-apps.folder' and item['name'] not in BASE_FOLDERS:
                    folders.append((item['id'], item['name']))
                    stack.append(item['id'])
                elif 'folder' not in item['mimeType']:
                    all_files.append(item)
        except Exception as e:
            print(f"Folder scan fail: {e}")
    return all_files, folders

# ✅ Main Processor
def run_drive_processing():
    global knowledge_base, processing_status
    start = datetime.utcnow().isoformat()
    processing_status.update({"running": True, "last_run": start, "log": {}})
    move_log, error_log = {}, []

    try:
        creds = authenticate_drive()
        if not creds:
            processing_status["log"] = {"error": "Drive auth failed"}
            return

        service = build("drive", "v3", credentials=creds)
        files, folders = get_all_files_iteratively(service)

        ext_counter = {}
        for f in files:
            ext = os.path.splitext(f['name'])[-1].lower()
            ext_counter[ext] = ext_counter.get(ext, 0) + 1

        folder_ids = {}
        for ext, count in ext_counter.items():
            folder_name = EXTENSION_MAP.get(ext, "Miscellaneous") if count >= 10 else "Miscellaneous"
            if folder_name not in folder_ids:
                folder_ids[folder_name] = ensure_folder(service, folder_name)

        new_knowledge = {}
        for file in files:
            try:
                name, file_id = file['name'], file['id']
                ext = os.path.splitext(name)[-1].lower()
                request = service.files().get_media(fileId=file_id)
                path = os.path.join(tempfile.gettempdir(), name)
                with open(path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done, retries = False, 0
                    while not done and retries < 20:
                        _, done = downloader.next_chunk()
                        retries += 1
                if not done:
                    error_log.append({"file": name, "reason": "Timeout"})
                    continue
                text = extract_text(path, ext)
                category = EXTENSION_MAP.get(ext, "Miscellaneous") if ext_counter.get(ext, 0) >= 10 else "Miscellaneous"
                if text and not is_duplicate(text, name):
                    if category == "Word_Documents":
                        new_knowledge[name] = text
                move_file(service, file_id, folder_ids[category], move_log.setdefault(category, []))
                os.remove(path)
                log_memory()
            except Exception as e:
                error_log.append({"file": file.get('name'), "reason": str(e)})

        for fid, name in folders:
            if name in BASE_FOLDERS:
                continue
            contents = service.files().list(q=f"'{fid}' in parents", fields="files(id)").execute().get("files", [])
            if not contents:
                try:
                    service.files().delete(fileId=fid).execute()
                except Exception as e:
                    error_log.append({"folder": name, "reason": str(e)})

        knowledge_base.update(new_knowledge)
        np.save("ai_metadata.npy", knowledge_base)
        with open(processed_files_path, "w") as f:
            json.dump(list(processed_files), f)
        if new_knowledge:
            rebuild_faiss()

    except Exception as e:
        error_log.append({"fatal": str(e)})
    finally:
        processing_status.update({
            "running": False,
            "last_run": datetime.utcnow().isoformat(),
            "log": {
                "moved": move_log,
                "errors": error_log,
                "count": len(files),
                "processed": sum(len(v) for v in move_log.values()),
                "duplicates_skipped": len(processed_files),
            }
        })

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
    run_drive_processing()
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
