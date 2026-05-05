import os
import random
import traceback
from datetime import datetime, timedelta, UTC
from functools import wraps

from flask import Flask, render_template, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import smtplib


# ================= APP INIT =================
app = Flask(__name__)

# IMPORTANT: use env in production (Render safe)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")


# ================= UPLOAD CONFIG =================
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ================= DATABASE =================
uri = os.getenv("DATABASE_URL")

if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = uri or "sqlite:///we_capture.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ================= MAIL CONFIG =================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "official.wecapture@gmail.com")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = app.config["MAIL_USERNAME"]


# ================= INIT EXTENSIONS =================
db = SQLAlchemy(app)
mail = Mail(app)


# ================= OWNER EMAIL =================
ADMIN_EMAIL = app.config["MAIL_USERNAME"]  # always sends to official email


# ================= EMAIL SENDER (ROBUST FIX) =================
def send_email(msg):
    """
    Priority:
    1. Flask-Mail (Render friendly if SMTP allowed)
    2. SMTP fallback
    """

    try:
        # Try Flask-Mail first
        mail.send(msg)
        return True, None

    except Exception as e1:
        print("Flask-Mail failed:", e1)

        # fallback SMTP
        try:
            if not app.config["MAIL_PASSWORD"]:
                return False, "MAIL_PASSWORD not set"

            smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
            smtp.starttls()
            smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])

            smtp.sendmail(
                app.config["MAIL_USERNAME"],
                msg.recipients,
                msg.as_string()
            )

            smtp.quit()
            return True, None

        except Exception as e2:
            print("SMTP fallback failed:", e2)
            return False, str(e2)


# ================= DEBUG =================
print("MAIL USER:", app.config["MAIL_USERNAME"])
print("MAIL PASSWORD LOADED:", bool(app.config["MAIL_PASSWORD"]))
print("ADMIN EMAIL:", ADMIN_EMAIL)

# ================= MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))

    password_hash = db.Column(db.String(200), nullable=False)

    otp = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    is_verified = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))

    showroom_name = db.Column(db.String(150))
    showroom_address = db.Column(db.String(250))
    delivery_location = db.Column(db.String(200))

    salesperson_name = db.Column(db.String(100))
    salesperson_phone = db.Column(db.String(20))

    delivery_date = db.Column(db.Date)
    delivery_time = db.Column(db.Time)

    package_name = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    file_url = db.Column(db.String(300), nullable=False)
    media_type = db.Column(db.String(10))  # image/video

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(100))
    rating = db.Column(db.Integer)
    text = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@app.route("/verify_signup/<email>", methods=["GET", "POST"])
def verify_signup(email):

    temp_user = session.get("temp_user")

    if not temp_user or temp_user["email"] != email:
        flash("Session expired. Please signup again.", "danger")
        return redirect("/signup")

    if request.method == "POST":

        otp = request.form["otp"]

        # OTP check
        if otp != temp_user["otp"]:
            flash("Invalid OTP", "danger")
            return redirect(request.url)

        # expiry check (SAFE)
        expiry = datetime.fromisoformat(temp_user["otp_expiry"])

        if datetime.utcnow() > expiry:
            flash("OTP expired", "danger")
            session.pop("temp_user", None)
            return redirect("/signup")

        # create user
        user = User(
            username=temp_user["username"],
            email=temp_user["email"],
            phone=temp_user["phone"],
            is_verified=True
        )

        user.set_password(temp_user["password"])

        db.session.add(user)
        db.session.commit()

        # cleanup
        session.pop("temp_user", None)
        session["user_id"] = user.id

        flash("Account created successfully 🚀", "success")
        return redirect("/booking")

    return render_template("verify_signup.html", email=email)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        # invalid credentials
        if not user or not user.check_password(password):
            flash("Invalid credentials", "danger")
            return redirect("/login")

        # email not verified
        if not user.is_verified:
            flash("Please verify your email first", "warning")
            return redirect("/login")

        # SESSION CLEAR (important fix)
        session.clear()
        session["user_id"] = user.id

        flash("Login successful 🚀", "success")
        return redirect("/booking")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect("/")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "official.wecapture@gmail.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "wecapture@2627")

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:

            session.clear()
            session["admin_logged_in"] = True

            flash("Admin logged in successfully 🚀", "success")
            return redirect("/admin")

        flash("Invalid admin credentials", "danger")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out")
    return redirect("/admin/login")

