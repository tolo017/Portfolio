import hmac
import hashlib
import json
import os

class SignatureManager:
    def __init__(self, secret_key=None):
        self.secret_key = secret_key or os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')

    def generate_signature(self, data_dict):
        """Generates a signature for a dictionary of data."""
        # Ensure consistent order by sorting keys
        data_string = json.dumps(data_dict, sort_keys=True).encode('utf-8')
        return hmac.new(self.secret_key.encode('utf-8'), data_string, hashlib.sha256).hexdigest()

    def verify_signature(self, data_dict, signature):
        """Verifies if the signature matches the data."""
        expected_signature = self.generate_signature(data_dict)
        return hmac.compare_digest(expected_signature, signature)

# Helper to generate a code for the receipt
def generate_receipt_code(receipt_number, amount, secret):
    # Use 2 decimal places for consistent string representation of currency
    formatted_amount = "{:.2f}".format(float(amount))
    data = f"{receipt_number}-{formatted_amount}"
    return hmac.new(secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()[:8].upper()
