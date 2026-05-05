import random
import os
import traceback
from datetime import datetime, timedelta, UTC
from functools import wraps

from flask import Flask, render_template, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ================= APP SETUP =================
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"


# ================= UPLOAD CONFIG =================
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return render_template("home.html")

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

app.config["MAIL_USERNAME"] = "official.wecapture@gmail.com"
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # Render ENV
app.config["MAIL_DEFAULT_SENDER"] = app.config["MAIL_USERNAME"]

app.config["MAIL_DEBUG"] = True


mail = Mail()
mail.init_app(app)
db = SQLAlchemy(app)

app.config["MAIL_TIMEOUT"] = 10


# ================= GLOBAL CONSTANTS =================
ADMIN_EMAIL = "official.wecapture@gmail.com"


print("MAIL USER:", app.config["MAIL_USERNAME"])
print("MAIL PASS LOADED:", bool(app.config["MAIL_PASSWORD"]))

# ================= MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)

    password_hash = db.Column(db.String(200), nullable=False)

    otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

    is_verified = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)

    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)

    showroom_name = db.Column(db.String(150))
    showroom_address = db.Column(db.String(250))
    delivery_location = db.Column(db.String(200))

    salesperson_name = db.Column(db.String(100))
    salesperson_phone = db.Column(db.String(20))

    delivery_date = db.Column(db.Date, nullable=False)
    delivery_time = db.Column(db.Time, nullable=False)

    package_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="Pending")

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    file_url = db.Column(db.String(300), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)  # image/video


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=False)

    name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.String(500), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )

    # ================= HELPERS =================

def generate_otp():
    return str(random.randint(100000, 999999))


def get_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


# ================= DECORATORS =================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Login first", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Admin login required", "danger")
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper


# ================= CONTEXT PROCESSOR =================

@app.context_processor
def inject_user():
    return dict(current_user=get_user())

# ================= SIGNUP =================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"].strip().lower()
        phone = request.form["phone"]
        password = request.form["password"]

        # check if user exists
        if User.query.filter_by(email=email).first():
            flash("Email already exists", "danger")
            return redirect("/signup")

        # generate OTP
        otp = generate_otp()

        session["temp_user"] = {
            "username": username,
            "email": email,
            "phone": phone,
            "password": password,
            "otp": otp,
            "otp_expiry": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        }

        # EMAIL
        msg = Message(
            subject="We Capture OTP Verification",
            recipients=[email]
        )

        msg.html = f"""
        <h2>We Capture 🎥</h2>
        <p>Hello {username},</p>

        <p>Your OTP is:</p>
        <h1 style="color:#d7ad4b;">{otp}</h1>

        <p>This OTP is valid for 5 minutes.</p>
        """

        try:
            mail.send(msg)
            flash("OTP sent to your email successfully", "success")
            return redirect(f"/verify_signup/{email}")

        except Exception as e:
            print("EMAIL ERROR:", str(e))
            flash("Email failed. Check server logs.", "danger")
            return redirect("/signup")

    return render_template("signup.html")


# ================= VERIFY SIGNUP =================

@app.route("/verify_signup/<email>", methods=["GET", "POST"])
def verify_signup(email):

    temp_user = session.get("temp_user")

    if not temp_user or temp_user["email"] != email:
        flash("Session expired. Please signup again.", "danger")
        return redirect("/signup")

    if request.method == "POST":

        otp = request.form["otp"]

        if otp != temp_user["otp"]:
            flash("Invalid OTP", "danger")
            return redirect(request.url)

        expiry = datetime.fromisoformat(temp_user["otp_expiry"])

        if datetime.now(UTC) > expiry:
            flash("OTP expired", "danger")
            return redirect("/signup")

        # CREATE USER
        user = User(
            username=temp_user["username"],
            email=temp_user["email"],
            phone=temp_user["phone"],
            is_verified=True
        )

        user.set_password(temp_user["password"])

        db.session.add(user)
        db.session.commit()

        session.pop("temp_user", None)
        session["user_id"] = user.id

        flash("Account created successfully 🎉")
        return redirect("/booking")

    return render_template("verify_signup.html", email=email)

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("User not found", "danger")
            return redirect("/login")

        if not user.check_password(password):
            flash("Invalid credentials", "danger")
            return redirect("/login")

        if not user.is_verified:
            flash("Verify your email first", "warning")
            return redirect("/login")

        session["user_id"] = user.id
        return redirect("/booking")

    return render_template("login.html")


