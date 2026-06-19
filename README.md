# Hash Grill Loyalty & Rewards System 🍗🔥

A production-ready, automated loyalty points system designed for **Hash Grill Restaurant**. This system integrates seamlessly with the restaurant's existing Linktree QR code and automates point collection directly from the POS system.

---

## 🚀 Key Features

- **Automated Point Sync**: Zero-touch automation using a POS Bridge script.
- **Smart Point Logic**:
  - **Earn**: 1 Loyalty Point for every **KES 1,000** spent.
  - **Redeem**: 10 Points = **KES 50** Instant Discount.
  - **Free Meal**: Reach **10 visits** (of KES 2,500+) to unlock a **FREE MEAL**.
- **Dual Interfaces**:
  - **Customer Dashboard**: View points balance, track free meal progress, and redeem cash discounts.
  - **Admin Dashboard**: Overview of all transactions, manual free meal redemption, and reward management.
- **Secure Self-Claim**: Customers can manually claim points using a secure 8-digit code from their receipt if they weren't entered at the POS.
- **Modern Theme**: Professional high-end restaurant aesthetic (Orange, Black, and White).

---

## 🛠️ Tech Stack

- **Backend**: Python / Flask
- **Database**: SQLite (SQLAlchemy ORM)
- **Security**: HMAC-SHA256 Signatures, CSRF Protection, Bcrypt Hashing
- **Frontend**: Bootstrap 5, FontAwesome 6, Custom CSS

---

## 📦 Installation & Setup

### 1. Server Setup (The "System")
1. **Clone/Copy** the project files to your server.
2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment**:
   Create a `.env` file or set environment variables:
   ```env
   SECRET_KEY=your-flask-secret
   POS_SECRET_KEY=hash-grill-pos-sync-secret
   ```
5. **Run the Application**:
   ```bash
   python3 app.py
   ```
   *The system will automatically initialize the database on the first run.*

### 2. POS Setup (The "Automation Bridge")
1. Copy `pos_bridge.py` to the computer where the POS software is running.
2. Ensure Python is installed on the POS computer.
3. Update the `SERVER_URL` in `pos_bridge.py` to your deployed website URL.
4. Run the script:
   ```bash
   python pos_bridge.py
   ```
   *The script will watch for receipt `.txt` files and sync them to the server automatically.*

---

## 🔐 Security

- **POS Sync**: All data sent from the POS to the server is signed with an **HMAC-SHA256 signature**. The server rejects any data that doesn't match the shared `POS_SECRET_KEY`.
- **User Passwords**: Hashed using **Bcrypt**.
- **Forms**: Protected against Cross-Site Request Forgery (CSRF).

---

## 👤 User Roles

### Admin (Initial Login)
- **Phone**: `0700000000`
- **Password**: `admin123`
- *Admins can verify customer visits and trigger the "Free Meal" redemption.*

### Customer
- Customers can register with their phone number via the Linktree link.
- Points are added automatically if their phone number is entered at the POS.
- If not, they can use the "Claim Points" feature with their receipt number and secure code.

---

## 📄 License
Production-ready for Hash Grill Restaurant. Developed by Jules.
