from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return "SalesBOT is up and running!"

@app.route('/salesbot/query', methods=['POST'])
def salesbot_query():
    query = request.get_json().get('query')
    # Implement your data search logic here
    return jsonify({"response": f"Search results for query: {query}"})

if __name__ == '__main__':
    app.run(debug=True)