@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():

    PACKAGES = {
        "Signature Moment": {"price": "₹4,799"},
        "Elite Experience": {"price": "₹13,999"},
        "Legacy Arrival": {"price": "₹79,999"},
        "Prestige VIP Experience": {"price": "₹1,79,000"}
    }

    if request.method == "POST":

        try:
            new_booking = Booking(
                user_id=session["user_id"],
                full_name=request.form["full_name"],
                phone=request.form["phone"],
                email=request.form["email"].strip().lower(),

                showroom_name=request.form["showroom_name"],
                showroom_address=request.form["showroom_address"],
                delivery_location=request.form["delivery_location"],

                salesperson_name=request.form["salesperson_name"],
                salesperson_phone=request.form["salesperson_phone"],

                delivery_date=datetime.strptime(
                    request.form["delivery_date"], "%Y-%m-%d"
                ).date(),

                delivery_time=datetime.strptime(
                    request.form["delivery_time"], "%H:%M"
                ).time(),

                package_name=request.form["package_name"],
                status="Pending"
            )

            db.session.add(new_booking)
            db.session.commit()

            # ================= OWNER EMAIL =================
            msg = Message(
                subject="🚗 New Booking Received - We Capture",
                recipients=[ADMIN_EMAIL]
            )

            msg.html = f"""
            <h2>🚗 New Booking Alert</h2>

            <p><b>Name:</b> {new_booking.full_name}</p>
            <p><b>Phone:</b> {new_booking.phone}</p>
            <p><b>Email:</b> {new_booking.email}</p>

            <hr>

            <p><b>Showroom:</b> {new_booking.showroom_name}</p>
            <p><b>Address:</b> {new_booking.showroom_address}</p>

            <hr>

            <p><b>Delivery:</b> {new_booking.delivery_location}</p>

            <hr>

            <p><b>Salesperson:</b> {new_booking.salesperson_name}</p>
            <p><b>Sales Phone:</b> {new_booking.salesperson_phone}</p>

            <hr>

            <p><b>Date:</b> {new_booking.delivery_date}</p>
            <p><b>Time:</b> {new_booking.delivery_time}</p>

            <hr>

            <p><b>Package:</b> {new_booking.package_name}</p>
            """

            success, error = send_email(msg)

            if not success:
                print("BOOKING EMAIL FAILED:", error)
                flash("Booking saved but email failed", "warning")
            else:
                flash("Booking submitted successfully 🚀", "success")

            return redirect(f"/booking_success/{new_booking.id}")

        except Exception:
            db.session.rollback()
            print("BOOKING ERROR:\n", traceback.format_exc())
            flash("Something went wrong while booking", "danger")
            return redirect("/booking")

    return render_template("booking.html", packages=PACKAGES)

@app.route("/admin/update_status/<int:id>/<status>")
@admin_required
def update_status(id, status):

    try:
        booking = Booking.query.get_or_404(id)
        booking.status = status
        db.session.commit()

        # ================= EMAIL TO USER =================
        msg = Message(
            subject=f"We Capture - Booking {status}",
            recipients=[booking.email]
        )

        if status == "Confirmed":
            msg.html = f"""
            <h2>Booking Confirmed ✅</h2>
            <p>Hello {booking.full_name},</p>
            <p>Your booking is confirmed.</p>
            <p><b>Date:</b> {booking.delivery_date}</p>
            <p><b>Time:</b> {booking.delivery_time}</p>
            """

        elif status == "Completed":
            msg.html = f"""
            <h2>Service Completed 🚚</h2>
            <p>Hello {booking.full_name},</p>
            <p>Your service is completed successfully.</p>
            """

        elif status == "Cancelled":
            msg.html = f"""
            <h2>Booking Cancelled ❌</h2>
            <p>Hello {booking.full_name},</p>
            <p>Your booking has been cancelled.</p>
            """

        else:
            msg.html = f"""
            <p>Status updated: {status}</p>
            """

        success, error = send_email(msg)

        if not success:
            print("STATUS EMAIL FAILED:", error)
            flash("Status updated but email failed", "warning")
        else:
            flash("Status updated & email sent 🚀", "success")

    except Exception:
        db.session.rollback()
        print("STATUS UPDATE ERROR:\n", traceback.format_exc())
        flash("Failed to update status", "danger")

    return redirect("/admin")

