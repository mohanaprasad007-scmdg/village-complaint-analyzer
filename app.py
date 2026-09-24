from flask import Flask, request, jsonify, send_from_directory, session, redirect
from openai import OpenAI
import sqlite3
import os
from datetime import datetime
import uuid
import json

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

# OpenAI
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

DB_NAME = "complaints.db"


# =========================================================
# DEPARTMENT CONFIGURATION
# =========================================================

DEPARTMENTS = {
    "ROAD": {
        "name": "Panchayat / Rural Development",
        "username": "road",
        "password": "road123"
    },
    "WATER": {
        "name": "Water Supply Department",
        "username": "water",
        "password": "water123"
    },
    "ELECTRICITY": {
        "name": "Electricity Department",
        "username": "electricity",
        "password": "electricity123"
    },
    "STREET_LIGHT": {
        "name": "Panchayat / Local Body",
        "username": "streetlight",
        "password": "street123"
    },
    "SANITATION": {
        "name": "Sanitation Department",
        "username": "sanitation",
        "password": "sanitation123"
    },
    "DRAINAGE": {
        "name": "Panchayat / Local Body",
        "username": "drainage",
        "password": "drainage123"
    },
    "HEALTH": {
        "name": "Public Health Department",
        "username": "health",
        "password": "health123"
    },
    "EDUCATION": {
        "name": "Education Department",
        "username": "education",
        "password": "education123"
    },
    "AGRICULTURE": {
        "name": "Agriculture Department",
        "username": "agriculture",
        "password": "agriculture123"
    },
    "SAFETY": {
        "name": "Police / Public Safety",
        "username": "police",
        "password": "police123"
    },
    "OTHER": {
        "name": "Panchayat / Local Administration",
        "username": "admin",
        "password": "admin123"
    }
}


# =========================================================
# DATABASE
# =========================================================

def init_db():
    conn = sqlite3.connect(DB_NAME)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT UNIQUE,
            complaint TEXT,
            category TEXT,
            priority TEXT,
            department_code TEXT,
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


def upgrade_old_database():
    conn = sqlite3.connect(DB_NAME)

    columns = [
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(complaints)"
        ).fetchall()
    ]

    if "department_code" not in columns:
        conn.execute("""
            ALTER TABLE complaints
            ADD COLUMN department_code TEXT
        """)

    conn.commit()
    conn.close()


init_db()
upgrade_old_database()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# LOGIN PAGE
# =========================================================

@app.route("/login")
def login():
    if "department_code" in session:
        return redirect("/admin")

    return send_from_directory(
        ".",
        "login.html"
    )


# =========================================================
# ADMIN PAGE
# =========================================================

@app.route("/admin")
def admin():
    if "department_code" not in session:
        return redirect("/login")

    return send_from_directory(
        ".",
        "admin.html"
    )


# =========================================================
# LOGIN API
# =========================================================

@app.route("/api/login", methods=["POST"])
def api_login():

    data = request.get_json() or {}

    username = str(
        data.get("username", "")
    ).strip().lower()

    password = str(
        data.get("password", "")
    )

    for code, department in DEPARTMENTS.items():

        if (
            username == department["username"]
            and password == department["password"]
        ):

            session["department_code"] = code
            session["department_name"] = department["name"]

            return jsonify({
                "success": True,
                "department_code": code,
                "department": department["name"],
                "redirect": "/admin"
            })

    return jsonify({
        "error": "Invalid username or password."
    }), 401


# =========================================================
# LOGOUT
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "success": True,
        "redirect": "/login"
    })


# =========================================================
# CURRENT USER
# =========================================================

@app.route("/api/me")
def current_user():

    if "department_code" not in session:

        return jsonify({
            "authenticated": False
        }), 401

    code = session["department_code"]

    department = DEPARTMENTS.get(code)

    if not department:

        session.clear()

        return jsonify({
            "authenticated": False
        }), 401

    return jsonify({
        "authenticated": True,
        "department_code": code,
        "department": department["name"]
    })


# =========================================================
# AI COMPLAINT ANALYSIS
# =========================================================

