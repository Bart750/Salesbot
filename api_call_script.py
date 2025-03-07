import requests

# ✅ Replace with your actual Ngrok URL
API_URL = "https://0367-2a00-23c8-4aa9-200-d171-5aa1-47ef-ca01.ngrok-free.app/search"

# ✅ Define search query and optional file type
query = "best sales strategies"
file_type = "pdf"  # Change to "pptx", "docx", etc. or None for all file types

def call_salesbot_api():
    """Calls the SalesBOT API and prints the response."""
    try:
        response = requests.get(API_URL, params={"query": query, "file_type": file_type}, timeout=10)
        
        # Check if response is successful
        if response.status_code == 200:
            print("\n🔍 **SalesBOT AI API Response:**\n")
            for i, result in enumerate(response.json(), 1):
                print(f"{i}. 📄 {result['file_name']}")
                print(f"   🔗 Link: {result['google_drive_link']}")
                print(f"   🏆 Relevance Score: {result['relevance_score']}\n")
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ API is not responding: {e}")

if __name__ == "__main__":
    print("🚀 Calling SalesBOT API...\n")
    call_salesbot_api()
