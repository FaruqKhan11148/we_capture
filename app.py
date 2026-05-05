import random
from datetime import datetime, timedelta, UTC
from functools import wraps

from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

import os
from werkzeug.utils import secure_filename

# CREATE APP ONLY ONCE
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"

# UPLOAD CONFIG
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# AUTO CREATE FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# DATABASE
uri = os.getenv("DATABASE_URL")

if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = uri or "sqlite:///we_capture.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# MAIL CONFIG
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False

app.config["MAIL_USERNAME"] = "official.wecapture@gmail.com"
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # IMPORTANT
app.config["MAIL_DEFAULT_SENDER"] = app.config["MAIL_USERNAME"]

app.config["MAIL_DEBUG"] = True
app.config["MAIL_SUPPRESS_SEND"] = False

# NOW INIT MAIL
mail = Mail(app)

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))

    otp = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    is_verified = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)

    full_name = db.Column(db.String(100))
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

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_url = db.Column(db.String(300))
    media_type = db.Column(db.String(10))  # image or video

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)

    name = db.Column(db.String(100))
    rating = db.Column(db.Integer)
    text = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))


# ---------------- HELPERS ----------------

def generate_otp():
    return str(random.randint(100000, 999999))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Login first", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_logged_in" not in session:
            flash("Admin login required", "danger")
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper


def get_user():
    if "user_id" in session:
        return db.session.get(User, session["user_id"])
    return None


@app.context_processor
def inject_user():
    return dict(current_user=get_user())

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    media = Media.query.all()
    reviews = Review.query.order_by(Review.id.desc()).all()

    return render_template("home.html", media=media, reviews=reviews)

# ---------------- SIGNUP ----------------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"].strip().lower()
        phone = request.form["phone"]
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "danger")
            return redirect("/signup")

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
        <p>Hello,</p>

        <p>Thank you for signing up.</p>

        <p><strong>Your OTP is:</strong></p>

        <h1 style="color:#d7ad4b;">{otp}</h1>

        <p>This OTP is valid for 5 minutes.</p>

        <p>If you didn’t request this, ignore this email.</p>
        """

        try:
            mail.send(msg)   # ✅ REAL EMAIL SEND
            flash("OTP sent to your email successfully", "success")
        except Exception as e:
            print(e)
            flash("Failed to send query", "danger")

        flash("OTP sent to your email. Please verify.")
        return redirect(f"/verify_signup/{email}")

    return render_template("signup.html")

# ---------------- VERIFY ----------------

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

        # ✅ CREATE USER NOW (after verification)
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

# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid credentials", "danger")
            return redirect("/login")

        if not user.is_verified:
            flash("Verify your email first", "warning")
            return redirect("/login")

        session["user_id"] = user.id
        return redirect("/booking")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- FORGOT PASSWORD ----------------

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
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

        <p>Password reset requested.</p>

        <p>Your OTP is:</p>

        <h1 style="color:#d7ad4b;">{otp}</h1>

        <p>This OTP is valid for <b>5 minutes</b>.</p>
        """

        try:
            mail.send(msg)   # ✅ enable email sending
        except Exception as e:
            print("OTP:", otp)
            print("Error:", e)

        return redirect(f"/reset_password/{email}")

    return render_template("forgot_password.html")

# ---------------- RESET ----------------

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

        if user.otp_expiry < datetime.now(UTC):
            flash("OTP expired", "danger")
            return redirect("/forgot_password")

        user.set_password(password)
        db.session.commit()

        flash("Password updated")
        return redirect("/login")

    return render_template("reset_password.html")

# ---------------- BOOKING ----------------

