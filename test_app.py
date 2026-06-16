import unittest
from app import app, db, bcrypt
from models import User, LoyaltyProfile, Transaction, Reward

class TestLoyaltySystem(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
            # Create test admin without forcing ID
            pw = bcrypt.generate_password_hash('test').decode('utf-8')
            admin = User(name='Admin', phone_number='0700', password=pw, role='admin')
            db.session.add(admin)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_customer_registration(self):
        response = self.app.post('/register', data=dict(
            name='Test Customer',
            phone_number='0711',
            password='password'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.name, 'Test Customer')
            self.assertIsNotNone(user.profile)

    def test_point_calculation(self):
        # Register a customer
        self.app.post('/register', data=dict(
            name='C1', phone_number='0711', password='p'
        ))

        # Login as admin (who can act as waiter)
        self.app.post('/login', data=dict(
            phone_number='0700', password='test'
        ))

        # Add points: 2500 KES should give 25 points and 1 qualifying visit
        self.app.post('/waiter/dashboard', data=dict(
            phone_number='0711', amount='2500', receipt_number='REC001'
        ))

        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertEqual(user.profile.total_points, 25.0)
            self.assertEqual(user.profile.qualifying_visits, 1)

    def test_redemption(self):
        # Register and give points
        self.app.post('/register', data=dict(
            name='C1', phone_number='0711', password='p'
        ))
        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            user.profile.total_points = 100.0
            reward = Reward(name='Free Burger', point_cost=50)
            db.session.add(reward)
            db.session.commit()
            reward_id = reward.id

        # Login as customer
        self.app.post('/login', data=dict(
            phone_number='0711', password='p'
        ))

        # Redeem
        self.app.post(f'/customer/redeem/{reward_id}', follow_redirects=True)

        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertEqual(user.profile.total_points, 50.0)
            tx = Transaction.query.filter_by(customer_id=user.id, transaction_type='redeem').first()
            self.assertIsNotNone(tx)

if __name__ == '__main__':
    unittest.main()
