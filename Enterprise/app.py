from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_mail import Mail, Message
import smtplib
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart  
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline
import openai
import logging
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
OPENAI_API_KEY="your_key"
openai.api_key = os.getenv("OPENAI_API_KEY")



app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)



class JobApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    resume_filename = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default="Pending")
    interview_datetime = db.column(db.Column(db.String(50), nullable=True))


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'yourmail@gmail.com'   # your company email
app.config['MAIL_PASSWORD'] = 'password'             # Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = ('Eminent Enterprise HR Team', 'eminent0267@gmail.com')

mail = Mail(app)


# ========== UPLOAD CONFIG ==========
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ========== ROUTES ==========

@app.route('/')
def home():
    return render_template('index.html', title="Home")

@app.route('/careers')
def careers():
    jobs = [
        {"id": 1, "title": "Software Engineer", "desc": "Develop and maintain Python-based applications."},
        {"id": 2, "title": "Marketing Executive", "desc": "Handle campaigns and promotions effectively."},
        {"id": 3, "title": "HR Manager", "desc": "Manage recruitment and employee engagement."}
    ]
    return render_template('careers.html', jobs=jobs, title="Careers")

@app.route('/contact')
def contact():
    return render_template('contact.html', title="Contact Us")

@app.route('/apply/<int:job_id>', methods=['GET', 'POST'])
def apply(job_id):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        resume = request.files['resume']

        if not resume:
            flash("⚠ Please upload your resume.", "warning")
            return redirect(request.url)

        filename = secure_filename(resume.filename)
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        resume.save(resume_path)

        # 1️⃣ Save to Database
        new_application = JobApplication(
            job_id=job_id,
            name=name,
            email=email,
            phone=phone,
            resume_filename=filename
        )
        db.session.add(new_application)
        db.session.commit()

        # 2️⃣ Send Email to Host
        msg = Message(subject=f"New Application - {name}",
                      recipients=['hostemail@example.com'])
        msg.body = f"Name: {name}\nEmail: {email}\nPhone: {phone}\nApplied for Job ID: {job_id}"
        with open(resume_path, 'rb') as fp:
            msg.attach(filename, "application/octet-stream", fp.read())
        mail.send(msg)

        # 3️⃣ Send Auto Reply
        auto_reply = Message(subject="Job Application Received",
                             recipients=[email])
        auto_reply.body = f"Dear {name},\n\nThank you for applying to our company. We're following up on your application for Job ID: {job_id}.\n\nWe want to thank you for your interest in a position at Eminent Enterprise. We're looking forward to reviewing your Application,and will contact you soon if your skills matches our requirements. \n\nHave a great day!\nEminent Enterprise HR Team"
        mail.send(auto_reply)

        flash("✅ Application submitted successfully! Confirmation email sent.", "success")
        return redirect(url_for('careers'))

    return render_template('apply.html', job_id=job_id, title="Apply")



@app.route('/services')
def services():
    return render_template('services.html')

#  ========= Admin Route ==========

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin@123':  # Simple auth for demo
            session['admin_logged_in'] = True
            flash("✅ Logged in successfully. \n Welcome Admin", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("❌ Invalid credentials. Try again.", "danger")
    return render_template('admin_login.html', title="Admin Login") 



@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash("Please login first!", "warning")
        return redirect(url_for('admin_login'))

    # ====== SEARCH / FILTER ======
    query = JobApplication.query
    search = request.args.get('search')

    if search:
        query = query.filter(
            (JobApplication.name.ilike(f"%{search}%")) |
            (JobApplication.email.ilike(f"%{search}%")) |
            (JobApplication.job_id.ilike(f"%{search}%"))
        )

    applications = query.all()

    # ====== ANALYTICS ======
    total = JobApplication.query.count()
    accepted = JobApplication.query.filter_by(status='Accepted').count()
    rejected = JobApplication.query.filter_by(status='Rejected').count()
    pending = JobApplication.query.filter_by(status='Pending').count()

    return render_template(
        'admin_dashboard.html',
        applications=applications,
        total=total,
        accepted=accepted,
        rejected=rejected,
        pending=pending,
        search=search or ""
    )

@app.route('/admin/update_status/<int:app_id>/<string:action>', methods=['GET', 'POST'])
def update_status(app_id, action):
    if not session.get('admin_logged_in'):
        flash("Please login first!", "warning")
        return redirect(url_for('admin_login'))

    application = JobApplication.query.get_or_404(app_id)

    if action == 'accept':
        if request.method == 'POST':
            interview_date = request.form['interview_date']
            interview_time = request.form['interview_time']
            datetime_str = f"{interview_date} at {interview_time}"

            application.status = "Accepted"
            application.interview_datetime = datetime_str
            db.session.commit()

            msg = Message(subject="Application Update - Congratulations!",
                          recipients=[application.email])
            msg.body = f"""
            Dear {application.name},

            Congratulations! 🎉

            You have been selected for the next round of interviews at Our Company.
            Your interview is scheduled for {datetime_str}.

            Regards,
            Eminent Enterprise
            HR Team
            """
            mail.send(msg)
            flash(f"{application.name} accepted and interview scheduled.", "success")
            return redirect(url_for('admin_dashboard'))

        return render_template('schedule_interview.html', app=application)

    elif action == 'reject':
        application.status = "Rejected"
        db.session.commit()

        msg = Message(subject="Application Update",
                      recipients=[application.email])
        msg.body = f"""
        Dear {application.name},

        Thank you for your interest in Our Company.

        After careful consideration, we regret to inform you that your application has not been selected for the next stage.
        We wish you all the best in your future endeavors.

        Regards,
        Eminent Enterprise
        HR Team
        """
        mail.send(msg)
        flash(f"{application.name} has been rejected and notified via email.", "info")

    return redirect(url_for('admin_dashboard'))




@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("✅ Logged out successfully.", "info")
    return redirect(url_for('home'))




@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)




# ------------------ Routes ------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/chatbot', methods=['POST'])
def chatbot():
    user_message = request.json.get('message', '').lower()
    
    if "career" in user_message or "job" in user_message:
        reply = 'You can explore our career opportunities <a href="/careers" target="_blank" style="color:#0d6efd; text-decoration: underline;">here</a>.'
    elif "service" in user_message or "offer" in user_message:
        reply = 'We provide a wide range of services! Check them out <a href="/services" target="_blank" style="color:#0d6efd; text-decoration: underline;">here</a>.'
    elif "contact" in user_message:
        reply = 'You can reach us via our <a href="/contact" target="_blank" style="color:#0d6efd; text-decoration: underline;">Contact page</a>.'
    elif "home" in user_message:
        reply = 'Return to our <a href="/" target="_blank" style="color:#0d6efd; text-decoration: underline;">Home page</a>.'
    else:
        reply = "I'm here to help! You can ask me questions about Eminent Enterprise website, please specify your query."

    return jsonify({"reply": reply})




# ========== INIT DATABASE ==========
with app.app_context():
    db.create_all()

if __name__ == "__main__":

    app.run(debug=True)
