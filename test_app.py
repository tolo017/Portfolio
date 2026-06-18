import unittest
from app import app, db, bcrypt
from models import User, LoyaltyProfile, Transaction, Reward

class TestLoyaltySystem(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
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

    def test_point_calculation_via_sync(self):
        # Register a customer
        self.app.post('/register', data=dict(
            name='C1', phone_number='0711', password='p'
        ))

        # Simulate POS Sync: 2500 KES should give 2.5 points and 1 qualifying visit
        from utils import SignatureManager
        sig_mgr = SignatureManager()
        payload = {"transactions": [{"receipt_number": "REC001", "amount": 2500, "phone_number": "0711"}]}
        import json
        signature = sig_mgr.generate_signature(payload)

        self.app.post('/api/pos/sync',
                      data=json.dumps(payload),
                      content_type='application/json',
                      headers={"X-POS-Signature": signature})

        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertEqual(user.profile.total_points, 2.5)
            self.assertEqual(user.profile.qualifying_visits, 1)

    def test_cash_redemption(self):
        # Register and give points
        self.app.post('/register', data=dict(
            name='C1', phone_number='0711', password='p'
        ))
        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            user.profile.total_points = 25.0
            db.session.commit()

        # Login as customer
        self.app.post('/login', data=dict(
            phone_number='0711', password='p'
        ))

        # Redeem cash (10 points = 50 KES)
        # Should redeem 20 points for 100 KES
        self.app.post('/customer/redeem_cash', follow_redirects=True)

        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertEqual(user.profile.total_points, 5.0) # 25 - 20
            tx = Transaction.query.filter_by(customer_id=user.id, transaction_type='redeem_cash').first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.points_redeemed, 20)

if __name__ == '__main__':
    unittest.main()