@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():
    PACKAGES = {
        "Signature Moment": {
            "price": "₹4,799",
            "summary": "Perfect for a simple yet stylish delivery celebration.",
            "features": [
                "Celebration Cake",
                "Flower Setup",
                "Decorative Bow Styling",
                "Cinematic Reel Capture"
            ]
        },

        "Elite Experience": {
            "price": "₹13,999",
            "summary": "A grand upgrade with entry effects and celebration elements.",
            "features": [
                "Includes Signature Package",
                "Red Carpet Entry",
                "Fire Gun Effects",
                "Paper Blast Celebration",
                "Custom Name Board",
                "Cinematic Reel",
                "Gift Hamper"
            ]
        },

        "Legacy Arrival": {
            "price": "₹79,999",
            "summary": "Premium cinematic experience with luxury entry and drone coverage.",
            "features": [
                "Includes Elite Package",
                "Flash Entry Experience",
                "Drone Shoot Coverage",
                "Cinematic Reel",
                "Custom Decoration Setup",
                "Smoke Effects",
                "Fire Gun",
                "Paper Blast",
                "Photo Frame",
                "Premium Gift Hampers"
            ]
        },

        "Prestige VIP Experience": {
            "price": "₹1,79,000",
            "summary": "Ultimate luxury delivery with venue, hosting, and grand celebrations.",
            "features": [
                "Includes Legacy Package",
                "Open Ground / Farmhouse / Resort Venue",
                "Grand Royal Welcome",
                "Luxury Decoration Setup",
                "Dedicated Host Assistance",
                "Fun Games & Surprise Activities",
                "Firecracker Show",
                "Premium Cinematic Coverage",
                "Fully Customized Experience"
            ]
        }
    }

    if request.method == "POST":
        booking = Booking(
            user_id=session["user_id"],
            full_name=request.form["full_name"],
            phone=request.form["phone"],
            email=request.form["email"],
            showroom_name=request.form["showroom_name"],
            showroom_address=request.form["showroom_address"],
            delivery_location=request.form["delivery_location"],
            salesperson_name=request.form["salesperson_name"],
            salesperson_phone=request.form["salesperson_phone"],
            delivery_date=datetime.strptime(request.form["delivery_date"], "%Y-%m-%d").date(),
            delivery_time=datetime.strptime(request.form["delivery_time"], "%H:%M").time(),
            package_name=request.form["package_name"]
        )

        db.session.add(booking)
        db.session.commit()

        # 🔥 ADMIN EMAIL
        ADMIN_EMAIL = "official.wecapture@gmail.com"

        ADMIN_EMAIL = "official.wecapture@gmail.com"

        msg = Message(
            subject="🚗 New Booking Received - We Capture",
            recipients=[ADMIN_EMAIL]
        )

        msg.html = f"""
        <h2>New Booking Alert 🚗</h2>

        <p><strong>Customer Name:</strong> {booking.full_name}</p>
        <p><strong>Phone:</strong> {booking.phone}</p>
        <p><strong>Email:</strong> {booking.email}</p>

        <hr>

        <p><strong>Showroom Name:</strong> {booking.showroom_name}</p>
        <p><strong>Showroom Address:</strong> {booking.showroom_address}</p>
        <p><strong>Delivery Location:</strong> {booking.delivery_location}</p>

        <hr>

        <p><strong>Salesperson:</strong> {booking.salesperson_name}</p>
        <p><strong>Salesperson Phone:</strong> {booking.salesperson_phone}</p>

        <hr>

        <p><strong>Delivery Date:</strong> {booking.delivery_date}</p>
        <p><strong>Delivery Time:</strong> {booking.delivery_time}</p>

        <hr>

        <p><strong>Package:</strong> {booking.package_name}</p>

        <hr>
        <p style="font-size:12px;">We Capture System</p>
        """

        try:
            mail.send(msg)
            print("📩 Admin email sent")
        except Exception as e:
            print("⚠️ Admin email failed:", e)

        return redirect(f"/booking_success/{booking.id}")

    return render_template("booking.html", packages=PACKAGES)

# ---------------- SUCCESS ----------------

@app.route("/booking_success/<int:id>")
@login_required
def booking_success(id):
    booking = Booking.query.get_or_404(id)
    return render_template("booking_success.html", booking=booking)

# ---------------- MY BOOKINGS ----------------

@app.route("/my_bookings")
@login_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=session["user_id"]).all()
    return render_template("my_bookings.html", bookings=bookings)

# ---------------- PACKAGES ----------------

@app.route("/packages")
def packages_page():
    packages = {
        "Signature Moment": {
            "price": "₹4,799",
            "summary": "Perfect for a simple yet stylish delivery celebration.",
            "features": [
                "Celebration Cake",
                "Flower Setup",
                "Decorative Bow Styling",
                "Cinematic Reel Capture"
            ]
        },

        "Elite Experience": {
            "price": "₹13,999",
            "summary": "A grand upgrade with entry effects and celebration elements.",
            "features": [
                "Includes Signature Package",
                "Red Carpet Entry",
                "Fire Gun Effects",
                "Paper Blast Celebration",
                "Custom Name Board",
                "Cinematic Reel",
                "Gift Hamper"
            ]
        },

        "Legacy Arrival": {
            "price": "₹79,999",
            "summary": "Premium cinematic experience with luxury entry and drone coverage.",
            "features": [
                "Includes Elite Package",
                "Flash Entry Experience",
                "Drone Shoot Coverage",
                "Cinematic Reel",
                "Custom Decoration Setup",
                "Smoke Effects",
                "Fire Gun",
                "Paper Blast",
                "Photo Frame",
                "Premium Gift Hampers"
            ]
        },

        "Prestige VIP Experience": {
            "price": "₹1,79,000",
            "summary": "Ultimate luxury delivery with venue, hosting, and grand celebrations.",
            "features": [
                "Includes Legacy Package",
                "Open Ground / Farmhouse / Resort Venue",
                "Grand Royal Welcome",
                "Luxury Decoration Setup",
                "Dedicated Host Assistance",
                "Fun Games & Surprise Activities",
                "Firecracker Show",
                "Premium Cinematic Coverage",
                "Fully Customized Experience"
            ]
        }
    }

    return render_template("packages.html", packages=packages)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        ADMIN_EMAIL = "official.wecapture@gmail.com"
        ADMIN_PASSWORD = "wecapture@2627"

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Admin logged in successfully")
            return redirect("/admin")

        flash("Invalid admin credentials", "danger")

    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin_dashboard():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    media = Media.query.all()
    return render_template("admin_dashboard.html", bookings=bookings, media=media)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out")
    return redirect("/admin/login")


