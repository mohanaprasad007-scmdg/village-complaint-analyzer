from flask import Flask, request, jsonify, send_from_directory, session, redirect
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import json
import uuid
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "vca-change-this-secret-key"
)

DB_NAME = "complaints.db"

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY"
)

client = (
    OpenAI(api_key=OPENAI_API_KEY)
    if OPENAI_API_KEY
    else None
)


# =========================================================
# DEPARTMENTS
# =========================================================

DEPARTMENTS = {

    "ROAD":
        {"name": "Panchayat / Rural Development"},

    "WATER":
        {"name": "Water Supply Department"},

    "ELECTRICITY":
        {"name": "Electricity Department"},

    "STREET_LIGHT":
        {"name": "Panchayat / Local Body"},

    "SANITATION":
        {"name": "Sanitation Department"},

    "DRAINAGE":
        {"name": "Panchayat / Local Body"},

    "HEALTH":
        {"name": "Public Health Department"},

    "EDUCATION":
        {"name": "Education Department"},

    "AGRICULTURE":
        {"name": "Agriculture Department"},

    "SAFETY":
        {"name": "Police / Public Safety"},

    "OTHER":
        {"name": "Panchayat / Local Administration"}
}


# =========================================================
# GOVERNMENT HIERARCHY
# =========================================================

HIERARCHY = [

    (
        "VILLAGE_OFFICER",
        "Village / Panchayat Officer"
    ),

    (
        "BLOCK_OFFICER",
        "Block Officer"
    ),

    (
        "TALUK_OFFICER",
        "Taluk Officer"
    ),

    (
        "DISTRICT_OFFICER",
        "District Officer"
    ),

    (
        "DEPARTMENT_OFFICER",
        "Department Officer"
    ),

    (
        "DEPARTMENT_HEAD",
        "Department Head"
    ),

    (
        "STATE_ADMINISTRATOR",
        "State Administrator"
    )
]

ROLE_NAMES = dict(HIERARCHY)

ROLE_ORDER = {
    role: i
    for i, (role, name) in enumerate(HIERARCHY)
}

ROLE_ALIASES = {
    "OFFICER":
        "DEPARTMENT_OFFICER"
}


# =========================================================
# DATABASE
# =========================================================

def using_postgres():

    return (
        bool(os.environ.get("DATABASE_URL"))
        and psycopg2 is not None
    )


class DB:

    def __init__(self):

        self.pg = using_postgres()

        if self.pg:

            self.conn = psycopg2.connect(
                os.environ["DATABASE_URL"],
                cursor_factory=psycopg2.extras.RealDictCursor
            )

        else:

            self.conn = sqlite3.connect(
                DB_NAME
            )

            self.conn.row_factory = sqlite3.Row


    def execute(self, sql, params=()):

        if self.pg:

            sql = sql.replace(
                "?",
                "%s"
            )

        cur = self.conn.cursor()

        cur.execute(
            sql,
            params
        )

        return cur


    def commit(self):

        self.conn.commit()


    def close(self):

        self.conn.close()


def get_db():

    return DB()


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    db = get_db()

    if db.pg:

        db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id SERIAL PRIMARY KEY,
                complaint_id TEXT UNIQUE NOT NULL,
                complaint TEXT NOT NULL,
                category TEXT,
                priority TEXT,
                department_code TEXT,
                department TEXT,
                summary TEXT,
                action TEXT,
                impact TEXT,
                status TEXT DEFAULT 'Assigned',
                created_at TEXT,
                assigned_role TEXT,
                assigned_user_id INTEGER,
                current_level INTEGER,
                updated_at TEXT,
                district TEXT,
                taluk TEXT,
                block TEXT,
                village TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                department_code TEXT,
                role TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                district TEXT,
                taluk TEXT,
                block TEXT,
                village TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS complaint_history (
                id SERIAL PRIMARY KEY,
                complaint_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT,
                officer_role TEXT,
                officer_name TEXT,
                created_at TEXT
            )
        """)

    else:

        db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT UNIQUE NOT NULL,
                complaint TEXT NOT NULL,
                category TEXT,
                priority TEXT,
                department_code TEXT,
                department TEXT,
                summary TEXT,
                action TEXT,
                impact TEXT,
                status TEXT DEFAULT 'Assigned',
                created_at TEXT,
                assigned_role TEXT,
                assigned_user_id INTEGER,
                current_level INTEGER,
                updated_at TEXT,
                district TEXT,
                taluk TEXT,
                block TEXT,
                village TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                department_code TEXT,
                role TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                district TEXT,
                taluk TEXT,
                block TEXT,
                village TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS complaint_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT,
                officer_role TEXT,
                officer_name TEXT,
                created_at TEXT
            )
        """)

    db.commit()

    db.close()


