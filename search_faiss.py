from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import fitz  # PyMuPDF for PDFs
import os
import signal
import sys
import subprocess
import time
import json
import zipfile
import hashlib
import tempfile
import io
import gc
import psutil

app = Flask(__name__)

# ✅ Kill existing Gunicorn & Waitress processes
def kill_existing_processes():
    print("🛑 Killing any existing Gunicorn & Waitress processes...")
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    print("✅ Killed old instances.")

# ✅ Google Drive API Authentication
SCOPES = ["https://www.googleapis.com/auth/drive"]

def authenticate_drive():
    try:
        SERVICE_ACCOUNT_JSON = json.loads(os.getenv("SERVICE_ACCOUNT_JSON", "{}"))
        if not SERVICE_ACCOUNT_JSON:
            raise ValueError("❌ No service account credentials found in environment variables.")
        creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_JSON, scopes=SCOPES)
        return creds
    except Exception as e:
        print(f"❌ Error authenticating Google Drive: {e}")
        return None

# ✅ Initialize AI Model
model = SentenceTransformer('all-MiniLM-L6-v2')

# ✅ Lazy Load FAISS index & metadata
index = None
knowledge_base = {}

def load_faiss():
    global index
    if index is None:
        try:
            index = faiss.read_index("ai_search_index.faiss")
            index.nprobe = 1
            print("✅ FAISS index loaded successfully.")
        except Exception as e:
            print(f"❌ Error loading FAISS index: {e}")
            index = None

def load_knowledge_base():
    global knowledge_base
    try:
        knowledge_base = np.load("ai_metadata.npy", allow_pickle=True).item()
        print("✅ Knowledge base loaded successfully.")
    except Exception as e:
        print(f"❌ Error loading knowledge base: {e}")
        knowledge_base = {}

# ✅ Remove Duplicates
file_hashes = set()
processed_files_path = "processed_files.json"
processed_files = set()

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

def is_duplicate(content, filename):
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    if content_hash in file_hashes or filename in processed_files:
        return True
    file_hashes.add(content_hash)
    processed_files.add(filename)
    return False

def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    print(f"🔍 RAM usage: {mem:.2f} MB")

# ✅ Graceful Shutdown Handling
def cleanup(signum, frame):
    print("🛑 Stopping SalesBOT API...")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

# ✅ Root Endpoint
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "SalesBOT API is running!", "status": "OK"}), 200

# ✅ Health Check Endpoint
@app.route("/health", methods=["GET"])
def health_check():
    print("📱 Health check ping received.")
    return jsonify({"status": "API is live", "message": "Endpoints are active."})

# ✅ Process and store Google Drive docs in small batches
@app.route("/process_drive", methods=["POST"])
def process_drive():
    global knowledge_base
    print("📂 Processing documents from Google Drive...")
    creds = authenticate_drive()
    if not creds:
        return jsonify({"error": "Google Drive authentication failed."}), 500

    try:
        service = build("drive", "v3", credentials=creds)
        zip_results = service.files().list(q="name contains '.zip'", fields="files(id, name)").execute()
        zip_files = zip_results.get('files', [])

        if not zip_files:
            return jsonify({"message": "No .zip files found in Google Drive."})

        limit = int(request.args.get("limit", 3))
        processed_this_run = 0
        new_knowledge = {}

        for file in zip_files:
            file_id = file["id"]
            file_name = file["name"]
            print(f"📦 Downloading: {file_name}")

            drive_request = service.files().get_media(fileId=file_id)
            temp_zip_path = os.path.join(tempfile.gettempdir(), file_name)
            with open(temp_zip_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, drive_request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            print(f"📂 Unzipping {file_name}...")
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                for zip_info in zip_ref.infolist():
                    if processed_this_run >= limit:
                        break
                    if zip_info.filename.endswith(".pdf"):
                        try:
                            with zip_ref.open(zip_info) as pdf_file:
                                doc = fitz.open("pdf", pdf_file.read())
                                text = "".join([page.get_text("text") for page in doc[:10]])
                                doc.close()
                                gc.collect()
                                if text and not is_duplicate(text, zip_info.filename):
                                    new_knowledge[zip_info.filename] = text.strip()
                                    processed_this_run += 1
                                    log_memory()
                        except Exception as e:
                            print(f"❌ Could not process {zip_info.filename}: {e}")

        knowledge_base.update(new_knowledge)
        np.save("ai_metadata.npy", knowledge_base)
        with open(processed_files_path, "w") as f:
            json.dump(list(processed_files), f)

        return jsonify({"message": f"Processed {processed_this_run} new file(s). Skipped already processed or duplicates."})

    except Exception as e:
        print(f"❌ Google Drive processing error: {e}")
        return jsonify({"error": str(e)}), 500

# ✅ Query knowledge base
@app.route("/query", methods=["GET"])
def query_knowledge():
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400

    print(f"🔎 Searching for: {question}")

    if index is None:
        load_faiss()
    if not knowledge_base:
        load_knowledge_base()
    if index is None:
        return jsonify({"error": "FAISS index not available. Try processing documents first."}), 500

    try:
        query_embedding = model.encode([question], convert_to_numpy=True).astype("float32")
        D, I = index.search(query_embedding, 3)

        file_keys = list(knowledge_base.keys())
        results = []
        for idx in I[0]:
            if idx == -1 or idx >= len(file_keys):
                continue
            file_name = file_keys[idx]
            insight_text = knowledge_base[file_name]
            results.append({
                "source": file_name,
                "insight": insight_text[:500] + "..."
            })

        if not results:
            print("⚠️ No relevant insights found.")
            return jsonify({"message": "No relevant insights found."})

        return jsonify(results)
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        return jsonify({"error": str(e)}), 500

# ✅ Run Flask App
if __name__ == "__main__":
    print("🔥 Starting SalesBOT API...")
    port = int(os.getenv("PORT", 10000))
    print(f"🌐 Running on port {port} (Render auto-detects this)")

    if os.system(f"netstat -an | grep {port}") == 0:
        print("⚠️ Port already in use. Restarting server...")
        kill_existing_processes()

    load_faiss()
    load_knowledge_base()

    print("✅ Available routes in Flask app:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.methods} -> {rule.rule}")

    from waitress import serve
    try:
        serve(app, host="0.0.0.0", port=port)
    except OSError as e:
        if "Address already in use" in str(e):
            print("❌ ERROR: Port 10000 is already in use.")
            kill_existing_processes()
            print("🔄 Restarting Gunicorn...")
            os.system(f"gunicorn -w 2 -b 0.0.0.0:{port} search_faiss:app")
        else:
            print(f"❌ Unexpected error: {e}")
            raise e