# ================= Query =================

@app.route("/send_query", methods=["POST"])
def send_query():
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    location = request.form.get("location")
    message = request.form.get("message")

    try:
        msg = Message(
            subject="New Query - We Capture",
            recipients=[ADMIN_EMAIL]
        )

        msg.html = f"""
        <h2>New Query Received</h2>
        <p><b>Name:</b> {name}</p>
        <p><b>Email:</b> {email}</p>
        <p><b>Phone:</b> {phone}</p>
        <p><b>Location:</b> {location}</p>
        <p><b>Message:</b> {message}</p>
        """

        mail.send(msg)
        flash("Query sent successfully!", "success")

    except Exception as e:
        print("QUERY EMAIL ERROR:", e)
        flash("Failed to send query", "danger")

    return redirect("/")
    
# ================= LOGOUT =================

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect("/")


# ================= FORGOT PASSWORD =================

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("User not found", "danger")
            return redirect("/forgot_password")

        otp = generate_otp()

        user.otp = otp
        user.otp_expiry = datetime.now(UTC) + timedelta(minutes=5)
        db.session.commit()

        msg = Message(
            subject="We Capture - Reset Password OTP",
            recipients=[email]
        )

        msg.html = f"""
        <h2>We Capture 🎥</h2>
        <p>Password reset request received.</p>

        <p>Your OTP:</p>
        <h1 style="color:#d7ad4b;">{otp}</h1>

        <p>Valid for 5 minutes.</p>
        """

        try:
            mail.send(msg)
            flash("Reset OTP sent to email", "success")

        except Exception as e:
            print("RESET EMAIL ERROR:", str(e))
            flash("Email failed", "danger")

        return redirect(f"/reset_password/{email}")

    return render_template("forgot_password.html")


# ================= RESET PASSWORD =================

@app.route("/reset_password/<email>", methods=["GET", "POST"])
def reset_password(email):

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("User not found", "danger")
        return redirect("/forgot_password")

    if request.method == "POST":

        otp = request.form["otp"]
        password = request.form["password"]

        if user.otp != otp:
            flash("Invalid OTP", "danger")
            return redirect(request.url)

        if not user.otp_expiry or user.otp_expiry < datetime.now(UTC):
            flash("OTP expired", "danger")
            return redirect("/forgot_password")

        user.set_password(password)

        # clear OTP after use
        user.otp = None
        user.otp_expiry = None

        db.session.commit()

        flash("Password updated successfully")
        return redirect("/login")

    return render_template("reset_password.html")

# ================= BOOKING =================

@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():

    PACKAGES = {
        "Signature Moment": {
            "price": "₹4,799",
            "summary": "Simple stylish delivery celebration.",
            "features": [
                "Celebration Cake",
                "Flower Setup",
                "Cinematic Reel"
            ]
        },
        "Elite Experience": {
            "price": "₹13,999",
            "summary": "Grand entry experience.",
            "features": [
                "Red Carpet Entry",
                "Fire Effects",
                "Cinematic Reel"
            ]
        }
    }

    if request.method == "POST":

        try:
            booking = Booking(
                user_id=session["user_id"],
                full_name=request.form["full_name"],
                phone=request.form["phone"],
                email=request.form["email"],
                showroom_name=request.form.get("showroom_name"),
                showroom_address=request.form.get("showroom_address"),
                delivery_location=request.form.get("delivery_location"),
                salesperson_name=request.form.get("salesperson_name"),
                salesperson_phone=request.form.get("salesperson_phone"),
                delivery_date=datetime.strptime(request.form["delivery_date"], "%Y-%m-%d").date(),
                delivery_time=datetime.strptime(request.form["delivery_time"], "%H:%M").time(),
                package_name=request.form["package_name"]
            )

            db.session.add(booking)
            db.session.commit()

            # ================= ADMIN EMAIL =================
            ADMIN_EMAIL = "official.wecapture@gmail.com"

            msg = Message(
                subject="🚗 New Booking Received",
                recipients=[ADMIN_EMAIL]
            )

            msg.html = f"""
            <h2>New Booking 🚗</h2>

            <p><b>Name:</b> {booking.full_name}</p>
            <p><b>Phone:</b> {booking.phone}</p>
            <p><b>Email:</b> {booking.email}</p>

            <hr>

            <p><b>Showroom:</b> {booking.showroom_name}</p>
            <p><b>Delivery:</b> {booking.delivery_location}</p>

            <hr>

            <p><b>Date:</b> {booking.delivery_date}</p>
            <p><b>Time:</b> {booking.delivery_time}</p>

            <p><b>Package:</b> {booking.package_name}</p>
            """

            mail.send(msg)

            flash("Booking successful!", "success")
            return redirect(f"/booking_success/{booking.id}")

        except Exception as e:
            print("BOOKING ERROR:", str(e))
            flash("Booking failed. Try again.", "danger")
            return redirect("/booking")

    return render_template("booking.html", packages=PACKAGES)


