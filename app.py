import os
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from models import db, User, LoyaltyProfile, Transaction, Reward
from functools import wraps

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
    return User.query.get(int(user_id))

# Decorators for role-based access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def waiter_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['waiter', 'admin']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'waiter':
            return redirect(url_for('waiter_dashboard'))
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
            db.session.flush() # Get user id without committing

            # Create loyalty profile
            profile = LoyaltyProfile(user_id=user.id)
            db.session.add(profile)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Phone number already registered. Please login or use another number.', 'danger')
            return redirect(url_for('register'))

        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# Dashboard Routes (Placeholders)
@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('index'))

    profile = current_user.profile
    transactions = Transaction.query.filter_by(customer_id=current_user.id).order_by(Transaction.timestamp.desc()).limit(10).all()

    # Recommendations logic:
    # 1 point = 1 KES worth of value (similar to Bonga points where 10 points ~ 2 KES, or supermarkets)
    # Let's say 1 point = 1 KES for simplicity in redemption too.
    # We will fetch available rewards that the user can afford.
    recommended_rewards = Reward.query.filter(Reward.point_cost <= profile.total_points).all()

    return render_template('customer_dashboard.html', profile=profile, transactions=transactions, recommendations=recommended_rewards)

@app.route('/customer/redeem/<int:reward_id>', methods=['POST'])
@login_required
def redeem_reward(reward_id):
    if current_user.role != 'customer':
        abort(403)

    reward = Reward.query.get_or_404(reward_id)
    profile = current_user.profile

    if profile.total_points < reward.point_cost:
        flash('Not enough points to redeem this reward.', 'danger')
        return redirect(url_for('customer_dashboard'))

    # Process redemption
    profile.total_points -= reward.point_cost

    # Record transaction
    transaction = Transaction(
        customer_id=current_user.id,
            waiter_id=1, # Default to admin or system if customer initiates
        amount=0,
        points_earned=0,
        points_redeemed=reward.point_cost,
        receipt_number=f"REDEEM-{reward.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        transaction_type='redeem'
    )

    db.session.add(transaction)
    db.session.commit()

    flash(f'Success! You have redeemed {reward.name}. Show this message to the waiter to claim.', 'success')
    return redirect(url_for('customer_dashboard'))

@app.route('/waiter/dashboard', methods=['GET', 'POST'])
@waiter_required
@login_required
def waiter_dashboard():
    if request.method == 'POST':
        phone_number = request.form.get('phone_number')
        try:
            amount = float(request.form.get('amount'))
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash('Invalid amount. Please enter a positive number.', 'danger')
            return redirect(url_for('waiter_dashboard'))

        receipt_number = request.form.get('receipt_number')

        customer = User.query.filter_by(phone_number=phone_number, role='customer').first()
        if not customer:
            flash(f'Customer with phone {phone_number} not found.', 'danger')
            return redirect(url_for('waiter_dashboard'))

        # Calculate points: 1 point per 100 KES
        points_earned = amount / 100.0

        # Check if visit qualifies for free meal counter (>= 2000 KES)
        if amount >= 2000:
            customer.profile.qualifying_visits += 1
            if customer.profile.qualifying_visits >= 10:
                flash(f'CONGRATULATIONS! {customer.name} has reached 10 visits. They have earned a FREE MEAL!', 'success')

        customer.profile.total_points += points_earned

        transaction = Transaction(
            customer_id=customer.id,
            waiter_id=current_user.id,
            amount=amount,
            points_earned=points_earned,
            receipt_number=receipt_number,
            transaction_type='earn'
        )

        db.session.add(transaction)
        db.session.commit()

        flash(f'Success! {points_earned} points added to {customer.name}.', 'success')
        return redirect(url_for('waiter_dashboard'))

    return render_template('waiter_dashboard.html')

@app.route('/admin/dashboard')
@admin_required
@login_required
def admin_dashboard():
    waiters = User.query.filter_by(role='waiter').all()
    rewards = Reward.query.all()
    transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(20).all()
    total_customers = User.query.filter_by(role='customer').count()
    return render_template('admin_dashboard.html', waiters=waiters, rewards=rewards, transactions=transactions, total_customers=total_customers)

@app.route('/admin/add_waiter', methods=['POST'])
@admin_required
@login_required
def add_waiter():
    name = request.form.get('name')
    phone_number = request.form.get('phone_number')
    password = request.form.get('password')
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    waiter = User(name=name, phone_number=phone_number, password=hashed_password, role='waiter')
    db.session.add(waiter)
    db.session.commit()

    flash(f'Waiter {name} added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/waiter/redeem_free_meal', methods=['POST'])
@waiter_required
@login_required
def redeem_free_meal():
    phone_number = request.form.get('phone_number')
    customer = User.query.filter_by(phone_number=phone_number, role='customer').first()

    if not customer:
        flash('Customer not found.', 'danger')
        return redirect(url_for('waiter_dashboard'))

    if customer.profile.qualifying_visits < 10:
        flash('Customer does not have enough qualifying visits for a free meal.', 'warning')
        return redirect(url_for('waiter_dashboard'))

    # Reset visits and record transaction
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

    flash(f'Free meal redeemed for {customer.name}! Qualifying visits reset.', 'success')
    return redirect(url_for('waiter_dashboard'))

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

    flash(f'Reward {name} added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create initial admin if not exists
        admin = User.query.filter_by(role='admin').first()
        if not admin:
            hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(name='Admin', phone_number='0700000000', password=hashed_pw, role='admin')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, port=5000)