@app.route("/admin/update_status/<int:id>/<status>")
@admin_required
def update_status(id, status):
    booking = Booking.query.get_or_404(id)

    booking.status = status
    db.session.commit()

    # 🔥 SEND EMAIL TO USER
    msg = Message(
        subject=f"We Capture - Booking {status}",
        recipients=[booking.email]
    )

    if status == "Confirmed":
        msg.html = f"""
        <h2>Booking Confirmed ✅</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking has been <b>confirmed</b>.</p>
        <p>Delivery Date: {booking.delivery_date}</p>
        <p>Time: {booking.delivery_time}</p>
        """

    elif status == "Completed":
        msg.html = f"""
        <h2>Service Completed 🚚</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your delivery service has been completed successfully.</p>
        """

    elif status == "Cancelled":
        msg.html = f"""
        <h2>Booking Cancelled ❌</h2>
        <p>Hello {booking.full_name},</p>
        <p>Your booking has been cancelled.</p>
        """

    try:
        mail.send(msg)
        print("📩 Status email sent")
    except Exception as e:
        print("⚠️ Email failed:", e)

    flash("Status updated")
    return redirect("/admin")



@app.route("/send_query", methods=["POST"])
def send_query():
    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    location = request.form["location"]
    message = request.form["message"]

    ADMIN_EMAIL = "official.wecapture@gmail.com"

    msg = Message(
        subject="New Query - We Capture",
        recipients=[ADMIN_EMAIL]
    )

    msg.html = f"""
    <div style="font-family: Arial, sans-serif; background:#0f0f0f; padding:20px; color:white;">

        <div style="max-width:600px; margin:auto; background:#111; border-radius:12px; overflow:hidden; border:1px solid #2a2a2a;">

            <!-- HEADER -->
            <div style="text-align:center; padding:25px 20px; border-bottom:1px solid #2a2a2a;">
                <img src="https://res.cloudinary.com/dqs9wfgu1/image/upload/f_auto,q_auto/logo_yyzvej" 
                    alt="We Capture" 
                    style="height:55px; margin-bottom:10px;">
                
                <h2 style="color:#d7ad4b; margin:0;">We Capture 🎥</h2>
                <p style="color:#aaa; font-size:14px; margin-top:5px;">New Customer Query</p>
            </div>

            <!-- BODY -->
            <div style="padding:25px;">

                <p style="margin:10px 0;"><strong>👤 Name:</strong> {name}</p>
                <p style="margin:10px 0;"><strong>📧 Email:</strong> {email}</p>
                <p style="margin:10px 0;"><strong>📱 Phone:</strong> {phone}</p>
                <p style="margin:10px 0;"><strong>📍 Location:</strong> {location}</p>

                <hr style="border:0; border-top:1px solid #2a2a2a; margin:20px 0;">

                <p style="margin-bottom:10px;"><strong>📝 Message:</strong></p>

                <div style="background:#1a1a1a; padding:15px; border-radius:10px; color:#ddd; line-height:1.5;">
                    {message}
                </div>

            </div>

            <!-- FOOTER -->
            <div style="text-align:center; padding:15px; border-top:1px solid #2a2a2a; font-size:12px; color:#888;">
                🚗✨ We Capture — Cinematic Delivery Experiences<br>
                <span style="font-size:11px;">This is an automated notification</span>
            </div>

        </div>

    </div>
    """

    try:
        mail.send(msg)
        flash("OTP sent to your email successfully", "success")
    except Exception as e:  
        print("EMAIL ERROR:", e)
        flash("Failed to send OTP email", "danger")

    return redirect("/")



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

            flash("Media uploaded successfully!", "success")

        return redirect("/admin/upload_media")

    return render_template("upload_media.html")


@app.route("/admin/delete_media/<int:id>")
@admin_required
def delete_media(id):
    media = Media.query.get_or_404(id)

    # delete file from folder
    try:
        file_path = media.file_url.replace("/", "\\")
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass

    db.session.delete(media)
    db.session.commit()

    flash("Media deleted", "success")
    return redirect("/admin")


@app.route("/add_review", methods=["POST"])
@login_required
def add_review():
    user = get_user()

    rating = int(request.form.get("rating", 0))
    print("⭐ RECEIVED RATING:", rating)
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

    if review.user_id == user.id or "admin_logged_in" in session:
        db.session.delete(review)
        db.session.commit()
        flash("Review deleted", "success")
    else:
        flash("Not allowed", "danger")

    return redirect("/")
# ---------------- RUN ----------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()
