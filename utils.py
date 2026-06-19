import hmac, hashlib, json, os

class SignatureManager:
    def __init__(self, key=None):
        self.key = key or os.environ.get('POS_SECRET_KEY', 'hash-grill-pos-sync-secret')
    def generate_signature(self, data):
        s = json.dumps(data, sort_keys=True).encode()
        return hmac.new(self.key.encode(), s, hashlib.sha256).hexdigest()
    def verify_signature(self, data, sig):
        return hmac.compare_digest(self.generate_signature(data), sig) if sig else False

def generate_receipt_code(receipt_number, amount, secret):
    data = f"{receipt_number}-{float(amount):.2f}".encode()
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()[:8].upper()
