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

# --- PRESENTATION MODE: FORCED LOCAL DATABASE ---
# This line ensures we NEVER try to connect to the internet (Supabase/Postgres)
# during your presentation. It uses the file 'hash_grill.db' on your computer.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hash_grill.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'hash-grill-secure-key-123')
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
@app.before_request
def create_tables():
    db.create_all()
    if not User.query.filter_by(role='admin').first():
        hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(name='Admin', phone_number='0700000000', password=hashed_pw, role='admin')
        db.session.add(admin)
        db.session.commit()

# --- ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('customer_dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        phone = request.form.get('phone_number')
        user = User.query.filter_by(phone_number=phone).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login failed.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        hashed_password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        try:
            user = User(name=request.form.get('name'), phone_number=request.form.get('phone_number'), password=hashed_password, role='customer')
            db.session.add(user); db.session.flush()
            db.session.add(LoyaltyProfile(user_id=user.id))
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            flash('Phone number already registered.', 'danger')
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- CUSTOMER ROUTES ---

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = current_user.profile
    transactions = Transaction.query.filter_by(customer_id=current_user.id).order_by(Transaction.timestamp.desc()).limit(10).all()
    cash_value = (profile.total_points // 10) * 50
    recommendations = Reward.query.filter(Reward.point_cost <= profile.total_points).all()
    return render_template('customer_dashboard.html', profile=profile, transactions=transactions, recommendations=recommendations, cash_value=cash_value)

@app.route('/customer/claim_points', methods=['GET', 'POST'])
@login_required
def claim_points():
    if request.method == 'POST':
        r_num = request.form.get('receipt_number'); code = request.form.get('secure_code').upper()
        # Find unclaimed receipt
        tx = Transaction.query.filter_by(receipt_number=r_num, customer_id=1).first()
        if tx:
            pos_secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
            if code == generate_receipt_code(r_num, tx.amount, pos_secret):
                tx.customer_id = current_user.id
                current_user.profile.total_points += tx.points_earned
                if tx.amount >= 2500: current_user.profile.qualifying_visits += 1
                db.session.commit()
                flash('Points added!', 'success')
                return redirect(url_for('customer_dashboard'))
        flash('Invalid code or receipt.', 'danger')
    return render_template('claim_points.html')

@app.route('/customer/redeem_cash', methods=['POST'])
@login_required
def redeem_cash():
    profile = current_user.profile; pts = (profile.total_points // 10) * 10
    if pts >= 10:
        val = (pts // 10) * 50
        profile.total_points -= pts
        db.session.add(Transaction(customer_id=current_user.id, amount=0, points_redeemed=pts, receipt_number=f"CASH-{int(datetime.now().timestamp())}", transaction_type='redeem_cash'))
        db.session.commit()
        flash(f'Success! Redeemed KES {val} discount.', 'success')
    else: flash('Min 10 points required.', 'warning')
    return redirect(url_for('customer_dashboard'))

# --- ADMIN ROUTES ---

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
    phone = request.form.get('phone_number'); user = User.query.filter_by(phone_number=phone, role='customer').first()
    if user and user.profile.qualifying_visits >= 10:
        user.profile.qualifying_visits -= 10
        db.session.add(Transaction(customer_id=user.id, amount=0, transaction_type='free_meal', receipt_number=f"FREE-{int(datetime.now().timestamp())}"))
        db.session.commit()
        flash(f'Free meal redeemed for {user.name}!', 'success')
    else: flash('Not eligible or not found.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_reward', methods=['POST'])
@admin_required
@login_required
def add_reward():
    db.session.add(Reward(name=request.form.get('name'), description=request.form.get('description'), point_cost=int(request.form.get('point_cost'))))
    db.session.commit()
    flash('Reward added.', 'success')
    return redirect(url_for('admin_dashboard'))

# --- API ---

@app.route('/api/pos/sync', methods=['POST'])
@csrf.exempt
def pos_sync():
    data = request.json; sig = request.headers.get('X-POS-Signature')
    if not SignatureManager().verify_signature(data, sig): return {"error": "Unauthorized"}, 401
    for t in data.get('transactions', []):
        if not Transaction.query.filter_by(receipt_number=t['receipt_number']).first():
            pts = t['amount'] / 1000.0; cid = 1; user = User.query.filter_by(phone_number=t.get('phone_number')).first()
            if user:
                cid = user.id; user.profile.total_points += pts
                if t['amount'] >= 2500: user.profile.qualifying_visits += 1
            db.session.add(Transaction(customer_id=cid, amount=t['amount'], points_earned=pts, receipt_number=t['receipt_number'], transaction_type='pos_sync'))
    db.session.commit(); return {"status": "ok"}, 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
