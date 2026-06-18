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
import json

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-replace-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hash_grill.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Decorators for role-based access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('customer_dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')
        user = User.query.filter_by(phone_number=phone_number).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check phone number and password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        try:
            user = User(name=name, phone_number=phone_number, password=hashed_password, role='customer')
            db.session.add(user)
            db.session.flush()

            profile = LoyaltyProfile(user_id=user.id)
            db.session.add(profile)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Phone number already registered.', 'danger')
            return redirect(url_for('register'))

        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('index'))

    profile = current_user.profile
    transactions = Transaction.query.filter_by(customer_id=current_user.id).order_by(Transaction.timestamp.desc()).limit(10).all()

    # 10 points = 50 KES
    cash_value = (profile.total_points // 10) * 50

    recommended_rewards = Reward.query.filter(Reward.point_cost <= profile.total_points).all()

    return render_template('customer_dashboard.html',
                           profile=profile,
                           transactions=transactions,
                           recommendations=recommended_rewards,
                           cash_value=cash_value)

@app.route('/customer/redeem/<int:reward_id>', methods=['POST'])
@login_required
def redeem_reward(reward_id):
    if current_user.role != 'customer':
        abort(403)

    reward = Reward.query.get_or_404(reward_id)
    profile = current_user.profile

    if profile.total_points < reward.point_cost:
        flash('Not enough points.', 'danger')
        return redirect(url_for('customer_dashboard'))

    profile.total_points -= reward.point_cost

    transaction = Transaction(
        customer_id=current_user.id,
        waiter_id=1,
        amount=0,
        points_earned=0,
        points_redeemed=reward.point_cost,
        receipt_number=f"REDEEM-{reward.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        transaction_type='redeem'
    )

    db.session.add(transaction)
    db.session.commit()

    flash(f'Success! Redeemed {reward.name}.', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/customer/redeem_cash', methods=['POST'])
@login_required
def redeem_cash():
    profile = current_user.profile
    points_to_redeem = (profile.total_points // 10) * 10
    if points_to_redeem < 10:
        flash('Minimum 10 points required for cash redemption.', 'warning')
        return redirect(url_for('customer_dashboard'))

    cash_value = (points_to_redeem // 10) * 50
    profile.total_points -= points_to_redeem

    transaction = Transaction(
        customer_id=current_user.id,
        waiter_id=1,
        amount=0,
        points_earned=0,
        points_redeemed=points_to_redeem,
        receipt_number=f"CASH-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        transaction_type='redeem_cash'
    )
    db.session.add(transaction)
    db.session.commit()

    flash(f'Success! You have redeemed {points_to_redeem} points for KES {cash_value} discount. Show this to the cashier.', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/admin/dashboard')
@admin_required
@login_required
def admin_dashboard():
    rewards = Reward.query.all()
    transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(50).all()
    total_customers = User.query.filter_by(role='customer').count()

    pos_secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
    sample_code = generate_receipt_code("REC-SAMPLE", 2500, pos_secret)

    return render_template('admin_dashboard.html', rewards=rewards, transactions=transactions, total_customers=total_customers, sample_code=sample_code)

@app.route('/customer/claim_points', methods=['GET', 'POST'])
@login_required
def claim_points():
    if request.method == 'POST':
        receipt_number = request.form.get('receipt_number')
        claimed_code = request.form.get('secure_code').upper()

        tx = Transaction.query.filter_by(receipt_number=receipt_number, customer_id=1).first()

        if not tx:
            flash('Receipt not found or already claimed.', 'danger')
            return redirect(url_for('claim_points'))

        pos_secret = os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
        expected_code = generate_receipt_code(receipt_number, tx.amount, pos_secret)

        if claimed_code != expected_code:
            flash('Invalid secure code.', 'danger')
            return redirect(url_for('claim_points'))

        tx.customer_id = current_user.id
        current_user.profile.total_points += tx.points_earned
        if tx.amount >= 2500:
            current_user.profile.qualifying_visits += 1

        db.session.commit()
        flash(f'Success! {tx.points_earned} points added.', 'success')
        return redirect(url_for('customer_dashboard'))

    return render_template('claim_points.html')

@app.route('/api/pos/sync', methods=['POST'])
@csrf.exempt
def pos_sync():
    data = request.json
    signature = request.headers.get('X-POS-Signature')

    if not signature:
        return {"error": "Missing signature"}, 401

    sig_manager = SignatureManager()
    if not sig_manager.verify_signature(data, signature):
        return {"error": "Invalid signature"}, 401

    results = {"processed": 0, "errors": []}
    transactions = data.get('transactions', [])

    for tx_data in transactions:
        receipt_num = tx_data.get('receipt_number')
        amount = tx_data.get('amount')
        phone = tx_data.get('phone_number')

        existing = Transaction.query.filter_by(receipt_number=receipt_num).first()
        if existing:
            continue

        # 1 point per 1000 KES
        points_earned = amount / 1000.0

        customer_id = 1
        if phone:
            customer = User.query.filter_by(phone_number=phone, role='customer').first()
            if customer:
                customer_id = customer.id
                customer.profile.total_points += points_earned
                # Free meal on 10th visit of 2500+ KES
                if amount >= 2500:
                    customer.profile.qualifying_visits += 1

        new_tx = Transaction(
            customer_id=customer_id,
            waiter_id=1,
            amount=amount,
            points_earned=points_earned,
            receipt_number=receipt_num,
            transaction_type='pos_sync'
        )
        db.session.add(new_tx)
        results['processed'] += 1

    db.session.commit()
    return results, 200

@app.route('/admin/add_reward', methods=['POST'])
@admin_required
@login_required
def add_reward():
    name = request.form.get('name')
    description = request.form.get('description')
    point_cost = int(request.form.get('point_cost'))

    reward = Reward(name=name, description=description, point_cost=point_cost)
    db.session.add(reward)
    db.session.commit()

    flash(f'Reward {name} added.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/redeem_free_meal', methods=['POST'])
@admin_required
@login_required
def admin_redeem_free_meal():
    phone_number = request.form.get('phone_number')
    customer = User.query.filter_by(phone_number=phone_number, role='customer').first()

    if not customer:
        flash('Customer not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if customer.profile.qualifying_visits < 10:
        flash('Not enough qualifying visits.', 'warning')
        return redirect(url_for('admin_dashboard'))

    customer.profile.qualifying_visits -= 10

    transaction = Transaction(
        customer_id=customer.id,
        waiter_id=current_user.id,
        amount=0,
        points_earned=0,
        points_redeemed=0,
        receipt_number=f"FREE-MEAL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        transaction_type='redeem_free_meal'
    )

    db.session.add(transaction)
    db.session.commit()

    flash(f'Free meal redeemed for {customer.name}!', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(name='Admin', phone_number='0700000000', password=hashed_pw, role='admin')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, port=5000)
