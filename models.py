from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='customer') # 'admin', 'customer'
    profile = db.relationship('LoyaltyProfile', backref='user', uselist=False)

    def is_admin(self):
        return self.role == 'admin'

class LoyaltyProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_points = db.Column(db.Float, default=0.0)
    qualifying_visits = db.Column(db.Integer, default=0) # Number of visits with amount >= 2500

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    customer = db.relationship('User', foreign_keys=[customer_id], backref='transactions_as_customer')
    waiter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waiter = db.relationship('User', foreign_keys=[waiter_id], backref='transactions_as_waiter')
    amount = db.Column(db.Float, nullable=False)
    points_earned = db.Column(db.Float, default=0.0)
    points_redeemed = db.Column(db.Float, default=0.0)
    receipt_number = db.Column(db.String(50), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False) # 'earn', 'redeem', 'redeem_cash', 'pos_sync'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    point_cost = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255))
