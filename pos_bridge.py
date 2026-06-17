import requests
import json
import time
import sqlite3
import os
import hmac
import hashlib

# Configuration
SERVER_URL = "http://127.0.0.1:5000/api/pos/sync"
SECRET_KEY = "hash-grill-pos-sync-secret"
LOCAL_DB = "pos_queue.db"

class POSBridge:
    def __init__(self):
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(LOCAL_DB)
        conn.execute('''CREATE TABLE IF NOT EXISTS queue
                       (id INTEGER PRIMARY KEY, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()

    def generate_signature(self, data):
        data_string = json.dumps(data, sort_keys=True).encode('utf-8')
        return hmac.new(SECRET_KEY.encode('utf-8'), data_string, hashlib.sha256).hexdigest()

    def queue_transaction(self, receipt_number, amount, phone_number=None):
        """Simulates capturing a receipt and adding it to the local offline queue."""
        tx = {
            "receipt_number": receipt_number,
            "amount": amount,
            "phone_number": phone_number
        }
        conn = sqlite3.connect(LOCAL_DB)
        conn.execute("INSERT INTO queue (data) VALUES (?)", (json.dumps(tx),))
        conn.commit()
        conn.close()
        print(f"Captured receipt {receipt_number}. Queued for sync.")

    def sync_to_server(self):
        """Attempts to send all queued transactions to the server."""
        conn = sqlite3.connect(LOCAL_DB)
        cursor = conn.execute("SELECT id, data FROM queue LIMIT 50")
        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return

        transactions = []
        ids = []
        for row in rows:
            ids.append(row[0])
            transactions.append(json.loads(row[1]))

        payload = {"transactions": transactions}
        signature = self.generate_signature(payload)

        try:
            headers = {"X-POS-Signature": signature, "Content-Type": "application/json"}
            response = requests.post(SERVER_URL, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                print(f"Successfully synced {len(transactions)} transactions.")
                # Clear from queue
                conn.execute(f"DELETE FROM queue WHERE id IN ({','.join(map(str, ids))})")
                conn.commit()
            else:
                print(f"Server error during sync: {response.status_code}")
        except Exception as e:
            print(f"Sync failed (offline): {e}")

        conn.close()

if __name__ == "__main__":
    bridge = POSBridge()

    # Simulation: Capture some test receipts
    bridge.queue_transaction("REC-POS-001", 1500, "0711223344")
    bridge.queue_transaction("REC-POS-002", 3000, None) # Unclaimed

    # Continuous Sync Loop
    while True:
        bridge.sync_to_server()
        time.sleep(30) # Wait 30 seconds before next sync attempt
