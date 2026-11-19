from flask import Flask, render_template, request, jsonify
from data_loader import load_statutory_data, retrieve_top_sections
from ai_service import analyze_with_gemini

app = Flask(__name__)

# Startup statutory data load
load_statutory_data()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
@app.route("/api/query", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400

    sections = retrieve_top_sections(query, k=3)
    summary, model = analyze_with_gemini(query, sections)

    return jsonify({
        "query": query,
        "source_model": model,
        "gemini_summary": summary,
        "sections": sections
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