# =========================================================
# DATABASE UPGRADE
# =========================================================

def upgrade_db():

    db = get_db()

    complaint_columns = [

        ("assigned_role", "TEXT"),
        ("assigned_user_id", "INTEGER"),
        ("current_level", "INTEGER"),
        ("updated_at", "TEXT"),
        ("district", "TEXT"),
        ("taluk", "TEXT"),
        ("block", "TEXT"),
        ("village", "TEXT")
    ]

    user_columns = [

        ("district", "TEXT"),
        ("taluk", "TEXT"),
        ("block", "TEXT"),
        ("village", "TEXT")
    ]


    if db.pg:

        for name, typ in complaint_columns:

            try:

                db.execute(
                    f"""
                    ALTER TABLE complaints
                    ADD COLUMN IF NOT EXISTS
                    {name} {typ}
                    """
                )

            except Exception as e:

                print(
                    "Complaint migration:",
                    name,
                    repr(e)
                )

                db.conn.rollback()


        for name, typ in user_columns:

            try:

                db.execute(
                    f"""
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS
                    {name} {typ}
                    """
                )

            except Exception as e:

                print(
                    "User migration:",
                    name,
                    repr(e)
                )

                db.conn.rollback()


        try:

            db.execute("""
                CREATE TABLE IF NOT EXISTS complaint_history (
                    id SERIAL PRIMARY KEY,
                    complaint_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT,
                    officer_role TEXT,
                    officer_name TEXT,
                    created_at TEXT
                )
            """)

        except Exception as e:

            print(
                "History migration:",
                repr(e)
            )

            db.conn.rollback()

    else:

        complaint_existing = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(complaints)"
            ).fetchall()
        ]

        for name, typ in complaint_columns:

            if name not in complaint_existing:

                db.execute(
                    f"""
                    ALTER TABLE complaints
                    ADD COLUMN {name} {typ}
                    """
                )


        user_existing = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        for name, typ in user_columns:

            if name not in user_existing:

                db.execute(
                    f"""
                    ALTER TABLE users
                    ADD COLUMN {name} {typ}
                    """
                )


        db.execute("""
            CREATE TABLE IF NOT EXISTS complaint_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT,
                officer_role TEXT,
                officer_name TEXT,
                created_at TEXT
            )
        """)


    try:

        db.execute("""
            UPDATE complaints
            SET assigned_role =
                'VILLAGE_OFFICER'
            WHERE assigned_role IS NULL
               OR assigned_role = ''
        """)

        db.execute("""
            UPDATE complaints
            SET current_level = 1
            WHERE current_level IS NULL
        """)

        db.execute("""
            UPDATE complaints
            SET status = 'Assigned'
            WHERE status IS NULL
               OR status = ''
        """)

        db.execute("""
            UPDATE complaints
            SET updated_at = created_at
            WHERE updated_at IS NULL
               OR updated_at = ''
        """)

        db.commit()

    except Exception as e:

        print(
            "Migration error:",
            repr(e)
        )

        db.conn.rollback()


    db.close()


init_db()

upgrade_db()


# =========================================================
# HELPERS
# =========================================================

def admin_credentials():

    return (

        os.environ.get(
            "ADMIN_USERNAME",
            "vcaadmin"
        ),

        os.environ.get(
            "ADMIN_PASSWORD"
        )
    )


def is_admin():

    return session.get(
        "role"
    ) == "ADMIN"


