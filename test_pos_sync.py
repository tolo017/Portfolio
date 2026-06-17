import unittest
import json
from app import app, db
from utils import SignatureManager, generate_receipt_code
from models import Transaction, User, LoyaltyProfile

class TestPOSSync(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            # Initial system data
            admin = User(name='Admin', phone_number='0700', password='p', role='admin')
            db.session.add(admin)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_pos_sync_endpoint(self):
        payload = {
            "transactions": [
                {"receipt_number": "POS-001", "amount": 2500, "phone_number": None},
                {"receipt_number": "POS-002", "amount": 1000, "phone_number": None}
            ]
        }
        sig_manager = SignatureManager()
        signature = sig_manager.generate_signature(payload)

        response = self.client.post('/api/pos/sync',
                                   json=payload,
                                   headers={'X-POS-Signature': signature})

        self.assertEqual(response.status_code, 200)
        with app.app_context():
            count = Transaction.query.filter_by(transaction_type='pos_sync').count()
            self.assertEqual(count, 2)

    def test_self_claim_points(self):
        # 1. POS Syncs an unclaimed receipt
        with app.app_context():
            db.session.add(Transaction(
                customer_id=1, waiter_id=1, amount=2500, points_earned=25.0,
                receipt_number="CLAIM-001", transaction_type='pos_sync'
            ))
            db.session.commit()

        # 2. Register user
        self.client.post('/register', data=dict(name='User', phone_number='0711', password='p'))
        self.client.post('/login', data=dict(phone_number='0711', password='p'))

        # 3. Claim
        # Force the environment variable for the test
        import os
        os.environ['POS_SECRET_KEY'] = 'hash-grill-pos-sync-secret'

        secure_code = generate_receipt_code("CLAIM-001", 2500, 'hash-grill-pos-sync-secret')

        response = self.client.post('/customer/claim_points', data=dict(
            receipt_number="CLAIM-001",
            secure_code=secure_code
        ), follow_redirects=True)

        self.assertIn(b'Success', response.data)
        with app.app_context():
            user = User.query.filter_by(phone_number='0711').first()
            self.assertEqual(user.profile.total_points, 25.0)
            self.assertEqual(user.profile.qualifying_visits, 1)

if __name__ == '__main__':
    unittest.main()