@app.route("/api/analyze", methods=["POST"])
def analyze():

    data = request.get_json(silent=True) or {}

    complaint = str(
        data.get("complaint", "")
    ).strip()

    if not complaint:

        return jsonify({
            "error": "Please enter a complaint."
        }), 400

    complaint = complaint[:10000]

    # Check API key before making the request
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:

        return jsonify({
            "error": "OpenAI API key is not configured.",
            "details": "Please add OPENAI_API_KEY in Render Environment Variables."
        }), 500

    prompt = f"""
You are an AI Village Complaint Analyzer.

Analyze this citizen complaint:

{complaint}

Return ONLY valid JSON.

Use exactly these fields:

{{
  "category": "",
  "priority": "",
  "department_code": "",
  "summary": "",
  "action": "",
  "impact": ""
}}

CATEGORY must be exactly one of:

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

PRIORITY must be exactly one of:

Low
Medium
High
Emergency

DEPARTMENT_CODE must be EXACTLY one of:

ROAD
WATER
ELECTRICITY
STREET_LIGHT
SANITATION
DRAINAGE
HEALTH
EDUCATION
AGRICULTURE
SAFETY
OTHER

Use these routing rules:

Road problems -> ROAD
Drinking water / water supply -> WATER
Power / electrical problems -> ELECTRICITY
Street lamp / street light problems -> STREET_LIGHT
Garbage / waste collection -> SANITATION
Drainage / sewage problems -> DRAINAGE
Medical / health problems -> HEALTH
School / education problems -> EDUCATION
Farming / crop / agricultural problems -> AGRICULTURE
Crime / immediate public safety -> SAFETY
Anything else -> OTHER

Examples:

"Road has many potholes"
-> ROAD

"No drinking water"
-> WATER

"Power has been disconnected"
-> ELECTRICITY

"Street lights are not working"
-> STREET_LIGHT

"Garbage is not collected"
-> SANITATION

"Drain is blocked"
-> DRAINAGE

"Village health centre has no doctor"
-> HEALTH

"School building is damaged"
-> EDUCATION

"Farmers need irrigation support"
-> AGRICULTURE

"Someone is creating a public safety problem"
-> SAFETY

Be concise and practical.

Do not invent phone numbers,
official names or guarantees.
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        ai_text = response.output_text.strip()

        # Remove markdown code fences if returned
        ai_text = ai_text.replace(
            "```json",
            ""
        )

        ai_text = ai_text.replace(
            "```",
            ""
        )

        ai_text = ai_text.strip()

        analysis = json.loads(ai_text)

        category = str(
            analysis.get(
                "category",
                "Other"
            )
        ).strip()

        priority = str(
            analysis.get(
                "priority",
                "Medium"
            )
        ).strip()

        department_code = str(
            analysis.get(
                "department_code",
                "OTHER"
            )
        ).upper().strip()

        # Safety fallback
        if department_code not in DEPARTMENTS:
            department_code = "OTHER"

        department = DEPARTMENTS[
            department_code
        ]["name"]

        summary = str(
            analysis.get(
                "summary",
                ""
            )
        ).strip()

        action = str(
            analysis.get(
                "action",
                ""
            )
        ).strip()

        impact = str(
            analysis.get(
                "impact",
                ""
            )
        ).strip()

        complaint_id = (
            "VCA-"
            + datetime.now().strftime("%Y%m%d")
            + "-"
            + uuid.uuid4().hex[:6].upper()
        )

        created_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = sqlite3.connect(DB_NAME)

        conn.execute("""
            INSERT INTO complaints
            (
                complaint_id,
                complaint,
                category,
                priority,
                department_code,
                department,
                summary,
                action,
                impact,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            complaint_id,
            complaint,
            category,
            priority,
            department_code,
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
            "department_code": department_code,
            "department": department,
            "summary": summary,
            "action": action,
            "impact": impact,
            "status": "Assigned"
        })

    except json.JSONDecodeError as e:

        print(
            "AI JSON ERROR:",
            repr(e)
        )

        return jsonify({
            "error": "AI returned an invalid response.",
            "details": str(e)
        }), 500

    except Exception as e:

        # IMPORTANT:
        # This block must stay indented.
        print(
            "OPENAI/API ERROR:",
            repr(e)
        )

        return jsonify({
            "error": "Complaint processing failed.",
            "details": str(e)
        }), 500


# =========================================================
# CITIZEN TRACKING
# =========================================================

@app.route("/api/complaint/<complaint_id>")
def get_complaint(complaint_id):

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    complaint = conn.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (
        complaint_id
    )).fetchone()

    conn.close()

    if not complaint:

        return jsonify({
            "error": "Complaint not found."
        }), 404

    return jsonify(
        dict(complaint)
    )


# =========================================================
# DEPARTMENT COMPLAINTS
# =========================================================

@app.route("/api/department")
def department_complaints():

    if "department_code" not in session:

        return jsonify({
            "error": "Authentication required."
        }), 401

    code = session["department_code"]

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    complaints = conn.execute("""
        SELECT *
        FROM complaints
        WHERE department_code = ?
        ORDER BY id DESC
    """, (
        code
    )).fetchall()

    conn.close()

    return jsonify([
        dict(item)
        for item in complaints
    ])


# =========================================================
# ALL COMPLAINTS - ADMIN ONLY
# =========================================================

@app.route("/api/complaints")
def get_complaints():

    if "department_code" not in session:

        return jsonify({
            "error": "Authentication required."
        }), 401

    code = session["department_code"]

    if code != "OTHER":

        return jsonify({
            "error":
            "Only the administrator can view all complaints."
        }), 403

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


# =========================================================
# UPDATE COMPLAINT STATUS
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>/status",
    methods=["POST"]
)
def update_status(complaint_id):

    if "department_code" not in session:

        return jsonify({
            "error": "Authentication required."
        }), 401

    data = request.get_json(silent=True) or {}

    status = str(
        data.get("status", "")
    ).strip()

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

    code = session["department_code"]

    conn = sqlite3.connect(DB_NAME)

    if code == "OTHER":

        cursor = conn.execute("""
            UPDATE complaints
            SET status = ?
            WHERE complaint_id = ?
        """, (
            status,
            complaint_id
        ))

    else:

        cursor = conn.execute("""
            UPDATE complaints
            SET status = ?
            WHERE complaint_id = ?
            AND department_code = ?
        """, (
            status,
            complaint_id,
            code
        ))

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    if updated == 0:

        return jsonify({
            "error":
            "Complaint not found or not assigned to your department."
        }), 404

    return jsonify({
        "success": True,
        "complaint_id": complaint_id,
        "status": status
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "Village Complaint Analyzer",
        "database": "connected",
        "openai_configured": bool(
            os.environ.get("OPENAI_API_KEY")
        )
    })


# =========================================================
# SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
)