def current_role():

    role = session.get(
        "role",
        ""
    )

    return ROLE_ALIASES.get(
        role,
        role
    )


def current_department():

    return session.get(
        "department_code"
    )


def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def find_next_role(role):

    role = ROLE_ALIASES.get(
        role,
        role
    )

    if role not in ROLE_ORDER:

        return None

    index = (
        ROLE_ORDER[role]
        + 1
    )

    if index >= len(HIERARCHY):

        return None

    return HIERARCHY[index][0]


# =========================================================
# HISTORY
# =========================================================

def add_history(
    db,
    complaint_id,
    action,
    status=None,
    officer_role=None,
    officer_name=None
):

    db.execute("""
        INSERT INTO complaint_history
        (
            complaint_id,
            action,
            status,
            officer_role,
            officer_name,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (

        complaint_id,
        action,
        status,
        officer_role,
        officer_name,
        now()
    ))


# =========================================================
# OFFICER ASSIGNMENT
# =========================================================

def assign_officer(
    db,
    department_code,
    role,
    district=None,
    taluk=None,
    block=None,
    village=None
):

    query = """
        SELECT id
        FROM users
        WHERE department_code = ?
          AND active = 1
          AND role = ?
    """

    params = [
        department_code,
        role
    ]


    if district:

        query += """
            AND district = ?
        """

        params.append(
            district
        )


    if taluk:

        query += """
            AND taluk = ?
        """

        params.append(
            taluk
        )


    if block:

        query += """
            AND block = ?
        """

        params.append(
            block
        )


    if village:

        query += """
            AND village = ?
        """

        params.append(
            village
        )


    query += """
        ORDER BY id ASC
        LIMIT 1
    """


    row = db.execute(
        query,
        tuple(params)
    ).fetchone()


    return (
        row["id"]
        if row
        else None
    )


# =========================================================
# LOCATION ACCESS
# =========================================================

def location_matches(row):

    if is_admin():

        return True


    role = current_role()


    user_district = session.get(
        "district"
    )

    user_taluk = session.get(
        "taluk"
    )

    user_block = session.get(
        "block"
    )

    user_village = session.get(
        "village"
    )


    if role == "VILLAGE_OFFICER":

        return (

            row["district"]
            == user_district

            and

            row["taluk"]
            == user_taluk

            and

            row["block"]
            == user_block

            and

            row["village"]
            == user_village
        )


    if role == "BLOCK_OFFICER":

        return (

            row["district"]
            == user_district

            and

            row["taluk"]
            == user_taluk

            and

            row["block"]
            == user_block
        )


    if role == "TALUK_OFFICER":

        return (

            row["district"]
            == user_district

            and

            row["taluk"]
            == user_taluk
        )


    if role == "DISTRICT_OFFICER":

        return (
            row["district"]
            == user_district
        )


    return True


def can_access_complaint(row):

    if is_admin():

        return True


    if (
        row["department_code"]
        != current_department()
    ):

        return False


    if not location_matches(row):

        return False


    assigned_role = ROLE_ALIASES.get(

        row["assigned_role"]
        or "VILLAGE_OFFICER",

        row["assigned_role"]
        or "VILLAGE_OFFICER"
    )


    if (
        assigned_role
        != current_role()
    ):

        return False


    assigned_user = row[
        "assigned_user_id"
    ]


    if assigned_user is not None:

        return (
            str(assigned_user)
            ==
            str(
                session.get(
                    "user_id"
                )
            )
        )


    return True


# =========================================================
# LOCAL ANALYSIS
# =========================================================

def local_analyze(complaint):

    text = complaint.lower()


    rules = {

        "WATER": [
            "water",
            "drinking water",
            "tap water",
            "water supply",
            "no water"
        ],

        "ROAD": [
            "road",
            "pothole",
            "potholes",
            "road damage"
        ],

        "ELECTRICITY": [
            "electricity",
            "electric",
            "power cut",
            "power",
            "current"
        ],

        "STREET_LIGHT": [
            "street light",
            "streetlight",
            "lamp"
        ],

        "SANITATION": [
            "garbage",
            "waste",
            "rubbish",
            "trash",
            "sanitation"
        ],

        "DRAINAGE": [
            "drain",
            "drainage",
            "sewage",
            "sewer"
        ],

        "HEALTH": [
            "hospital",
            "health",
            "doctor",
            "medical",
            "clinic",
            "ambulance"
        ],

        "EDUCATION": [
            "school",
            "teacher",
            "education",
            "classroom",
            "college"
        ],

        "AGRICULTURE": [
            "farmer",
            "farmers",
            "farming",
            "crop",
            "agriculture",
            "irrigation"
        ],

        "SAFETY": [
            "crime",
            "robbery",
            "violence",
            "danger",
            "unsafe",
            "police"
        ]
    }


    code = "OTHER"


    for department, words in rules.items():

        if any(
            word in text
            for word in words
        ):

            code = department
            break


    if any(
        x in text
        for x in [
            "emergency",
            "accident",
            "fire",
            "death",
            "dying",
            "serious injury"
        ]
    ):

        priority = "Emergency"


    elif any(
        x in text
        for x in [
            "urgent",
            "severe",
            "hospital",
            "unsafe",
            "children",
            "elderly"
        ]
    ):

        priority = "High"


    elif any(
        x in text
        for x in [
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


    categories = {

        "ROAD":
            "Roads",

        "WATER":
            "Water",

        "ELECTRICITY":
            "Electricity",

        "STREET_LIGHT":
            "Street Lights",

        "SANITATION":
            "Sanitation",

        "DRAINAGE":
            "Drainage",

        "HEALTH":
            "Health",

        "EDUCATION":
            "Education",

        "AGRICULTURE":
            "Agriculture",

        "SAFETY":
            "Public Safety",

        "OTHER":
            "Other"
    }


    actions = {

        "ROAD":
            "Inspect the affected road and arrange necessary repair work.",

        "WATER":
            "Inspect the water supply system and restore drinking water service.",

        "ELECTRICITY":
            "Inspect the electrical supply and repair the reported fault.",

        "STREET_LIGHT":
                        "Inspect and repair or replace faulty street lights.",

        "SANITATION":
            "Arrange sanitation services and remove accumulated waste.",

        "DRAINAGE":
            "Inspect and clear the drainage or sewage blockage.",

        "HEALTH":
            "Refer the issue to the appropriate public health authority.",

        "EDUCATION":
            "Refer the issue to the appropriate education authority.",

        "AGRICULTURE":
            "Refer the issue to the agriculture department.",

        "SAFETY":
            "Refer the issue to the appropriate public safety authority.",

        "OTHER":
            "Forward the complaint to the local administration."
    }

    return {
        "category":
            categories[code],

        "priority":
            priority,

        "department_code":
            code,

        "department":
            DEPARTMENTS[code]["name"],

        "summary":
            complaint,

        "action":
            actions[code],

        "impact":
            "The reported issue may affect local residents."
    }


# =========================================================
# OPENAI ANALYSIS
# =========================================================

def ai_analyze(complaint):

    prompt = f"""
Analyze this citizen complaint:

{complaint}

Return ONLY JSON with:
category,
priority,
department_code,
summary,
action,
impact.

department_code must be one of:
ROAD, WATER, ELECTRICITY, STREET_LIGHT,
SANITATION, DRAINAGE, HEALTH, EDUCATION,
AGRICULTURE, SAFETY, OTHER.

priority must be:
Low, Medium, High, Emergency.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    text = response.output_text.strip()

    text = (
        text
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    return json.loads(text)


# =========================================================
# PAGES
# =========================================================

@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/citizen")
def citizen():
    return send_from_directory(".", "citizen.html")


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


# =========================================================
# LOGIN
# =========================================================

@app.route("/api/login", methods=["POST"])
def api_login():

    data = request.get_json(silent=True) or {}

    username = str(
        data.get("username", "")
    ).strip().lower()

    password = str(
        data.get("password", "")
    )

    requested_role = str(
        data.get("requested_role", "OFFICER")
    ).strip().upper()

    if not username or not password:
        return jsonify({
            "error":
                "Username and password are required."
        }), 400

    admin_user, admin_pass = admin_credentials()

    if requested_role == "ADMIN":

        if (
            admin_pass
            and username == admin_user.lower()
            and password == admin_pass
        ):

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
                "redirect": "/admin"
            })

        return jsonify({
            "error":
                "Invalid Main Admin credentials."
        }), 401

    db = get_db()

    user = db.execute("""
        SELECT *
        FROM users
        WHERE username = ?
          AND active = 1
        LIMIT 1
    """, (
        username,
    )).fetchone()

    db.close()

    if not user:

        return jsonify({
            "error":
                "Officer account not found."
        }), 401

    if not check_password_hash(
        user["password_hash"],
        password
    ):

        return jsonify({
            "error":
                "Invalid officer password."
        }), 401

    code = user["department_code"]

    if code not in DEPARTMENTS:

        return jsonify({
            "error":
                "Invalid officer department."
        }), 403

    role = ROLE_ALIASES.get(
        user["role"],
        user["role"]
    )

    session.clear()

    session.update({
        "user_id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "role": role,
        "department_code": code,
        "department_name":
            DEPARTMENTS[code]["name"],
        "district": user["district"],
        "taluk": user["taluk"],
        "block": user["block"],
        "village": user["village"]
    })

    return jsonify({
        "success": True,
        "role": role,
        "role_name":
            ROLE_NAMES.get(role, role),
        "department":
            DEPARTMENTS[code]["name"],
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
def me():

    if "role" not in session:

        return jsonify({
            "authenticated": False
        }), 401

    role = current_role()

    return jsonify({
        "authenticated": True,
        "user_id":
            session.get("user_id"),
        "username":
            session.get("username"),
        "name":
            session.get("name"),
        "role":
            role,
        "role_name": (
            "System Administrator"
            if role == "ADMIN"
            else ROLE_NAMES.get(
                role,
                role
            )
        ),
        "department_code":
            session.get(
                "department_code"
            ),
        "department":
            session.get(
                "department_name"
            ),
        "district":
            session.get("district"),
        "taluk":
            session.get("taluk"),
        "block":
            session.get("block"),
        "village":
            session.get("village")
    })


# =========================================================
# ROLES
# =========================================================

@app.route("/api/roles")
def roles():

    return jsonify([

        {
            "role": role,
            "name": name,
            "level": i + 1
        }

        for i, (role, name)
        in enumerate(HIERARCHY)
    ])


# =========================================================
# COMPLAINT SUBMISSION
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
    ).strip()[:10000]

    if not complaint:

        return jsonify({
            "error":
                "Please enter a complaint."
        }), 400

    analysis = None
    mode = "LOCAL"

    if client:

        try:

            analysis = ai_analyze(
                complaint
            )

            mode = "AI"

        except Exception as e:

            print(
                "AI unavailable:",
                repr(e)
            )

    if not analysis:

        analysis = local_analyze(
            complaint
        )

    code = str(
        analysis.get(
            "department_code",
            "OTHER"
        )
    ).upper().strip()

    if code not in DEPARTMENTS:
        code = "OTHER"

    district = str(
        data.get(
            "district",
            ""
        )
    ).strip()

    taluk = str(
        data.get(
            "taluk",
            ""
        )
    ).strip()

    block = str(
        data.get(
            "block",
            ""
        )
    ).strip()

    village = str(
        data.get(
            "village",
            ""
        )
    ).strip()

    complaint_id = (
        "VCA-"
        +
        datetime.now().strftime(
            "%Y%m%d"
        )
        +
        "-"
        +
        uuid.uuid4()
        .hex[:6]
        .upper()
    )

    db = get_db()

    assigned_role = "VILLAGE_OFFICER"

    assigned_user_id = assign_officer(
        db,
        code,
        assigned_role,
        district,
        taluk,
        block,
        village
    )

    created_time = now()

    db.execute("""
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
            created_at,
            assigned_role,
            assigned_user_id,
            current_level,
            updated_at,
            district,
            taluk,
            block,
            village
        )
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        complaint_id,
        complaint,
        str(
            analysis.get(
                "category",
                "Other"
            )
        ),
        str(
            analysis.get(
                "priority",
                "Medium"
            )
        ),
        code,
        DEPARTMENTS[
            code
        ]["name"],
        str(
            analysis.get(
                "summary",
                complaint
            )
        ),
        str(
            analysis.get(
                "action",
                ""
            )
        ),
        str(
            analysis.get(
                "impact",
                ""
            )
        ),
        "Assigned",
        created_time,
        assigned_role,
        assigned_user_id,
        1,
        created_time,
        district,
        taluk,
        block,
        village
    ))

    add_history(
        db,
        complaint_id,
        "Complaint Submitted",
        "Assigned",
        assigned_role,
        ROLE_NAMES[
            assigned_role
        ]
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "complaint_id":
            complaint_id,
        "category":
            analysis.get(
                "category",
                "Other"
            ),
        "priority":
            analysis.get(
                "priority",
                "Medium"
            ),
        "department_code":
            code,
        "department":
            DEPARTMENTS[
                code
            ]["name"],
        "summary":
            analysis.get(
                "summary",
                complaint
            ),
        "action":
            analysis.get(
                "action",
                ""
            ),
        "impact":
            analysis.get(
                "impact",
                ""
            ),
        "status":
            "Assigned",
        "assigned_role":
            assigned_role,
        "assigned_role_name":
            ROLE_NAMES[
                assigned_role
            ],
        "district":
            district,
        "taluk":
            taluk,
        "block":
            block,
        "village":
            village,
        "analysis_mode":
            mode
    })


# =========================================================
# CITIZEN TRACKING
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>"
)
def track(complaint_id):

    db = get_db()

    row = db.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (
        complaint_id,
    )).fetchone()

    if not row:

        db.close()

        return jsonify({
            "error":
                "Complaint not found."
        }), 404

    result = dict(row)

    role = result.get(
        "assigned_role"
    )

    result[
        "assigned_role_name"
    ] = ROLE_NAMES.get(
        role,
        role
    ) if role else None

    history = db.execute("""
        SELECT
            action,
            status,
            officer_role,
            officer_name,
            created_at
        FROM complaint_history
        WHERE complaint_id = ?
        ORDER BY id ASC
    """, (
        complaint_id,
    )).fetchall()

    result["history"] = [
        dict(item)
        for item in history
    ]

    db.close()

    return jsonify(result)


# =========================================================
# COMPLAINT HISTORY
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>/history"
)
def complaint_history(complaint_id):

    if "role" not in session:

        return jsonify({
            "error":
                "Authentication required."
        }), 401

    db = get_db()

    complaint = db.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (
        complaint_id,
    )).fetchone()

    if not complaint:

        db.close()

        return jsonify({
            "error":
                "Complaint not found."
        }), 404

    if not can_access_complaint(
        complaint
    ):

        db.close()

        return jsonify({
            "error":
                "Access denied."
        }), 403

    rows = db.execute("""
        SELECT
            action,
            status,
            officer_role,
            officer_name,
            created_at
        FROM complaint_history
        WHERE complaint_id = ?
        ORDER BY id ASC
    """, (
        complaint_id,
    )).fetchall()

    db.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


# =========================================================
# OFFICER DASHBOARD
# =========================================================

@app.route(
    "/api/department"
)
def department_complaints():

    if not session.get(
        "user_id"
    ):

        return jsonify({
            "error":
                "Login required."
        }), 401

    db = get_db()

    role = current_role()

    department_code = (
        session.get(
            "department_code"
        )
    )

    rows = db.execute("""
        SELECT *
        FROM complaints
        WHERE department_code = ?
          AND assigned_role = ?
        ORDER BY id DESC
    """, (
        department_code,
        role
    )).fetchall()

    db.close()

    result = []

    for row in rows:

        complaint = dict(row)

        if not location_matches(
            complaint
        ):
            continue

        assigned_role = (
            complaint.get(
                "assigned_role"
            )
        )

        complaint[
            "assigned_role_name"
        ] = ROLE_NAMES.get(
            assigned_role,
            assigned_role
        )

        result.append(
            complaint
        )

    return jsonify(result)


# =========================================================
# ADMIN COMPLAINTS
# =========================================================

@app.route(
    "/api/complaints"
)
def complaints():

    if not is_admin():

        return jsonify({
            "error":
                "Administrator access required."
        }), 403

    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM complaints
        ORDER BY id DESC
    """).fetchall()

    db.close()

    result = []

    for row in rows:

        item = dict(row)

        item[
            "assigned_role_name"
        ] = ROLE_NAMES.get(
            item.get(
                "assigned_role"
            ),
            item.get(
                "assigned_role"
            )
        )

        result.append(item)

    return jsonify(result)


# =========================================================
# STATUS UPDATE
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>/status",
    methods=["POST"]
)
def update_status(complaint_id):

    if "role" not in session:

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

    allowed = [
        "Assigned",
        "In Progress",
        "Resolved",
        "Rejected"
    ]

    if status not in allowed:

        return jsonify({
            "error":
                "Invalid status."
        }), 400

    db = get_db()

    row = db.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (
        complaint_id,
    )).fetchone()

    if not row:

        db.close()

        return jsonify({
            "error":
                "Complaint not found."
        }), 404

    if not can_access_complaint(
        row
    ):

        db.close()

        return jsonify({
            "error":
                "This complaint is assigned to another government level or area."
        }), 403

    updated = now()

    db.execute("""
        UPDATE complaints
        SET status = ?,
            updated_at = ?
        WHERE complaint_id = ?
    """, (
        status,
        updated,
        complaint_id
    ))

    add_history(
        db,
        complaint_id,
        "Status Updated",
        status,
        current_role(),
        session.get(
            "name",
            "Government Officer"
        )
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "complaint_id":
            complaint_id,
        "status":
            status
    })


