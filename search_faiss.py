# ✅ Ultimate SalesBOT Script – Boot-Safe + Drive Integrated (search_faiss.py)
from flask import Flask, request, jsonify
import threading
import os
import subprocess
import time
from waitress import serve
from datetime import datetime

# ✅ Shared runtime state + drive logic
from shared import model, index, knowledge_base, rebuild_faiss, log_memory, processed_files, processing_status
from sort_drive import run_drive_processing
import numpy as np

app = Flask(__name__)

def kill_existing_processes():
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

def launch_drive_sort():
    if not processing_status.get("boot_triggered"):
        processing_status["boot_triggered"] = True
        threading.Thread(target=run_drive_processing, daemon=True).start()

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "SalesBOT is live",
        "sorted_files": len(knowledge_base),
        "memory_MB": log_memory()
    })

@app.route("/status", methods=["GET"])
def status():
    return jsonify(processing_status)

@app.route("/mem", methods=["GET"])
def memory_status():
    return jsonify({"memory_MB": log_memory()})

@app.route("/process_drive", methods=["POST"])
def process_drive():
    if processing_status["running"]:
        return jsonify({"message": "Drive processing is already running."}), 429
    threading.Thread(target=run_drive_processing, daemon=True).start()
    return jsonify({"message": "Drive processing started."}), 202

@app.route("/query")
def query():
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400
    if index is None or not knowledge_base:
        return jsonify({"error": "Search system not ready. Try again shortly."}), 503
    try:
        query_embedding = model.encode([question], convert_to_numpy=True).astype("float32")
        D, I = index.search(query_embedding, 3)
        keys = list(knowledge_base.keys())
        results = []
        for idx in I[0]:
            if idx == -1 or idx >= len(keys):
                continue
            results.append({
                "source": keys[idx],
                "insight": knowledge_base[keys[idx]][:500] + "..."
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Query failed: {str(e)}"}), 500

@app.route("/reload_index", methods=["POST"])
def reload_index():
    try:
        rebuild_faiss()
        return jsonify({"message": "FAISS index rebuilt."}), 200
    except Exception as e:
        return jsonify({"error": f"Rebuild failed: {str(e)}"}), 500

@app.route("/last_run_log", methods=["GET"])
def last_run_log():
    return jsonify(processing_status.get("log", {}))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"\n\n🚀 Booting SalesBOT on port {port}\n")
    kill_existing_processes()
    with app.app_context():
        launch_drive_sort()
    serve(app, host="0.0.0.0", port=port)
