import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from models import db, User, LoyaltyProfile, Transaction, Reward
from functools import wraps
from utils import SignatureManager, generate_receipt_code

load_dotenv()
app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # 1. SQLAlchemy requires 'postgresql://' instead of 'postgres://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # 2. Add SSL mode for Supabase/Neon
    if "?" not in database_url:
        database_url += "?sslmode=require"

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

    # 3. Connection Pooling for Vercel/Serverless
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hash_grill.db'

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'hash-grill-secure-789')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- INITIALIZATION ---
def init_db():
    with app.app_context():
        db.create_all()
        # 1. Create System/Admin User (ID 1)
        system = db.session.get(User, 1)
        if not system:
            pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            system = User(id=1, name='Admin', phone_number='0700000000', password=pw, role='admin')
            db.session.add(system)
            db.session.commit()
            db.session.add(LoyaltyProfile(user_id=1))
            db.session.commit()

# Ensure tables are ready
try:
    init_db()
except Exception as e:
    print(f"Postgres Sync Issue: {e}")

# --- ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard' if current_user.role == 'admin' else 'customer_dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone_number')
        user = User.query.filter_by(phone_number=phone).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user); return redirect(url_for('index'))
        flash('Login failed. Check credentials.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        try:
            user = User(name=request.form.get('name'), phone_number=request.form.get('phone_number'), password=hashed)
            db.session.add(user); db.session.flush()
            db.session.add(LoyaltyProfile(user_id=user.id))
            db.session.commit(); flash('Success! Login now.', 'success'); return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback(); flash('Phone number exists.', 'danger')
    return render_template('register.html')

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    # Safety ensure profile exists
    if not current_user.profile:
        db.session.add(LoyaltyProfile(user_id=current_user.id))
        db.session.commit()

    profile = current_user.profile
    points = profile.total_points or 0
    cash_val = (int(points) // 10) * 50
    txs = Transaction.query.filter_by(customer_id=current_user.id).order_by(Transaction.timestamp.desc()).limit(10).all()
    recs = Reward.query.filter(Reward.point_cost <= points).all()
    return render_template('customer_dashboard.html', profile=profile, transactions=txs, recommendations=recs, cash_value=cash_val)

@app.route('/customer/claim_points', methods=['GET', 'POST'])
@login_required
def claim_points():
    if request.method == 'POST':
        r_num = request.form.get('receipt_number'); code = request.form.get('secure_code').upper()
        # ID 1 is the system/admin bucket
        tx = Transaction.query.filter_by(receipt_number=r_num, customer_id=1).first()
        if tx:
            secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
            if code == generate_receipt_code(r_num, tx.amount, secret):
                tx.customer_id = current_user.id
                current_user.profile.total_points = (current_user.profile.total_points or 0) + tx.points_earned
                if tx.amount >= 2500: current_user.profile.qualifying_visits += 1
                db.session.commit(); flash('Points added!', 'success'); return redirect(url_for('customer_dashboard'))
        flash('Invalid code or receipt.', 'danger')
    return render_template('claim_points.html')

@app.route('/customer/redeem_cash', methods=['POST'])
@login_required
def redeem_cash():
    profile = current_user.profile
    pts = (int(profile.total_points or 0) // 10) * 10
    if pts >= 10:
        profile.total_points -= pts
        db.session.add(Transaction(customer_id=current_user.id, amount=0, points_redeemed=pts, receipt_number=f"CASH-{int(datetime.now().timestamp())}", transaction_type='redeem_cash'))
        db.session.commit(); flash('Discount redeemed!', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/admin/dashboard')
@admin_required
@login_required
def admin_dashboard():
    txs = Transaction.query.order_by(Transaction.timestamp.desc()).limit(50).all()
    count = User.query.filter_by(role='customer').count()
    return render_template('admin_dashboard.html', transactions=txs, total_customers=count)

@app.route('/admin/redeem_free_meal', methods=['POST'])
@admin_required
@login_required
def admin_redeem_free_meal():
    phone = request.form.get('phone_number')
    user = User.query.filter_by(phone_number=phone).first()
    if user and user.profile and user.profile.qualifying_visits >= 10:
        user.profile.qualifying_visits -= 10
        db.session.add(Transaction(customer_id=user.id, amount=0, transaction_type='free_meal', receipt_number=f"FREE-{int(datetime.now().timestamp())}"))
        db.session.commit(); flash('Success!', 'success')
    else: flash('Not eligible.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/pos/sync', methods=['POST'])
@csrf.exempt
def pos_sync():
    data = request.json; sig = request.headers.get('X-POS-Signature')
    if not SignatureManager().verify_signature(data, sig): return {"error": "Unauthorized"}, 401
    for t in data.get('transactions', []):
        if not Transaction.query.filter_by(receipt_number=t['receipt_number']).first():
            pts = t['amount'] / 1000.0; cid = 1
            user = User.query.filter_by(phone_number=t.get('phone_number')).first()
            if user:
                cid = user.id
                user.profile.total_points = (user.profile.total_points or 0) + pts
                if t['amount'] >= 2500: user.profile.qualifying_visits += 1
            db.session.add(Transaction(customer_id=cid, amount=t['amount'], points_earned=pts, receipt_number=t['receipt_number'], transaction_type='pos_sync'))
    db.session.commit(); return {"status": "ok"}, 200

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