@app.route("/admin/upload_media", methods=["GET", "POST"])
@admin_required
def upload_media():

    if request.method == "POST":

        file = request.files.get("file")
        media_type = request.form.get("media_type")

        if not file or file.filename == "":
            flash("No file selected", "danger")
            return redirect("/admin/upload_media")

        try:
            # secure filename (CRITICAL FIX)
            filename = secure_filename(file.filename)

            # unique name to avoid overwrite
            unique_name = f"{datetime.utcnow().timestamp()}_{filename}"

            filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

            file.save(filepath)

            file_url = f"/static/uploads/{unique_name}"

            media = Media(
                file_url=file_url,
                media_type=media_type
            )

            db.session.add(media)
            db.session.commit()

            flash("Media uploaded successfully 🚀", "success")

        except Exception:
            print("UPLOAD ERROR:\n", traceback.format_exc())
            flash("Upload failed", "danger")

        return redirect("/admin/upload_media")

    return render_template("upload_media.html")

@app.route("/admin/delete_media/<int:id>")
@admin_required
def delete_media(id):

    try:
        media = Media.query.get_or_404(id)

        # convert URL → real file path
        file_path = media.file_url.replace("/static/", "static/")

        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(media)
        db.session.commit()

        flash("Media deleted successfully", "success")

    except Exception:
        db.session.rollback()
        print("DELETE MEDIA ERROR:\n", traceback.format_exc())
        flash("Failed to delete media", "danger")

    return redirect("/admin")

# ================= ADMIN DASHBOARD =================

@app.route("/admin")
@admin_required
def admin_dashboard():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    media = Media.query.all()
    return render_template("admin_dashboard.html", bookings=bookings, media=media)


# ================= UPDATE BOOKING STATUS =================

@app.route("/admin/update_status/<int:id>/<status>")
@admin_required
def update_status(id, status):

    booking = Booking.query.get_or_404(id)
    booking.status = status
    db.session.commit()

    # EMAIL TO USER
    msg = Message(
        subject=f"We Capture - Booking {status}",
        recipients=[booking.email]
    )

    if status == "Confirmed":
        msg.html = f"""
        <h2>Booking Confirmed ✅</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking is confirmed.</p>
        <p><b>Date:</b> {booking.delivery_date}</p>
        <p><b>Time:</b> {booking.delivery_time}</p>
        """

    elif status == "Completed":
        msg.html = f"""
        <h2>Service Completed 🚚</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your service is completed successfully.</p>
        """

    elif status == "Cancelled":
        msg.html = f"""
        <h2>Booking Cancelled ❌</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking has been cancelled.</p>
        """

    else:
        msg.html = f"<p>Status updated: {status}</p>"

    try:
        mail.send(msg)
    except Exception as e:
        print("STATUS EMAIL ERROR:", e)

    flash("Status updated successfully", "success")
    return redirect("/admin")


# ================= UPLOAD MEDIA =================

@app.route("/admin/upload_media", methods=["GET", "POST"])
@admin_required
def upload_media():

    if request.method == "POST":

        file = request.files.get("file")
        media_type = request.form.get("media_type")

        if file and file.filename != "":

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(filepath)

            file_url = "/" + filepath.replace("\\", "/")

            media = Media(
                file_url=file_url,
                media_type=media_type
            )

            db.session.add(media)
            db.session.commit()

            flash("Media uploaded successfully", "success")

        return redirect("/admin/upload_media")

    return render_template("upload_media.html")


# ================= DELETE MEDIA =================

@app.route("/admin/delete_media/<int:id>")
@admin_required
def delete_media(id):

    media = Media.query.get_or_404(id)

    try:
        file_path = media.file_url.lstrip("/")
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print("DELETE FILE ERROR:", e)

    db.session.delete(media)
    db.session.commit()

    flash("Media deleted successfully", "success")
    return redirect("/admin")

