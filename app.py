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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'hash-grill-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hash_grill.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Admin Access Decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

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
        password = request.form.get('password')
        user = User.query.filter_by(phone_number=phone).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login Unsuccessful. Check phone number and password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone_number')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        try:
            user = User(name=name, phone_number=phone, password=hashed_password, role='customer')
            db.session.add(user)
            db.session.flush()
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
        receipt_number = request.form.get('receipt_number')
        code = request.form.get('secure_code').upper()
        tx = Transaction.query.filter_by(receipt_number=receipt_number, customer_id=1).first()
        if not tx:
            flash('Receipt not found or already claimed.', 'danger')
        else:
            pos_secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
            if code == generate_receipt_code(receipt_number, tx.amount, pos_secret):
                tx.customer_id = current_user.id
                current_user.profile.total_points += tx.points_earned
                if tx.amount >= 2500:
                    current_user.profile.qualifying_visits += 1
                db.session.commit()
                flash(f'Success! {tx.points_earned} points added.', 'success')
                return redirect(url_for('customer_dashboard'))
            flash('Invalid secure code.', 'danger')
    return render_template('claim_points.html')

@app.route('/customer/redeem/<int:reward_id>', methods=['POST'])
@login_required
def redeem_reward(reward_id):
    reward = Reward.query.get_or_404(reward_id)
    if current_user.profile.total_points < reward.point_cost:
        flash('Not enough points.', 'danger')
    else:
        current_user.profile.total_points -= reward.point_cost
        db.session.add(Transaction(customer_id=current_user.id, amount=0, points_redeemed=reward.point_cost, receipt_number=f"RED-{reward.id}-{int(datetime.now().timestamp())}", transaction_type='redeem'))
        db.session.commit()
        flash(f'Success! Redeemed {reward.name}.', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/customer/redeem_cash', methods=['POST'])
@login_required
def redeem_cash():
    profile = current_user.profile
    pts = (profile.total_points // 10) * 10
    if pts < 10:
        flash('Minimum 10 points required.', 'warning')
    else:
        val = (pts // 10) * 50
        profile.total_points -= pts
        db.session.add(Transaction(customer_id=current_user.id, amount=0, points_redeemed=pts, receipt_number=f"CASH-{int(datetime.now().timestamp())}", transaction_type='redeem_cash'))
        db.session.commit()
        flash(f'Success! Redeemed KES {val} discount.', 'success')
    return redirect(url_for('customer_dashboard'))

# --- ADMIN ROUTES ---

@app.route('/admin/dashboard')
@admin_required
@login_required
def admin_dashboard():
    rewards = Reward.query.all()
    txs = Transaction.query.order_by(Transaction.timestamp.desc()).limit(50).all()
    count = User.query.filter_by(role='customer').count()
    pos_secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
    sample = generate_receipt_code("REC-SAMPLE", 2500, pos_secret)
    return render_template('admin_dashboard.html', rewards=rewards, transactions=txs, total_customers=count, sample_code=sample)

@app.route('/admin/add_reward', methods=['POST'])
@admin_required
@login_required
def add_reward():
    db.session.add(Reward(name=request.form.get('name'), description=request.form.get('description'), point_cost=int(request.form.get('point_cost'))))
    db.session.commit()
    flash('Reward added.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/redeem_free_meal', methods=['POST'])
@admin_required
@login_required
def admin_redeem_free_meal():
    phone = request.form.get('phone_number')
    user = User.query.filter_by(phone_number=phone, role='customer').first()
    if user and user.profile.qualifying_visits >= 10:
        user.profile.qualifying_visits -= 10
        db.session.add(Transaction(customer_id=user.id, amount=0, transaction_type='free_meal', receipt_number=f"FREE-{int(datetime.now().timestamp())}"))
        db.session.commit()
        flash(f'Free meal redeemed for {user.name}!', 'success')
    else:
        flash('Customer not found or not eligible.', 'danger')
    return redirect(url_for('admin_dashboard'))

# --- API ---

@app.route('/api/pos/sync', methods=['POST'])
@csrf.exempt
def pos_sync():
    data = request.json
    sig = request.headers.get('X-POS-Signature')
    if not SignatureManager().verify_signature(data, sig):
        return {"error": "Unauthorized"}, 401

    for t in data.get('transactions', []):
        if not Transaction.query.filter_by(receipt_number=t['receipt_number']).first():
            pts = t['amount'] / 1000.0
            cid = 1
            user = User.query.filter_by(phone_number=t.get('phone_number')).first()
            if user:
                cid = user.id
                user.profile.total_points += pts
                if t['amount'] >= 2500: user.profile.qualifying_visits += 1
            db.session.add(Transaction(customer_id=cid, amount=t['amount'], points_earned=pts, receipt_number=t['receipt_number'], transaction_type='pos_sync'))
    db.session.commit()
    return {"status": "ok"}, 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='admin').first():
            db.session.add(User(name='Admin', phone_number='0700000000', password=bcrypt.generate_password_hash('admin123').decode('utf-8'), role='admin'))
            db.session.commit()
    app.run(debug=True, port=5000)
