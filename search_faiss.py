from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from google.oauth2 import service_account
import fitz  # PyMuPDF for PDFs

app = Flask(__name__)

# ✅ Path to service account JSON file
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# ✅ Authenticate Google Drive using Service Account
def authenticate_drive():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return creds

# ✅ Initialize AI Model
model = SentenceTransformer('all-MiniLM-L6-v2')

# ✅ Load FAISS index and metadata
try:
    index = faiss.read_index("ai_search_index.faiss")
    file_metadata = np.load("ai_metadata.npy", allow_pickle=True)
    print("✅ FAISS index and metadata loaded successfully.")
except Exception as e:
    print(f"❌ Error loading FAISS index or metadata: {e}")
    exit()

# ✅ Generate Google Drive link from file ID
def get_drive_link(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"

# ✅ Search function
def search_files(query, top_k=5):
    query_embedding = model.encode([query], convert_to_numpy=True).astype("float32")
    D, I = index.search(query_embedding, top_k)

    results = []
    for i in range(len(I[0])):
        if I[0][i] == -1:
            continue
        file_name, file_id = file_metadata[I[0][i]].split(" | ")
        results.append({"file_name": file_name, "drive_link": get_drive_link(file_id), "score": float(D[0][i])})

    return results

# ✅ Extract text from a Google Drive file
def extract_text_from_drive(file_id):
    creds = authenticate_drive()
    service = build("drive", "v3", credentials=creds)
    request = service.files().get_media(fileId=file_id)
    
    with fitz.open(stream=request.execute(), filetype="pdf") as doc:
        text = "".join([page.get_text("text") for page in doc])
    
    return text.strip()

# ✅ API Endpoint for Searching Files
@app.route("/search", methods=["GET"])
def api_search():
    query = request.args.get("query")
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    results = search_files(query)
    if not results:
        return jsonify({"message": "No relevant files found."})
    
    # Optionally extract summary of the top result
    top_result = results[0]
    file_id = top_result["drive_link"].split("/")[-2]  # Extract file ID
    text_content = extract_text_from_drive(file_id)
    top_result["summary"] = text_content[:500] + "..." if len(text_content) > 500 else text_content
    
    return jsonify(results)

# ✅ Run Flask App
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
