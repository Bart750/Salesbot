#!/bin/bash

# 👇 Update this to your actual host/port if not localhost
BASE_URL="http://localhost:10000"

echo "🔍 GET /status"
curl -s "$BASE_URL/status" | jq
echo -e "\n-----------------------------\n"

echo "📜 GET /last_run_log"
curl -s "$BASE_URL/last_run_log" | jq
echo -e "\n-----------------------------\n"

echo "📂 GET /files"
curl -s "$BASE_URL/files" | jq
echo -e "\n-----------------------------\n"

echo "🧠 GET /debug"
curl -s "$BASE_URL/debug" | jq
echo -e "\n-----------------------------\n"

echo "🔁 POST /reload_index"
curl -s -X POST "$BASE_URL/reload_index" | jq
echo -e "\n-----------------------------\n"

echo "💬 GET /query?question=How do we position TGI?"
curl -s "$BASE_URL/query?question=How%20do%20we%20position%20TGI?" | jq
echo -e "\n-----------------------------\n"
