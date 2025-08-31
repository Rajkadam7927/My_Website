import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash  # For secure passwords

app = Flask(__name__)
CORS(app)  # allow cross-origin if needed later
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")  # set on Render

DATABASE_URL = os.environ.get("DATABASE_URL")  # set on Render (postgres://...)

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    # fallback for local dev (optional)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        dbname=os.environ.get("DB_NAME", "your_db"),
        user=os.environ.get("DB_USER", "your_user"),
        password=os.environ.get("DB_PASS", "your_pass"),
        port=os.environ.get("DB_PORT", "5432")
    )

# ---------------- ROUTES ---------------- #

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if user and check_password_hash(user["password"], password):
            session["username"] = user["username"]
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid Username or Password", "danger")

    return render_template("login.html")


@app.route("/index")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM employees;")
        total_employees = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM employees WHERE position_status = 'Open';")
        current_hirings = cur.fetchone()[0] or 0

        total_ambulance = 1936  # static value
    finally:
        cur.close()
        conn.close()

    return render_template(
        "index.html",
        total_employees=total_employees,
        current_hirings=current_hirings,
        total_ambulance=total_ambulance
    )


@app.route("/workforce")
def workforce():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
              id, prefix, name, applied_position, interview_status, finalized_position,
              status, position_status, remark, contact_no1, contact_no2, email, source,
              source_other, education, mode_of_interview, experience_years, current_company,
              current_ctc, expected_ctc, notice_period, offers_status, joining_date, resume_path
            FROM employees
            ORDER BY id DESC
        """)
        employees = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template("workforce_insights.html", employees=employees)


@app.route("/search")
def search_page():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("search.html")


@app.route("/search_employee")
def search_employee():
    if "username" not in session:
        return jsonify([]), 401

    contact = request.args.get("contact", "").strip()
    if not contact:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM employees
            WHERE contact_no1 = %s OR contact_no2 = %s
            ORDER BY id DESC
        """, (contact, contact))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify(rows)


@app.route("/update_employee/<int:emp_id>", methods=["POST"])
def update_employee(emp_id):
    if "username" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    data = request.get_json() or {}
    allowed = {
        "interview_status","finalized_position","mode_of_interview","experience_years",
        "current_company","current_ctc","expected_ctc","notice_period","offers_status",
        "joining_date","status","remark","contact_no1","contact_no2","email","source","source_other"
    }
    set_parts = []
    values = []
    for k, v in data.items():
        if k in allowed:
            set_parts.append(f"{k} = %s")
            values.append(v)
    if not set_parts:
        return jsonify({"success": False, "message": "No updatable fields provided"}), 400

    values.append(emp_id)
    sql = f"UPDATE employees SET {', '.join(set_parts)} WHERE id = %s"
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()
    return jsonify({"success": True})


@app.route("/add_record", methods=["GET", "POST"])
def add_record():
    if "username" not in session:
        return redirect(url_for("login")) if request.method == "GET" else (jsonify({"success": False, "message": "Not logged in"}), 401)

    if request.method == "GET":
        return render_template("add_record.html")

    form = request.form
    f = request.files.get("resume_path")
    resume_filename = f.filename if f else None

    fields = [
        "prefix","name","applied_position","interview_status","finalized_position","status",
        "position_status","remark","contact_no1","contact_no2","email","source","source_other",
        "education","mode_of_interview","experience_years","current_company","current_ctc",
        "expected_ctc","notice_period","offers_status","joining_date","resume_path"
    ]
    values = []
    for fld in fields:
        if fld == "resume_path":
            values.append(resume_filename)
        else:
            values.append(form.get(fld))

    placeholders = ",".join(["%s"] * len(fields))
    cols = ",".join(fields)
    sql = f"INSERT INTO employees ({cols}) VALUES ({placeholders})"

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

    return jsonify({"success": True, "message": "Record added successfully"})


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("You have been logged out", "info")
    return redirect(url_for("login"))


@app.route("/health")
def health():
    return jsonify({"ok": True})


# ---------------- HELPER: Create hashed password ---------------- #
def create_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_pw))
        conn.commit()
    finally:
        cur.close()
        conn.close()


# ---------------- RUN ---------------- #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
