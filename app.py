from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import sqlite3
import os
from datetime import datetime
import uuid

app = Flask(__name__)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

DB_NAME = "complaints.db"


# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DB_NAME)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT UNIQUE,
            complaint TEXT,
            category TEXT,
            priority TEXT,
            department TEXT,
            summary TEXT,
            action TEXT,
            impact TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- HOME ----------------

@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# ---------------- AI ANALYZER ----------------

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

Analyze this citizen complaint:

{complaint}

Return ONLY valid JSON.

Use exactly these fields:

{{
  "category": "",
  "priority": "",
  "department": "",
  "summary": "",
  "action": "",
  "impact": ""
}}

CATEGORY must be one of:

Roads
Water
Electricity
Sanitation
Drainage
Street Lights
Waste
Health
Education
Agriculture
Public Safety
Other

PRIORITY must be one of:

Low
Medium
High
Emergency

DEPARTMENT should identify the most appropriate
local authority or department.

Examples:

Roads -> Panchayat / Rural Development
Water -> Water Supply / Panchayat
Electricity -> Electricity Department
Street Lights -> Panchayat / Local Body
Waste -> Sanitation / Panchayat
Drainage -> Panchayat / Local Body
Health -> Public Health Department
Education -> Education Department
Agriculture -> Agriculture Department
Public Safety -> Police / Local Administration

Be practical and concise.

Do not invent phone numbers,
official names or guarantees.
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        ai_text = response.output_text.strip()

        # Remove markdown JSON fences if AI adds them
        ai_text = ai_text.replace("```json", "")
        ai_text = ai_text.replace("```", "")
        ai_text = ai_text.strip()

        import json

        analysis = json.loads(ai_text)

        category = analysis.get("category", "Other")
        priority = analysis.get("priority", "Medium")
        department = analysis.get(
            "department",
            "Local Administration"
        )
        summary = analysis.get("summary", "")
        action = analysis.get("action", "")
        impact = analysis.get("impact", "")

        # Generate complaint ID
        complaint_id = (
            "VCA-" +
            datetime.now().strftime("%Y%m%d") +
            "-" +
            uuid.uuid4().hex[:6].upper()
        )

        created_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Save complaint
        conn = sqlite3.connect(DB_NAME)

        conn.execute("""
            INSERT INTO complaints
            (
                complaint_id,
                complaint,
                category,
                priority,
                department,
                summary,
                action,
                impact,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            complaint_id,
            complaint,
            category,
            priority,
            department,
            summary,
            action,
            impact,
            "Assigned",
            created_at
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "complaint_id": complaint_id,
            "category": category,
            "priority": priority,
            "department": department,
            "summary": summary,
            "action": action,
            "impact": impact,
            "status": "Assigned"
        })

    except json.JSONDecodeError:

        return jsonify({
            "error": "AI returned an invalid response. Please try again."
        }), 500

    except Exception as e:

        return jsonify({
            "error": "Complaint processing failed.",
            "details": str(e)
        }), 500


# ---------------- VIEW COMPLAINT ----------------

@app.route("/api/complaint/<complaint_id>")
def get_complaint(complaint_id):

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    complaint = conn.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (complaint_id,)).fetchone()

    conn.close()

    if not complaint:

        return jsonify({
            "error": "Complaint not found."
        }), 404

    return jsonify(dict(complaint))


# ---------------- ALL COMPLAINTS ----------------

@app.route("/api/complaints")
def get_complaints():

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    complaints = conn.execute("""
        SELECT *
        FROM complaints
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify([
        dict(item)
        for item in complaints
    ])


# ---------------- DEPARTMENT COMPLAINTS ----------------

@app.route("/api/department/<path:department>")
def department_complaints(department):

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    complaints = conn.execute("""
        SELECT *
        FROM complaints
        WHERE department LIKE ?
        ORDER BY id DESC
    """, (
        "%" + department + "%",
    )).fetchall()

    conn.close()

    return jsonify([
        dict(item)
        for item in complaints
    ])


# ---------------- UPDATE STATUS ----------------

@app.route(
    "/api/complaint/<complaint_id>/status",
    methods=["POST"]
)
def update_status(complaint_id):

    data = request.get_json() or {}

    status = data.get("status", "").strip()

    allowed_statuses = [
        "Assigned",
        "In Progress",
        "Resolved",
        "Rejected"
    ]

    if status not in allowed_statuses:

        return jsonify({
            "error": "Invalid status."
        }), 400

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.execute("""
        UPDATE complaints
        SET status = ?
        WHERE complaint_id = ?
    """, (
        status,
        complaint_id
    ))

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    if updated == 0:

        return jsonify({
            "error": "Complaint not found."
        }), 404

    return jsonify({
        "success": True,
        "complaint_id": complaint_id,
        "status": status
    })


# ---------------- HEALTH ----------------

@app.route("/api/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Village Complaint Analyzer",
        "database": "connected"
    })


# ---------------- START SERVER ----------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