# =========================================================
# ESCALATION
# =========================================================

@app.route(
    "/api/complaint/<complaint_id>/escalate",
    methods=["POST"]
)
def escalate(complaint_id):

    if "role" not in session:

        return jsonify({
            "error":
                "Authentication required."
        }), 401

    db = get_db()

    row = db.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (
        complaint_id,
    )).fetchone()

    if not row:

        db.close()

        return jsonify({
            "error":
                "Complaint not found."
        }), 404

    if not can_access_complaint(
        row
    ):

        db.close()

        return jsonify({
            "error":
                "You cannot escalate this complaint."
        }), 403

    current = ROLE_ALIASES.get(
        row["assigned_role"]
        or "VILLAGE_OFFICER",
        row["assigned_role"]
        or "VILLAGE_OFFICER"
    )

    next_role = find_next_role(
        current
    )

    if not next_role:

        db.close()

        return jsonify({
            "error":
                "This complaint has reached the State Administrator level."
        }), 400

    next_level = (
        ROLE_ORDER[
            next_role
        ] + 1
    )

    next_user_id = assign_officer(
        db,
        row["department_code"],
        next_role,
        row["district"],
        row["taluk"],
        row["block"],
        row["village"]
    )

    updated = now()

        db.execute("""
        UPDATE complaints
        SET assigned_role = ?,
            assigned_user_id = ?,
            current_level = ?,
            status = ?,
            updated_at = ?
        WHERE complaint_id = ?
    """, (
        next_role,
        next_user_id,
        next_level,
        "Assigned",
        updated,
        complaint_id
    ))

    add_history(
        db,
        complaint_id,
        "Complaint Escalated",
        "Assigned",
        next_role,
        ROLE_NAMES[next_role]
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "complaint_id": complaint_id,
        "previous_role": current,
        "previous_role_name":
            ROLE_NAMES.get(
                current,
                current
            ),
        "new_role": next_role,
        "new_role_name":
            ROLE_NAMES[next_role],
        "assigned_user_id":
            next_user_id,
        "status": "Assigned"
    })


