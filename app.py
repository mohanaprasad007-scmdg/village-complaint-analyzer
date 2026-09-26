from flask import Flask, request, jsonify, send_from_directory, session, redirect
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime
import uuid
import json

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "vca-change-this-secret-key"
)

DB_NAME = "complaints.db"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = None

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# =========================================================
# DEPARTMENTS
# =========================================================

DEPARTMENTS = {
    "ROAD": {
        "name": "Panchayat / Rural Development"
    },
    "WATER": {
        "name": "Water Supply Department"
    },
    "ELECTRICITY": {
        "name": "Electricity Department"
    },
    "STREET_LIGHT": {
        "name": "Panchayat / Local Body"
    },
    "SANITATION": {
        "name": "Sanitation Department"
    },
    "DRAINAGE": {
        "name": "Panchayat / Local Body"
    },
    "HEALTH": {
        "name": "Public Health Department"
    },
    "EDUCATION": {
        "name": "Education Department"
    },
    "AGRICULTURE": {
        "name": "Agriculture Department"
    },
    "SAFETY": {
        "name": "Police / Public Safety"
    },
    "OTHER": {
        "name": "Panchayat / Local Administration"
    }
}


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            department_code TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    conn.commit()

    conn.close()


def upgrade_old_database():

    conn = get_db()

    columns = [
        row["name"]
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
# ADMIN ENVIRONMENT LOGIN
# =========================================================

def admin_credentials():

    username = os.environ.get(
        "ADMIN_USERNAME",
        "vcaadmin"
    )

    password = os.environ.get(
        "ADMIN_PASSWORD"
    )

    return username, password


def is_admin():

    return (
        session.get("role") == "ADMIN"
    )


def current_department():

    return session.get(
        "department_code"
    )


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

        "summary": complaint,

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

    return json.loads(
        text.strip()
    )


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

    if "role" in session:

        return redirect("/admin")

    return send_from_directory(
        ".",
        "login.html"
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if "role" not in session:

        return redirect("/login")

    return send_from_directory(
        ".",
        "admin.html"
    )


# =========================================================
# LOGIN API
# =========================================================

@app.route(
    "/api/login",
    methods=["POST"]
)
def api_login():

    data = request.get_json(
        silent=True
    ) or {}


    username = str(
        data.get(
            "username",
            ""
        )
    ).strip().lower()


    password = str(
        data.get(
            "password",
            ""
        )
    )


    if not username or not password:

        return jsonify({
            "error":
            "Username and password are required."
        }), 400


    # -----------------------------------------------------
    # ADMIN LOGIN
    # -----------------------------------------------------

    admin_username, admin_password = (
        admin_credentials()
    )


    if (
        admin_password
        and username == admin_username.lower()
        and password == admin_password
    ):

        session.clear()

        session["user_id"] = "admin"

        session["username"] = admin_username

        session["name"] = "System Administrator"

        session["role"] = "ADMIN"

        session["department_code"] = "OTHER"

        session["department_name"] = (
            "All Departments"
        )

        return jsonify({

            "success": True,

            "role": "ADMIN",

            "department":
            "All Departments",

            "redirect": "/admin"
        })


    # -----------------------------------------------------
    # OFFICER LOGIN
    # -----------------------------------------------------

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE username = ?
        AND active = 1
        LIMIT 1
    """, (
        username,
    )).fetchone()

    conn.close()


    if not user:

        return jsonify({
            "error":
            "Invalid username or password."
        }), 401


    if not check_password_hash(
        user["password_hash"],
        password
    ):

        return jsonify({
            "error":
            "Invalid username or password."
        }), 401


    if user["department_code"] not in DEPARTMENTS:

        return jsonify({
            "error":
            "Officer department is invalid."
        }), 403


    session.clear()

    session["user_id"] = user["id"]

    session["username"] = user["username"]

    session["name"] = user["name"]

    session["role"] = user["role"]

    session["department_code"] = (
        user["department_code"]
    )

    session["department_name"] = (
        DEPARTMENTS[
            user["department_code"]
        ]["name"]
    )


    return jsonify({

        "success": True,

        "role":
        user["role"],

        "department":
        session["department_name"],

        "redirect": "/admin"
    })


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

    if "role" not in session:

        return jsonify({
            "authenticated": False
        }), 401


    return jsonify({

        "authenticated": True,

        "user_id":
        session.get("user_id"),

        "username":
        session.get("username"),

        "name":
        session.get("name"),

        "role":
        session.get("role"),

        "department_code":
        session.get("department_code"),

        "department":
        session.get("department_name")
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
        data.get(
            "complaint",
            ""
        )
    ).strip()


    if not complaint:

        return jsonify({
            "error":
            "Please enter a complaint."
        }), 400


    complaint = complaint[:10000]


    # -----------------------------------------------------
    # TRY AI
    # -----------------------------------------------------

    analysis = None

    if client:

        try:

            analysis = ai_analyze(
                complaint
            )

        except Exception as e:

            print(
                "AI unavailable. "
                "Using local analyzer:",
                repr(e)
            )


    # -----------------------------------------------------
    # LOCAL FALLBACK
    # -----------------------------------------------------

    if not analysis:

        analysis = local_analyze(
            complaint
        )


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


    conn = get_db()


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
        "AI" if client and analysis
        else "LOCAL"
    })


# =========================================================
# TRACK COMPLAINT
# =========================================================
# ADMIN - CREATE OFFICER
# =========================================================

@app.route(
    "/api/admin/officers",
    methods=["POST"]
)
def create_officer():

    if not is_admin():

        return jsonify({
            "error":
            "Administrator access required."
        }), 403


    data = request.get_json(
        silent=True
    ) or {}


    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()


    username = str(
        data.get(
            "username",
            ""
        )
    ).strip().lower()


    password = str(
        data.get(
            "password",
            ""
        )
    )


    department_code = str(
        data.get(
            "department_code",
            ""
        )
    ).strip().upper()


    if not name:

        return jsonify({
            "error":
            "Officer name is required."
        }), 400


    if not username:

        return jsonify({
            "error":
            "Username is required."
        }), 400


    if len(password) < 8:

        return jsonify({
            "error":
            "Password must contain at least 8 characters."
        }), 400


    if department_code not in DEPARTMENTS:

        return jsonify({
            "error":
            "Invalid department."
        }), 400


    conn = get_db()


    existing = conn.execute("""
        SELECT id
        FROM users
        WHERE username = ?
    """, (
        username,
    )).fetchone()


    if existing:

        conn.close()

        return jsonify({
            "error":
            "Username already exists."
        }), 409


    password_hash = generate_password_hash(
        password
    )


    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    conn.execute("""
        INSERT INTO users
        (
            name,
            username,
            password_hash,
            department_code,
            role,
            active,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (

        name,

        username,

        password_hash,

        department_code,

        "OFFICER",

        1,

        created_at
    ))


    conn.commit()

    conn.close()


    return jsonify({

        "success": True,

        "message":
        "Officer account created.",

        "name":
        name,

        "username":
        username,

        "department_code":
        department_code,

        "department":
        DEPARTMENTS[
            department_code
        ]["name"]
    })


# =========================================================
# ADMIN - LIST OFFICERS
# =========================================================

@app.route(
    "/api/admin/officers"
)
def list_officers():

    if not is_admin():

        return jsonify({
            "error":
            "Administrator access required."
        }), 403


    conn = get_db()


    users = conn.execute("""
        SELECT
            id,
            name,
            username,
            department_code,
            role,
            active,
            created_at
        FROM users
        ORDER BY id DESC
    """).fetchall()


    conn.close()


    result = []


    for user in users:

        item = dict(user)

        item["department"] = DEPARTMENTS.get(
            item["department_code"],
            {}
        ).get(
            "name",
            item["department_code"]
        )

        result.append(item)


    return jsonify(result)


# =========================================================
# ADMIN - ENABLE / DISABLE OFFICER
# =========================================================

@app.route(
    "/api/admin/officers/<int:user_id>/active",
    methods=["POST"]
)
def change_officer_active(
    user_id
):

    if not is_admin():

        return jsonify({
            "error":
            "Administrator access required."
        }), 403


    data = request.get_json(
        silent=True
    ) or {}


    active = data.get(
        "active"
    )


    if active not in [
        True,
        False
    ]:

        return jsonify({
            "error":
            "Active must be true or false."
        }), 400


    conn = get_db()


    cursor = conn.execute("""
        UPDATE users
        SET active = ?
        WHERE id = ?
    """, (
        1 if active else 0,
        user_id
    ))


    conn.commit()

    updated = cursor.rowcount

    conn.close()


    if updated == 0:

        return jsonify({
            "error":
            "Officer not found."
        }), 404


    return jsonify({

        "success": True,

        "user_id":
        user_id,

        "active":
        bool(active)
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    conn = get_db()

    officer_count = conn.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE active = 1
    """).fetchone()[0]

    conn.close()


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
        True,

        "active_officers":
        officer_count
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
