import requests, json, time, os, hmac, hashlib, re, sqlite3

# ==========================================
# HASH GRILL POS BRIDGE CONFIGURATION
# ==========================================
SERVER_URL = "https://your-hash-grill-vercel-url.vercel.app/api/pos/sync"
SECRET_KEY = "hash-grill-pos-sync-secret"  # Must match POS_SECRET_KEY on Vercel
WATCH_DIR = "C:/HashGrill/Receipts"       # Folder where POS saves receipt .txt files
SYNC_INTERVAL = 10                        # Check for new files every 10 seconds

class POSBridge:
    def __init__(self):
        # Local queue to ensure NO points are lost during internet outages
        self.db = sqlite3.connect("pos_sync_queue.db")
        self.db.execute('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, data TEXT)')

        if not os.path.exists(WATCH_DIR):
            os.makedirs(WATCH_DIR)
            print(f"Created watch directory: {WATCH_DIR}")

    def parse_receipt(self, path):
        """
        Regex logic to extract Receipt #, Total, and Phone from text files.
        Modify these patterns if your POS receipt format changes.
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. Find Receipt Number (e.g., REC-12345 or Receipt #12345)
            r_match = re.search(r"(?:Receipt|Bill)\s*#?\s*[:\-]?\s*([A-Z0-9-]+)", content, re.I)
            # 2. Find Total Amount (e.g., Total: 2,500.00 or GRS TOTAL: 500)
            a_match = re.search(r"(?:Total|Amount|Payable)\s*[:\-]?\s*([\d,.]+)", content, re.I)
            # 3. Find Customer Phone (Optional - e.g., 0712345678)
            p_match = re.search(r"(?:Phone|Customer|Cell)\s*[:\-]?\s*(\d{10,})", content, re.I)

            if r_match and a_match:
                receipt_num = r_match.group(1)
                amount = float(a_match.group(1).replace(',', ''))
                phone = p_match.group(1) if p_match else None

                return {
                    "receipt_number": receipt_num,
                    "amount": amount,
                    "phone_number": phone
                }
        except Exception as e:
            print(f"Error reading file {path}: {e}")
        return None

    def sign_payload(self, payload):
        """Generates a secure HMAC signature matching the server's requirements."""
        payload_json = json.dumps(payload, sort_keys=True).encode('utf-8')
        return hmac.new(SECRET_KEY.encode(), payload_json, hashlib.sha256).hexdigest()

    def run(self):
        print("🚀 Hash Grill POS Bridge is running...")
        print(f"📁 Watching: {WATCH_DIR}")

        while True:
            # --- STEP 1: SCAN FOR NEW FILES ---
            for filename in os.listdir(WATCH_DIR):
                if filename.endswith(".txt"):
                    filepath = os.path.join(WATCH_DIR, filename)
                    data = self.parse_receipt(filepath)

                    if data:
                        # Add to local database queue
                        self.db.execute("INSERT INTO queue (data) VALUES (?)", (json.dumps(data),))
                        self.db.commit()
                        print(f"✅ Captured Receipt: {data['receipt_number']} (KES {data['amount']})")

                    # Delete file after reading to keep folder clean
                    os.remove(filepath)

            # --- STEP 2: SYNC QUEUE TO SERVER ---
            cursor = self.db.execute("SELECT id, data FROM queue LIMIT 20")
            rows = cursor.fetchall()

            if rows:
                transactions = [json.loads(r[1]) for r in rows]
                payload = {"transactions": transactions}
                signature = self.sign_payload(payload)

                try:
                    headers = {"X-POS-Signature": signature, "Content-Type": "application/json"}
                    response = requests.post(SERVER_URL, json=payload, headers=headers, timeout=10)

                    if response.status_code == 200:
                        # Success! Delete synced items from local queue
                        ids = ",".join([str(r[0]) for r in rows])
                        self.db.execute(f"DELETE FROM queue WHERE id IN ({ids})")
                        self.db.commit()
                        print(f"📤 Successfully synced {len(transactions)} transaction(s) to server.")
                    else:
                        print(f"❌ Server Error ({response.status_code}): {response.text}")
                except Exception as e:
                    print(f"📡 Offline: Waiting for internet to sync {len(rows)} pending transactions...")

            time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    POSBridge().run()
