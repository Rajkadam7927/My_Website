import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        dbname=os.environ.get("DB_NAME", "your_db"),
        user=os.environ.get("DB_USER", "your_user"),
        password=os.environ.get("DB_PASS", "your_pass"),
        port=os.environ.get("DB_PORT", "5432")
    )

# ---------------- LOGIN ---------------- #
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

# ---------------- DASHBOARD ---------------- #
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

        total_ambulance = 1936
    finally:
        cur.close()
        conn.close()

    return render_template(
        "index.html",
        total_employees=total_employees,
        current_hirings=current_hirings,
        total_ambulance=total_ambulance
    )

# ---------------- WORKFORCE INSIGHTS ---------------- #
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
        employees = cur.fetchall() or []

        expected_keys = [
            "id","prefix","name","applied_position","interview_status","finalized_position",
            "status","position_status","remark","contact_no1","contact_no2","email","source",
            "source_other","education","mode_of_interview","experience_years","current_company",
            "current_ctc","expected_ctc","notice_period","offers_status","joining_date","resume_path"
        ]
        for emp in employees:
            for key in expected_keys:
                if key not in emp or emp[key] is None:
                    emp[key] = ""
    finally:
        cur.close()
        conn.close()

    return render_template("workforce_insights.html", employees=employees)

# ---------------- SEARCH EMPLOYEE ---------------- #
@app.route("/search_employee")
def search_employee():
    if "username" not in session:
        return jsonify([])

    contact = request.args.get("contact","")
    if not contact: return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM employees WHERE contact_no1=%s OR contact_no2=%s", (contact, contact))
        employee = cur.fetchall()
        keys = [desc[0] for desc in cur.description]
        for emp in employee:
            for k in keys:
                if k not in emp or emp[k] is None:
                    emp[k] = ""
    finally:
        cur.close()
        conn.close()
    return jsonify(employee)

# ---------------- UPDATE EMPLOYEE ---------------- #
@app.route("/update_employee/<int:emp_id>", methods=["POST"])
def update_employee(emp_id):
    if "username" not in session:
        return jsonify({"success":False, "message":"Not logged in"})

    data = request.get_json()
    if not data: 
        return jsonify({"success":False, "message":"No data provided"})

    # Optional: define required fields
    required_fields = ["status", "interview_status"]
    for field in required_fields:
        if field in data and not data[field]:
            return jsonify({"success":False, "message":f"{field} is required"})

    filtered_data = {k:v for k,v in data.items() if v != ""}

    if not filtered_data:
        return jsonify({"success":False, "message":"No fields to update"})

    set_clause = ", ".join([f"{k}=%s" for k in filtered_data.keys()])
    values = list(filtered_data.values()) + [emp_id]

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE employees SET {set_clause} WHERE id=%s", values)
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return jsonify({"success":True, "message":"Data updated successfully"})

# ---------------- ADD RECORD ---------------- #
@app.route("/add_record", methods=["GET","POST"])
def add_record():
    if "username" not in session:
        return redirect(url_for("login"))

    required_fields = ["name","applied_position","contact_no1","status"]  # example

    if request.method=="POST":
        try:
            data = request.form.to_dict()
            file = request.files.get("resume_path")
            resume_path = ""
            if file and file.filename:
                os.makedirs("resumes", exist_ok=True)
                resume_path = f"resumes/{file.filename}"
                file.save(resume_path)
            data['resume_path'] = resume_path

            # Validate required fields
            for field in required_fields:
                if not data.get(field):
                    return jsonify({"success":False, "message":f"{field} is required"})

            # Only insert non-empty fields
            insert_data = {k:v for k,v in data.items() if v != ""}

            columns = insert_data.keys()
            values = [insert_data[col] for col in columns]

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO employees ({','.join(columns)}) VALUES ({','.join(['%s']*len(values))})
            """, values)
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success":True, "message":"Record added successfully"})
        except Exception as e:
            return jsonify({"success":False, "message":str(e)})

    return render_template("add_record.html")

# ---------------- LOGOUT ---------------- #
@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("You have been logged out", "info")
    return redirect(url_for("login"))

# ---------------- HEALTH CHECK ---------------- #
@app.route("/health")
def health():
    return jsonify({"ok": True})

# ---------------- HELPER: Create User ---------------- #
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
