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

DB_NAME = "complaints.db"

# OpenAI is optional.
# The application will continue working if credits are unavailable.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = None

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# =========================================================
# DEPARTMENTS
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
# LOCAL COMPLAINT ANALYZER
# =========================================================

def local_analyze(complaint):

    text = complaint.lower()

    rules = [

        (
            "WATER",
            [
                "water",
                "drinking water",
                "tap water",
                "water supply",
                "no water"
            ]
        ),

        (
            "ROAD",
            [
                "road",
                "pothole",
                "potholes",
                "street damage",
                "road damage"
            ]
        ),

        (
            "ELECTRICITY",
            [
                "electricity",
                "electric",
                "power cut",
                "power",
                "current"
            ]
        ),

        (
            "STREET_LIGHT",
            [
                "street light",
                "streetlight",
                "street lights",
                "lamp",
                "lights not working"
            ]
        ),

        (
            "SANITATION",
            [
                "garbage",
                "waste",
                "rubbish",
                "trash",
                "sanitation"
            ]
        ),

        (
            "DRAINAGE",
            [
                "drain",
                "drainage",
                "sewage",
                "sewer"
            ]
        ),

        (
            "HEALTH",
            [
                "hospital",
                "health",
                "doctor",
                "medical",
                "clinic",
                "ambulance"
            ]
        ),

        (
            "EDUCATION",
            [
                "school",
                "teacher",
                "education",
                "classroom",
                "college"
            ]
        ),

        (
            "AGRICULTURE",
            [
                "farmer",
                "farmers",
                "farming",
                "crop",
                "agriculture",
                "irrigation"
            ]
        ),

        (
            "SAFETY",
            [
                "crime",
                "robbery",
                "violence",
                "danger",
                "unsafe",
                "police"
            ]
        )
    ]

    department_code = "OTHER"

    for code, keywords in rules:

        if any(
            keyword in text
            for keyword in keywords
        ):
            department_code = code
            break


    category_map = {

        "ROAD": "Roads",
        "WATER": "Water",
        "ELECTRICITY": "Electricity",
        "STREET_LIGHT": "Street Lights",
        "SANITATION": "Sanitation",
        "DRAINAGE": "Drainage",
        "HEALTH": "Health",
        "EDUCATION": "Education",
        "AGRICULTURE": "Agriculture",
        "SAFETY": "Public Safety",
        "OTHER": "Other"
    }

    category = category_map[department_code]


    emergency_words = [

        "emergency",
        "life threatening",
        "life-threatening",
        "accident",
        "fire",
        "death",
        "dying",
        "serious injury"
    ]

    high_words = [

        "5 days",
        "six days",
        "7 days",
        "week",
        "weeks",
        "months",
        "children",
        "elderly",
        "hospital",
        "unsafe",
        "severe",
        "urgent"
    ]


    if any(
        word in text
        for word in emergency_words
    ):

        priority = "Emergency"

    elif any(
        word in text
        for word in high_words
    ):

        priority = "High"

    elif any(
        word in text
        for word in [
            "not working",
            "broken",
            "blocked",
            "problem",
            "issue",
            "no water",
            "no electricity"
        ]
    ):

        priority = "Medium"

    else:

        priority = "Low"


    action_map = {

        "ROAD":
        "Inspect the affected road and arrange necessary repair work.",

        "WATER":
        "Inspect the water supply system and restore drinking water service.",

        "ELECTRICITY":
        "Inspect the electrical supply and repair the reported fault.",

        "STREET_LIGHT":
        "Inspect the street lights and repair or replace faulty lights.",

        "SANITATION":
        "Arrange sanitation services and remove accumulated waste.",

        "DRAINAGE":
        "Inspect and clear the drainage or sewage blockage.",

        "HEALTH":
        "Refer the issue to the appropriate public health authority for inspection.",

        "EDUCATION":
        "Refer the issue to the appropriate education authority for inspection.",

        "AGRICULTURE":
        "Refer the issue to the agriculture department for field-level assistance.",

        "SAFETY":
        "Refer the issue to the appropriate public safety authority for immediate attention.",

        "OTHER":
        "Forward the complaint to the local administration for review."
    }


    impact_map = {

        "ROAD":
        "The reported road condition may affect safe travel and transportation.",

        "WATER":
        "Lack of water may affect households, hygiene and daily activities.",

        "ELECTRICITY":
        "The reported power issue may affect homes, businesses and essential services.",

        "STREET_LIGHT":
        "Poor lighting may affect visibility and public safety at night.",

        "SANITATION":
        "Accumulated waste may affect cleanliness and public health.",

        "DRAINAGE":
        "Blocked drainage may cause waterlogging, hygiene problems or property damage.",

        "HEALTH":
        "The issue may affect access to essential health services.",

        "EDUCATION":
        "The issue may affect students, teachers or access to education.",

        "AGRICULTURE":
        "The issue may affect farming activities and agricultural productivity.",

        "SAFETY":
        "The reported issue may affect public safety.",

        "OTHER":
        "The reported issue may affect residents and local services."
    }


    return {

        "category": category,

        "priority": priority,

        "department_code": department_code,

        "department":
        DEPARTMENTS[department_code]["name"],

        "summary":
        complaint,

        "action":
        action_map[department_code],

        "impact":
        impact_map[department_code]
    }