# =========================================================
# CREATE OFFICER
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
        data.get("name", "")
    ).strip()

    username = str(
        data.get("username", "")
    ).strip().lower()

    password = str(
        data.get("password", "")
    )

    code = str(
        data.get(
            "department_code",
            ""
        )
    ).strip().upper()

    role = str(
        data.get(
            "role",
            "DEPARTMENT_OFFICER"
        )
    ).strip().upper()

    district = str(
        data.get("district", "")
    ).strip()

    taluk = str(
        data.get("taluk", "")
    ).strip()

    block = str(
        data.get("block", "")
    ).strip()

    village = str(
        data.get("village", "")
    ).strip()

    allowed_roles = [
        x[0] for x in HIERARCHY
    ]

    if not name or not username:

        return jsonify({
            "error":
                "Name and username are required."
        }), 400

    if len(password) < 8:

        return jsonify({
            "error":
                "Password must contain at least 8 characters."
        }), 400

    if code not in DEPARTMENTS:

        return jsonify({
            "error":
                "Invalid department."
        }), 400

    if role not in allowed_roles:

        return jsonify({
            "error":
                "Invalid officer level."
        }), 400

    db = get_db()

    existing = db.execute("""
        SELECT id
        FROM users
        WHERE username = ?
    """, (
        username,
    )).fetchone()

    if existing:

        db.close()

        return jsonify({
            "error":
                "Username already exists."
        }), 409

    db.execute("""
        INSERT INTO users
        (
            name,
            username,
            password_hash,
            department_code,
            role,
            active,
            created_at,
            district,
            taluk,
            block,
            village
        )
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        username,
        generate_password_hash(
            password
        ),
        code,
        role,
        1,
        now(),
        district,
        taluk,
        block,
        village
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "message":
            "Officer account created.",
        "name": name,
        "username": username,
        "role": role,
        "role_name":
            ROLE_NAMES[role],
        "department_code": code,
        "department":
            DEPARTMENTS[code]["name"],
        "district": district,
        "taluk": taluk,
        "block": block,
        "village": village
    })


# =========================================================
# LIST OFFICERS
# =========================================================

@app.route("/api/admin/officers")
def list_officers():

    if not is_admin():

        return jsonify({
            "error":
                "Administrator access required."
        }), 403

    db = get_db()

    rows = db.execute("""
        SELECT
            id,
            name,
            username,
            department_code,
            role,
            active,
            created_at,
            district,
            taluk,
            block,
            village
        FROM users
        ORDER BY id DESC
    """).fetchall()

    db.close()

    result = []

    for row in rows:

        item = dict(row)

        role = ROLE_ALIASES.get(
            item["role"],
            item["role"]
        )

        item["role"] = role

        item["role_name"] = ROLE_NAMES.get(
            role,
            role
        )

        item["department"] = (
            DEPARTMENTS
            .get(
                item["department_code"],
                {}
            )
            .get(
                "name",
                item["department_code"]
            )
        )

        result.append(item)

    return jsonify(result)


# =========================================================
# ACTIVATE / DEACTIVATE OFFICER
# =========================================================

@app.route(
    "/api/admin/officers/<int:user_id>/active",
    methods=["POST"]
)
def change_officer(user_id):

    if not is_admin():

        return jsonify({
            "error":
                "Administrator access required."
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    active = data.get("active")

    if active not in [True, False]:

        return jsonify({
            "error":
                "Active must be true or false."
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
            "error":
                "Officer not found."
        }), 404

    return jsonify({
        "success": True,
        "user_id": user_id,
        "active": bool(active)
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    db = get_db()

    officers = db.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE active = 1
    """).fetchone()

    complaints = db.execute("""
        SELECT COUNT(*) AS c
        FROM complaints
    """).fetchone()

    history = db.execute("""
        SELECT COUNT(*) AS c
        FROM complaint_history
    """).fetchone()

    db.close()

    return jsonify({
        "status": "ok",
        "service":
            "Village Complaint Analyzer",
        "database": (
            "PostgreSQL"
            if using_postgres()
            else "SQLite"
        ),
        "openai_configured":
            bool(OPENAI_API_KEY),
        "local_fallback": True,
        "active_officers":
            officers["c"],
        "total_complaints":
            complaints["c"],
        "history_records":
            history["c"]
    })


# =========================================================
# RUN
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


    