# ================= BOOKING SUCCESS =================

@app.route("/booking_success/<int:id>")
@login_required
def booking_success(id):
    booking = Booking.query.get_or_404(id)
    return render_template("booking_success.html", booking=booking)


# ================= MY BOOKINGS =================

@app.route("/my_bookings")
@login_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=session["user_id"]).all()
    return render_template("my_bookings.html", bookings=bookings)

# ================= ADMIN LOGIN =================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    ADMIN_PASSWORD = "wecapture@2627"
    ADMIN_EMAIL_LOCAL = "official.wecapture@gmail.com"

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        if email == ADMIN_EMAIL_LOCAL and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Admin login successful")
            return redirect("/admin")

        flash("Invalid admin credentials", "danger")

    return render_template("admin_login.html")


# ================= ADMIN DASHBOARD =================

@app.route("/admin")
@admin_required
def admin_dashboard():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    media = Media.query.all()
    return render_template("admin_dashboard.html", bookings=bookings, media=media)


# ================= ADMIN LOGOUT =================

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out")
    return redirect("/admin/login")


# ================= STATUS UPDATE EMAIL =================

@app.route("/admin/update_status/<int:id>/<status>")
@admin_required
def update_status(id, status):

    booking = Booking.query.get_or_404(id)

    booking.status = status
    db.session.commit()

    msg = Message(
        subject=f"We Capture - Booking {status}",
        recipients=[booking.email]
    )

    if status == "Confirmed":
        msg.html = f"""
        <h2>Booking Confirmed ✅</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking is confirmed.</p>
        """

    elif status == "Completed":
        msg.html = f"""
        <h2>Service Completed 🚚</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your service is completed.</p>
        """

    elif status == "Cancelled":
        msg.html = f"""
        <h2>Booking Cancelled ❌</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking was cancelled.</p>
        """

    try:
        mail.send(msg)
        flash("Status updated + email sent", "success")
    except Exception as e:
        print("STATUS EMAIL ERROR:", str(e))
        flash("Status updated but email failed", "warning")

    return redirect("/admin")


# ================= MEDIA UPLOAD =================

@app.route("/admin/upload_media", methods=["GET", "POST"])
@admin_required
def upload_media():

    if request.method == "POST":

        file = request.files["file"]
        media_type = request.form["media_type"]

        if file:

            filename = secure_filename(file.filename)

            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(filepath)

            file_url = "/" + filepath.replace("\\", "/")

            media = Media(file_url=file_url, media_type=media_type)
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
        print("DELETE FILE ERROR:", str(e))

    db.session.delete(media)
    db.session.commit()

    flash("Media deleted", "success")
    return redirect("/admin")


# ================= REVIEWS =================

@app.route("/add_review", methods=["POST"])
@login_required
def add_review():

    user = get_user()

    rating = int(request.form.get("rating", 0))
    text = request.form["text"]

    review = Review(
        user_id=user.id,
        name=user.username,
        rating=rating,
        text=text
    )

    db.session.add(review)
    db.session.commit()

    flash("Review added!", "success")
    return redirect("/")


@app.route("/delete_review/<int:id>")
@login_required
def delete_review(id):

    review = Review.query.get_or_404(id)
    user = get_user()

    if review.user_id == user.id or session.get("admin_logged_in"):

        db.session.delete(review)
        db.session.commit()
        flash("Review deleted", "success")

    else:
        flash("Not allowed", "danger")

    return redirect("/")

# ================= MAIN RUN (RENDER SAFE) =================

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    # Render / production safe port handling
    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
