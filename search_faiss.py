from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import signal
import sys
import subprocess
import time

app = Flask(__name__)

# ✅ Kill existing Gunicorn & Waitress processes
def kill_existing_processes():
    print("🛑 Killing any existing Gunicorn & Waitress processes...")
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)  # Wait 2 seconds before restarting
    print("✅ Killed old instances.")

# ✅ Initialize AI Model
model = SentenceTransformer('all-MiniLM-L6-v2')

# ✅ Lazy Load FAISS index & metadata
index = None
knowledge_base = {}

def load_faiss():
    """ Loads FAISS index only when required to reduce memory usage """
    global index
    if index is None:
        try:
            index = faiss.read_index("ai_search_index.faiss")
            index.nprobe = 1  # Reduce FAISS search complexity
            print("✅ FAISS index loaded successfully.")
        except Exception as e:
            print(f"❌ Error loading FAISS index: {e}")
            index = None

# ✅ Graceful Shutdown Handling
def cleanup(signum, frame):
    print("🛑 Stopping SalesBOT API...")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)  # Handle Ctrl+C

# ✅ Root Endpoint (Fixes Render's Health Check Issue)
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "SalesBOT API is running!", "status": "OK"}), 200

# ✅ Health Check Endpoint
@app.route("/health", methods=["GET"])
def health_check():
    print("📡 Health check ping received.")
    return jsonify({"status": "API is live", "message": "Endpoints are active."})

# ✅ Query knowledge base
@app.route("/query", methods=["GET"])
def query_knowledge():
    """ Search for insights from the stored knowledge base """
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400

    print(f"🔎 Searching for: {question}")

    if index is None:
        load_faiss()
    if index is None:
        return jsonify({"error": "FAISS index not available. Try processing documents first."}), 500
    try:
        query_embedding = model.encode([question], convert_to_numpy=True).astype("float32")
        D, I = index.search(query_embedding, 3)  # Find top 3 related insights

        results = []
        for idx in I[0]:
            if idx == -1:
                continue
            results.append({"insight": f"Result {idx}"})  # Mock response for now

        return jsonify(results)
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        return jsonify({"error": str(e)}), 500

# ✅ Run Flask App
if __name__ == "__main__":
    print("🔥 Starting SalesBOT API...")

    # 🔧 Ensure Render uses the correct port
    port = int(os.getenv("PORT", 10000))  # 🔥 Force Flask to use port 10000
    print(f"🌐 Running on port {port} (Render auto-detects this)")

    # Kill existing processes **only if needed**
    if os.system(f"netstat -an | grep {port}") == 0:
        print("⚠️ Port already in use. Restarting server...")
        kill_existing_processes()

    # Load FAISS index
    load_faiss()

    # Debugging: List all active routes
    print("✅ Available routes in Flask app:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.methods} -> {rule.rule}")

    # Run Waitress instead of Flask for production
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