# =========================================================
# AI ANALYZER
# =========================================================

def ai_analyze(complaint):

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

DEPARTMENT_CODE must be exactly one of:

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
Street lights -> STREET_LIGHT
Garbage / waste -> SANITATION
Drainage / sewage -> DRAINAGE
Health problems -> HEALTH
Education problems -> EDUCATION
Agriculture problems -> AGRICULTURE
Public safety problems -> SAFETY
Anything else -> OTHER

Be concise and practical.

Do not invent phone numbers,
official names or guarantees.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    text = response.output_text.strip()

    text = text.replace(
        "```json",
        ""
    )

    text = text.replace(
        "```",
        ""
    )

    return json.loads(text.strip())


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
# LOGIN
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
# ADMIN
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

@app.route(
    "/api/logout",
    methods=["POST"]
)
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
# ANALYZE + FILE COMPLAINT
# =========================================================

@app.route(
    "/api/analyze",
    methods=["POST"]
)
def analyze():

    data = request.get_json(
        silent=True
    ) or {}

    complaint = str(
        data.get("complaint", "")
    ).strip()

    if not complaint:

        return jsonify({
            "error": "Please enter a complaint."
        }), 400

    complaint = complaint[:10000]


    # -----------------------------------------------------
    # TRY AI FIRST
    # -----------------------------------------------------

    analysis = None

    if client:

        try:

            analysis = ai_analyze(
                complaint
            )

        except Exception as e:

            print(
                "AI unavailable. Using local analyzer:",
                repr(e)
            )


    # -----------------------------------------------------
    # LOCAL FALLBACK
    # -----------------------------------------------------

    if not analysis:

        analysis = local_analyze(
            complaint
        )


    # -----------------------------------------------------
    # NORMALIZE RESULT
    # -----------------------------------------------------

    department_code = str(
        analysis.get(
            "department_code",
            "OTHER"
        )
    ).upper().strip()

    if department_code not in DEPARTMENTS:

        department_code = "OTHER"


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

    department = DEPARTMENTS[
        department_code
    ]["name"]


    summary = str(
        analysis.get(
            "summary",
            complaint
        )
    ).strip()


    action = str(
        analysis.get(
            "action",
            "Forward the complaint to the appropriate department."
        )
    ).strip()


    impact = str(
        analysis.get(
            "impact",
            "The reported issue may affect local residents."
        )
    ).strip()


    # -----------------------------------------------------
    # CREATE COMPLAINT ID
    # -----------------------------------------------------

    complaint_id = (

        "VCA-"

        + datetime.now().strftime(
            "%Y%m%d"
        )

        + "-"

        + uuid.uuid4().hex[
            :6
        ].upper()
    )


    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    # -----------------------------------------------------
    # SAVE TO DATABASE
    # -----------------------------------------------------

    conn = sqlite3.connect(
        DB_NAME
    )

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


    # -----------------------------------------------------
    # RETURN RESULT
    # -----------------------------------------------------

    return jsonify({

        "success": True,

        "complaint_id":
        complaint_id,

        "category":
        category,

        "priority":
        priority,

        "department_code":
        department_code,

        "department":
        department,

        "summary":
        summary,

        "action":
        action,

        "impact":
        impact,

        "status":
        "Assigned",

        "analysis_mode":
        "AI" if client and analysis else "LOCAL"
    })


# =========================================================
# TRACK COMPLAINT
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>"
)
def get_complaint(
    complaint_id
):

    conn = sqlite3.connect(
        DB_NAME
    )

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
            "error":
            "Complaint not found."
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
            "error":
            "Authentication required."
        }), 401


    code = session[
        "department_code"
    ]


    conn = sqlite3.connect(
        DB_NAME
    )

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
# ALL COMPLAINTS
# =========================================================

@app.route("/api/complaints")
def get_complaints():

    if "department_code" not in session:

                return jsonify({
            "error":
            "Authentication required."
        }), 401


    if session[
        "department_code"
    ] != "OTHER":

        return jsonify({
            "error":
            "Only the administrator can view all complaints."
        }), 403


    conn = sqlite3.connect(
        DB_NAME
    )

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
def update_status(
    complaint_id
):

    if "department_code" not in session:

        return jsonify({
            "error":
            "Authentication required."
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    status = str(
        data.get(
            "status",
            ""
        )
    ).strip()


    allowed_statuses = [

        "Assigned",

        "In Progress",

        "Resolved",

        "Rejected"
    ]


    if status not in allowed_statuses:

        return jsonify({
            "error":
            "Invalid status."
        }), 400


    code = session[
        "department_code"
    ]


    conn = sqlite3.connect(
        DB_NAME
    )


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

        "complaint_id":
        complaint_id,

        "status":
        status
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({

        "status":
        "ok",

        "service":
        "Village Complaint Analyzer",

        "database":
        "connected",

        "openai_configured":
        bool(OPENAI_API_KEY),

        "local_fallback":
        True
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
     
