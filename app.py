
import os
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from dotenv import load_dotenv
from database import get_db_connection

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing from .env")


# Admin login protection
def admin_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)
    return wrapper


# Admin login page
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        admin_username = os.getenv("ADMIN_USERNAME")
        admin_password = os.getenv("ADMIN_PASSWORD")

        if (
            admin_username
            and admin_password
            and username == admin_username
            and password == admin_password
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


# Admin logout
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# Admin dashboard
@app.route("/dashboard")
@admin_required
def dashboard():
    with get_db_connection() as connection:
        total_students = connection.execute(
            "SELECT COUNT(*) FROM public.students"
        ).fetchone()[0]

        branch_stats = connection.execute(
            """
            SELECT branch, COUNT(*)
            FROM public.students
            GROUP BY branch
            ORDER BY branch
            """
        ).fetchall()

        year_stats = connection.execute(
            """
            SELECT year, COUNT(*)
            FROM public.students
            GROUP BY year
            ORDER BY year
            """
        ).fetchall()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        branch_stats=branch_stats,
        year_stats=year_stats
    )


# Home page + Search (admin only)
@app.route("/")
@admin_required
def home():
    search = request.args.get("search", "").strip()

    with get_db_connection() as connection:
        if search:
            rows = connection.execute(
                """
                SELECT * FROM public.students
                WHERE name ILIKE %s OR roll ILIKE %s
                ORDER BY id DESC
                """,
                (f"%{search}%", f"%{search}%")
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM public.students ORDER BY id DESC"
            ).fetchall()

    columns = ["id", "name", "roll", "branch", "year", "email"]
    students = [
        dict(row) if hasattr(row, "keys") else dict(zip(columns, row))
        for row in rows
    ]

    return render_template(
        "index.html",
        students=students,
        search=search
    )


# Add student (admin only)
@app.route("/add", methods=["POST"])
@admin_required
def add_student():
    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip()
    branch = request.form.get("branch", "").strip()
    year_text = request.form.get("year", "").strip()
    email = request.form.get("email", "").strip()

    if not all([name, roll, branch, year_text, email]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("home"))

    try:
        year = int(year_text)
        if year not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        flash("Year must be between 1 and 4.", "error")
        return redirect(url_for("home"))

    try:
        with get_db_connection() as connection:
            existing = connection.execute(
                """
                SELECT id FROM public.students
                WHERE LOWER(roll) = LOWER(%s)
                """,
                (roll,)
            ).fetchone()

            if existing:
                flash("This roll number is already registered.", "error")
                return redirect(url_for("home"))

            connection.execute(
                """
                INSERT INTO public.students
                    (name, roll, branch, year, email)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (name, roll, branch, year, email)
            )

        flash("Student registered successfully!", "success")

    except Exception:
        app.logger.exception("Could not register student")
        flash("Registration failed. Please try again.", "error")

    return redirect(url_for("home"))


# Edit form (admin only)
@app.route("/edit/<int:student_id>")
@admin_required
def edit_student(student_id):
    with get_db_connection() as connection:
        student = connection.execute(
            "SELECT * FROM public.students WHERE id = %s",
            (student_id,)
        ).fetchone()

    if student is None:
        return "Student not found", 404

    columns = ["id", "name", "roll", "branch", "year", "email"]
    if not hasattr(student, "keys"):
        student = dict(zip(columns, student))

    return render_template("edit.html", student=student)


# Update student (admin only)
@app.route("/update/<int:student_id>", methods=["POST"])
@admin_required
def update_student(student_id):
    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip()
    branch = request.form.get("branch", "").strip()
    year_text = request.form.get("year", "").strip()
    email = request.form.get("email", "").strip()

    if not all([name, roll, branch, year_text, email]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("edit_student", student_id=student_id))

    try:
        year = int(year_text)
        if year not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        flash("Year must be between 1 and 4.", "error")
        return redirect(url_for("edit_student", student_id=student_id))

    with get_db_connection() as connection:
        duplicate = connection.execute(
            """
            SELECT id FROM public.students
            WHERE LOWER(roll) = LOWER(%s) AND id <> %s
            """,
            (roll, student_id)
        ).fetchone()

        if duplicate:
            return "That roll number is already in use.", 409

        connection.execute(
            """
            UPDATE public.students
            SET name = %s, roll = %s, branch = %s, year = %s, email = %s
            WHERE id = %s
            """,
            (name, roll, branch, year, email, student_id)
        )

    flash("Student updated successfully!", "success")
    return redirect(url_for("home"))


# Delete student (admin only)
@app.route("/delete/<int:student_id>", methods=["POST"])
@admin_required
def delete_student(student_id):
    with get_db_connection() as connection:
        connection.execute(
            "DELETE FROM public.students WHERE id = %s",
            (student_id,)
        )

    flash("Student deleted successfully!", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
