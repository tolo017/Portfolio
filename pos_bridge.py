import requests, json, time, os, hmac, hashlib, re

# UPDATE THIS TO YOUR PRODUCTION SERVER URL
SERVER_URL = "http://127.0.0.1:5000/api/pos/sync"
SECRET_KEY = "hash-grill-pos-sync-secret"
WATCH_DIR = "C:/POS/Receipts"

def parse_receipt(path):
    with open(path, 'r') as f: content = f.read()
    r_num = re.search(r"Receipt\s*#?:\s*([A-Z0-9-]+)", content, re.I)
    a_amt = re.search(r"Total\s*:\s*([\d,.]+)", content, re.I)
    p_num = re.search(r"Phone\s*:\s*(\d{10,})", content, re.I)
    if r_num and a_amt:
        return {"receipt_number": r_num.group(1), "amount": float(a_amt.group(1).replace(',','')), "phone_number": p_num.group(1) if p_num else None}
    return None

while True:
    if not os.path.exists(WATCH_DIR): os.makedirs(WATCH_DIR)
    for f in os.listdir(WATCH_DIR):
        if f.endswith(".txt"):
            data = parse_receipt(os.path.join(WATCH_DIR, f))
            if data:
                payload = {"transactions": [data]}
                sig = hmac.new(SECRET_KEY.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()
                try:
                    res = requests.post(SERVER_URL, json=payload, headers={"X-POS-Signature": sig})
                    if res.status_code == 200: os.remove(os.path.join(WATCH_DIR, f))
                except: print("Offline... Sync will resume when internet returns.")
    time.sleep(10)
