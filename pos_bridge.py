import requests, json, time, sqlite3, os, hmac, hashlib, re

# Configuration
# For production, change to your Vercel URL
SERVER_URL = "http://localhost:5000/api/pos/sync"
SECRET_KEY = "hash-grill-pos-sync-secret"
# Directory where your POS software saves receipt text files
WATCH_DIRECTORY = "./receipts_out"

class POSBridge:
    def __init__(self):
        # Create local queue for offline support
        self.db = sqlite3.connect("pos_queue.db")
        self.db.execute('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, data TEXT)')

        if not os.path.exists(WATCH_DIRECTORY):
            os.makedirs(WATCH_DIRECTORY)

    def parse_receipt(self, path):
        """
        Extracts Receipt Number, Total Amount, and Customer Phone from a text file.
        Modify regex patterns to match your POS software's receipt format.
        """
        try:
            with open(path, 'r') as f:
                content = f.read()

            # Pattern examples:
            # Receipt #: REC-12345
            # Total: 2,500.00
            # Customer: 0712345678

            r_num = re.search(r"Receipt\s*#?:\s*([A-Z0-9-]+)", content, re.I)
            # Remove commas from amount before converting to float
            a_amt = re.search(r"Total\s*:\s*([\d,.]+)", content, re.I)
            p_num = re.search(r"Phone\s*:\s*(\d{10,})", content, re.I)

            if r_num and a_amt:
                amount_str = a_amt.group(1).replace(',', '')
                return {
                    "receipt_number": r_num.group(1),
                    "amount": float(amount_str),
                    "phone_number": p_num.group(1) if p_num else None
                }
        except Exception as e:
            print(f"Error parsing {path}: {e}")
        return None

    def sign_payload(self, payload):
        payload_json = json.dumps(payload, sort_keys=True)
        return hmac.new(SECRET_KEY.encode(), payload_json.encode(), hashlib.sha256).hexdigest()

    def run(self):
        print(f"Hash Grill POS Bridge Started...")
        print(f"Watching: {WATCH_DIRECTORY}")

        while True:
            # 1. Watch for new receipt files
            for f in os.listdir(WATCH_DIRECTORY):
                if f.endswith(".txt"):
                    filepath = os.path.join(WATCH_DIRECTORY, f)
                    data = self.parse_receipt(filepath)
                    if data:
                        self.db.execute("INSERT INTO queue (data) VALUES (?)", (json.dumps(data),))
                        self.db.commit()
                        print(f"Queued Receipt: {data['receipt_number']}")
                    os.remove(filepath)

            # 2. Try Syncing Queue to Server
            cursor = self.db.execute("SELECT id, data FROM queue LIMIT 20")
            rows = cursor.fetchall()

            if rows:
                payload = {"transactions": [json.loads(r[1]) for r in rows]}
                signature = self.sign_payload(payload)

                try:
                    res = requests.post(
                        SERVER_URL,
                        json=payload,
                        headers={"X-POS-Signature": signature},
                        timeout=5
                    )

                    if res.status_code == 200:
                        ids = ",".join([str(r[0]) for r in rows])
                        self.db.execute(f"DELETE FROM queue WHERE id IN ({ids})")
                        self.db.commit()
                        print(f"Successfully synced {len(rows)} transactions.")
                    else:
                        print(f"Server error ({res.status_code}): {res.text}")
                except Exception as e:
                    print(f"Sync failed (Offline?): {e}")

            time.sleep(10) # Wait 10 seconds before next check

if __name__ == "__main__":
    POSBridge().run()
