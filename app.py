from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():

    data = request.get_json() or {}

    complaint = data.get("complaint", "").strip()

    if not complaint:
        return jsonify({
            "error": "Please enter a complaint."
        }), 400

    complaint = complaint[:10000]

    prompt = f"""
You are an AI Village Complaint Analyzer.

Analyze the following citizen complaint:

{complaint}

Return the result in this exact structure:

CATEGORY:
Choose one:
Roads, Water, Electricity, Sanitation,
Drainage, Street Lights, Waste,
Health, Education, Agriculture,
Public Safety, Other

PRIORITY:
Choose one:
Low, Medium, High, Emergency

RESPONSIBLE DEPARTMENT:
Identify the most appropriate local government
department or authority.

COMPLAINT SUMMARY:
Give a short clear summary.

KEY PROBLEM:
Explain the main problem.

SUGGESTED ACTION:
Give practical steps the responsible authority
could take.

CITIZEN IMPACT:
Explain who is affected and how.

Be concise, practical and neutral.
Do not invent specific government officials,
phone numbers or guarantees.
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        return jsonify({
            "success": True,
            "analysis": response.output_text
        })

    except Exception as e:

        return jsonify({
            "error": "AI analysis failed",
            "details": str(e)
        }), 500


@app.route("/api/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Village Complaint Analyzer"
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
