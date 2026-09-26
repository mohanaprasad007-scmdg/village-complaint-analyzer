from flask import Flask, request, jsonify, send_from_directory, session, redirect
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, json, uuid
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "vca-change-this-secret-key"
)

DB_NAME = "complaints.db"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

DEPARTMENTS = {
    "ROAD": {"name": "Panchayat / Rural Development"},
    "WATER": {"name": "Water Supply Department"},
    "ELECTRICITY": {"name": "Electricity Department"},
    "STREET_LIGHT": {"name": "Panchayat / Local Body"},
    "SANITATION": {"name": "Sanitation Department"},
    "DRAINAGE": {"name": "Panchayat / Local Body"},
    "HEALTH": {"name": "Public Health Department"},
    "EDUCATION": {"name": "Education Department"},
    "AGRICULTURE": {"name": "Agriculture Department"},
    "SAFETY": {"name": "Police / Public Safety"},
    "OTHER": {"name": "Panchayat / Local Administration"}
}

def using_postgres():
    return bool(os.environ.get("DATABASE_URL")) and psycopg2 is not None

class DB:
    def __init__(self):
        self.pg = using_postgres()
        if self.pg:
            self.conn = psycopg2.connect(
                os.environ["DATABASE_URL"],
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        else:
            self.conn = sqlite3.connect(DB_NAME)
            self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        if self.pg:
            sql = sql.replace("?", "%s")
        return self.conn.cursor() if False else self._execute(sql, params)

    def _execute(self, sql, params):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db():
    return DB()

def init_db():
    db = get_db()

    if db.pg:
        db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY,
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                department_code TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
    else:
        db.execute("""
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
        db.execute("""
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

    db.commit()
    db.close()

def upgrade_db():
    db = get_db()

    if db.pg:
        for col in [
            ("department_code", "TEXT"),
            ("department", "TEXT"),
            ("summary", "TEXT"),
            ("action", "TEXT"),
            ("impact", "TEXT"),
            ("status", "TEXT")
        ]:
            try:
                db.execute(
                    f"ALTER TABLE complaints ADD COLUMN IF NOT EXISTS {col[0]} {col[1]}"
                )
            except Exception:
                db.conn.rollback()
    else:
        cols = [
            r["name"] for r in db.execute(
                "PRAGMA table_info(complaints)"
            ).fetchall()
        ]
        for name, typ in [
            ("department_code", "TEXT"),
            ("department", "TEXT"),
            ("summary", "TEXT"),
            ("action", "TEXT"),
            ("impact", "TEXT"),
            ("status", "TEXT")
        ]:
            if name not in cols:
                db.execute(
                    f"ALTER TABLE complaints ADD COLUMN {name} {typ}"
                )

    db.commit()
    db.close()

init_db()
upgrade_db()

def admin_credentials():
    return (
        os.environ.get("ADMIN_USERNAME", "vcaadmin"),
        os.environ.get("ADMIN_PASSWORD")
    )

def is_admin():
    return session.get("role") == "ADMIN"

def current_department():
    return session.get("department_code")

def local_analyze(complaint):
    text = complaint.lower()

    rules = [
        ("WATER", ["water", "drinking water", "tap water",
                   "water supply", "no water"]),
        ("ROAD", ["road", "pothole", "potholes",
                   "street damage", "road damage"]),
        ("ELECTRICITY", ["electricity", "electric",
                         "power cut", "power", "current"]),
        ("STREET_LIGHT", ["street light", "streetlight",
                          "street lights", "lamp",
                          "lights not working"]),
        ("SANITATION", ["garbage", "waste", "rubbish",
                        "trash", "sanitation"]),
        ("DRAINAGE", ["drain", "drainage", "sewage", "sewer"]),
        ("HEALTH", ["hospital", "health", "doctor",
                    "medical", "clinic", "ambulance"]),
        ("EDUCATION", ["school", "teacher", "education",
                       "classroom", "college"]),
        ("AGRICULTURE", ["farmer", "farmers", "farming",
                         "crop", "agriculture", "irrigation"]),
        ("SAFETY", ["crime", "robbery", "violence",
                    "danger", "unsafe", "police"])
    ]

    code = "OTHER"
    for c, words in rules:
        if any(w in text for w in words):
            code = c
            break

    categories = {
        "ROAD": "Roads", "WATER": "Water",
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

    emergency = [
        "emergency", "life threatening", "life-threatening",
        "accident", "fire", "death", "dying", "serious injury"
    ]

    high = [
        "5 days", "six days", "7 days", "week", "weeks",
        "months", "children", "elderly", "hospital",
        "unsafe", "severe", "urgent"
    ]

    medium = [
        "not working", "broken", "blocked", "problem",
        "issue", "no water", "no electricity"
    ]

    if any(x in text for x in emergency):
        priority = "Emergency"
    elif any(x in text for x in high):
        priority = "High"
    elif any(x in text for x in medium):
        priority = "Medium"
    else:
        priority = "Low"

    actions = {
        "ROAD": "Inspect the affected road and arrange necessary repair work.",
        "WATER": "Inspect the water supply system and restore drinking water service.",
        "ELECTRICITY": "Inspect the electrical supply and repair the reported fault.",
        "STREET_LIGHT": "Inspect the street lights and repair or replace faulty lights.",
        "SANITATION": "Arrange sanitation services and remove accumulated waste.",
        "DRAINAGE": "Inspect and clear the drainage or sewage blockage.",
        "HEALTH": "Refer the issue to the appropriate public health authority.",
        "EDUCATION": "Refer the issue to the appropriate education authority.",
        "AGRICULTURE": "Refer the issue to the agriculture department.",
        "SAFETY": "Refer the issue to the appropriate public safety authority.",
        "OTHER": "Forward the complaint to the local administration for review."
    }

    impacts = {
        "ROAD": "The reported road condition may affect safe travel and transportation.",
        "WATER": "Lack of water may affect households, hygiene and daily activities.",
        "ELECTRICITY": "The reported power issue may affect homes and essential services.",
        "STREET_LIGHT": "Poor lighting may affect visibility and public safety at night.",
        "SANITATION": "Accumulated waste may affect cleanliness and public health.",
        "DRAINAGE": "Blocked drainage may cause waterlogging and hygiene problems.",
        "HEALTH": "The issue may affect access to essential health services.",
        "EDUCATION": "The issue may affect students, teachers or education access.",
        "AGRICULTURE": "The issue may affect farming activities and productivity.",
        "SAFETY": "The reported issue may affect public safety.",
        "OTHER": "The reported issue may affect residents and local services."
    }

    return {
        "category": categories[code],
        "priority": priority,
        "department_code": code,
        "department": DEPARTMENTS[code]["name"],
        "summary": complaint,
        "action": actions[code],
        "impact": impacts[code]
    }

def ai_analyze(complaint):
    prompt = f"""
You are an AI Village Complaint Analyzer.

Analyze this citizen complaint:

{complaint}

Return ONLY valid JSON with:
category, priority, department_code, summary, action, impact.

department_code must be exactly:
ROAD, WATER, ELECTRICITY, STREET_LIGHT, SANITATION,
DRAINAGE, HEALTH, EDUCATION, AGRICULTURE, SAFETY, OTHER.

priority must be:
Low, Medium, High, Emergency.

Route road problems to ROAD.
Water supply to WATER.
Electricity to ELECTRICITY.
Street lights to STREET_LIGHT.
Garbage/waste to SANITATION.
Drainage/sewage to DRAINAGE.
Health to HEALTH.
Education to EDUCATION.
Agriculture to AGRICULTURE.
Public safety to SAFETY.
Other problems to OTHER.

Be concise and practical.
"""
    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )
    text = response.output_text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/login")
def login():
    if "role" in session:
        return redirect("/admin")
    return send_from_directory(".", "login.html")

@app.route("/admin")
def admin():
    if "role" not in session:
        return redirect("/login")
    return send_from_directory(".", "admin.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    admin_user, admin_pass = admin_credentials()

    if admin_pass and username == admin_user.lower() and password == admin_pass:
        session.clear()
        session.update({
            "user_id": "admin",
            "username": admin_user,
            "name": "System Administrator",
            "role": "ADMIN",
            "department_code": "OTHER",
            "department_name": "All Departments"
        })
        return jsonify({
            "success": True,
            "role": "ADMIN",
            "department": "All Departments",
            "redirect": "/admin"
        })

    db = get_db()
    user = db.execute("""
        SELECT * FROM users
        WHERE username = ? AND active = 1
        LIMIT 1
    """, (username,)).fetchone()
    db.close()

    if not user or not check_password_hash(
        user["password_hash"], password
    ):
        return jsonify({"error": "Invalid username or password."}), 401

    code = user["department_code"]

    if code not in DEPARTMENTS:
        return jsonify({"error": "Invalid officer department."}), 403

    session.clear()
    session.update({
        "user_id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "department_code": code,
        "department_name": DEPARTMENTS[code]["name"]
    })

    return jsonify({
        "success": True,
        "role": user["role"],
        "department": DEPARTMENTS[code]["name"],
        "redirect": "/admin"
    })

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "redirect": "/login"})

@app.route("/api/me")
def me():
    if "role" not in session:
        return jsonify({"authenticated": False}), 401

    return jsonify({
        "authenticated": True,
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "name": session.get("name"),
        "role": session.get("role"),
        "department_code": session.get("department_code"),
        "department": session.get("department_name")
    })

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    complaint = str(data.get("complaint", "")).strip()[:10000]

    if not complaint:
        return jsonify({"error": "Please enter a complaint."}), 400

    analysis = None
    mode = "LOCAL"

    if client:
        try:
            analysis = ai_analyze(complaint)
            mode = "AI"
        except Exception as e:
            print("AI unavailable:", repr(e))

    if not analysis:
        analysis = local_analyze(complaint)

    code = str(
        analysis.get("department_code", "OTHER")
    ).upper().strip()

    if code not in DEPARTMENTS:
        code = "OTHER"

    complaint_id = (
        "VCA-" +
        datetime.now().strftime("%Y%m%d") +
        "-" + uuid.uuid4().hex[:6].upper()
    )

    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    db.execute("""
        INSERT INTO complaints
        (complaint_id, complaint, category, priority,
         department_code, department, summary, action,
         impact, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        complaint_id,
        complaint,
        str(analysis.get("category", "Other")),
        str(analysis.get("priority", "Medium")),
        code,
        DEPARTMENTS[code]["name"],
        str(analysis.get("summary", complaint)),
        str(analysis.get("action", "Forward to the appropriate department.")),
        str(analysis.get("impact", "The issue may affect local residents.")),
        "Assigned",
        created
    ))
    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "complaint_id": complaint_id,
        "category": analysis.get("category", "Other"),
        "priority": analysis.get("priority", "Medium"),
        "department_code": code,
        "department": DEPARTMENTS[code]["name"],
        "summary": analysis.get("summary", complaint),
        "action": analysis.get("action", ""),
        "impact": analysis.get("impact", ""),
        "status": "Assigned",
        "analysis_mode": mode
    })

@app.route("/api/complaint/<complaint_id>")
def track(complaint_id):
    db = get_db()
    row = db.execute("""
        SELECT * FROM complaints
        WHERE complaint_id = ?
    """, (complaint_id,)).fetchone()
    db.close()

    if not row:
        return jsonify({"error": "Complaint not found."}), 404

    return jsonify(dict(row))

@app.route("/api/department")
def department():
    if "role" not in session:
        return jsonify({"error": "Authentication required."}), 401

    db = get_db()

    if is_admin():
        rows = db.execute("""
            SELECT * FROM complaints
            ORDER BY id DESC
        """).fetchall()
    else:
        rows = db.execute("""
            SELECT * FROM complaints
            WHERE department_code = ?
            ORDER BY id DESC
        """, (current_department(),)).fetchall()

    db.close()
    return jsonify([dict(x) for x in rows])

@app.route("/api/complaints")
def complaints():
    if not is_admin():
        return jsonify({"error": "Administrator access required."}), 403

    db = get_db()
    rows = db.execute("""
        SELECT * FROM complaints
        ORDER BY id DESC
    """).fetchall()
    db.close()

    return jsonify([dict(x) for x in rows])

@app.route("/api/complaint/<complaint_id>/status", methods=["POST"])
def update_status(complaint_id):
    if "role" not in session:
        return jsonify({"error": "Authentication required."}), 401

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()

    allowed = [
        "Assigned",
        "In Progress",
        "Resolved",
        "Rejected"
    ]

    if status not in allowed:
        return jsonify({"error": "Invalid status."}), 400

    db = get_db()

    row = db.execute("""
        SELECT department_code FROM complaints
        WHERE complaint_id = ?
    """, (complaint_id,)).fetchone()

    if not row:
        db.close()
        return jsonify({"error": "Complaint not found."}), 404

    if not is_admin() and row["department_code"] != current_department():
        db.close()
        return jsonify({
            "error": "You cannot update complaints outside your department."
        }), 403

    db.execute("""
        UPDATE complaints
        SET status = ?
        WHERE complaint_id = ?
    """, (status, complaint_id))

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "complaint_id": complaint_id,
        "status": status
    })

@app.route("/api/admin/officers", methods=["POST"])
def create_officer():
    if not is_admin():
        return jsonify({"error": "Administrator access required."}), 403

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))
    code = str(data.get("department_code", "")).strip().upper()

    if not name or not username:
        return jsonify({"error": "Name and username are required."}), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must contain at least 8 characters."
        }), 400

    if code not in DEPARTMENTS:
        return jsonify({"error": "Invalid department."}), 400

    db = get_db()

    if db.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ).fetchone():
        db.close()
        return jsonify({"error": "Username already exists."}), 409

    db.execute("""
        INSERT INTO users
        (name, username, password_hash, department_code,
         role, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        username,
        generate_password_hash(password),
        code,
        "OFFICER",
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "message": "Officer account created.",
        "name": name,
        "username": username,
        "department_code": code,
        "department": DEPARTMENTS[code]["name"]
    })

@app.route("/api/admin/officers")
def list_officers():
    if not is_admin():
        return jsonify({"error": "Administrator access required."}), 403

    db = get_db()

    rows = db.execute("""
        SELECT id, name, username, department_code,
               role, active, created_at
        FROM users
        ORDER BY id DESC
    """).fetchall()

    db.close()

    result = []

    for row in rows:
        item = dict(row)
        item["department"] = DEPARTMENTS.get(
            item["department_code"], {}
        ).get(
            "name",
            item["department_code"]
        )
        result.append(item)

    return jsonify(result)


@app.route(
    "/api/admin/officers/<int:user_id>/active",
    methods=["POST"]
)
def change_officer(user_id):
    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    data = request.get_json(silent=True) or {}
    active = data.get("active")

    if active not in [True, False]:
        return jsonify({
            "error": "Active must be true or false."
        }), 400

    db = get_db()

    cur = db.execute("""
        UPDATE users
        SET active = ?
        WHERE id = ?
    """, (
        1 if active else 0,
        user_id
    ))

    db.commit()

    count = cur.rowcount

    db.close()

    if count == 0:
        return jsonify({
            "error": "Officer not found."
        }), 404

    return jsonify({
        "success": True,
        "user_id": user_id,
        "active": bool(active)
    })


@app.route("/api/health")
def health():
    db = get_db()

    officers = db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE active = 1"
    ).fetchone()

    complaints = db.execute(
        "SELECT COUNT(*) AS c FROM complaints"
    ).fetchone()

    db.close()

    return jsonify({
        "status": "ok",
        "service": "Village Complaint Analyzer",
        "database": "PostgreSQL" if using_postgres() else "SQLite",
        "openai_configured": bool(OPENAI_API_KEY),
        "local_fallback": True,
        "active_officers": officers["c"],
        "total_complaints": complaints["c"]
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
        
