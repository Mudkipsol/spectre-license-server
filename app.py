from flask import Flask, request, jsonify
import sqlite3
import uuid
from datetime import datetime

app = Flask(__name__)
DB_FILE = "licenses.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            license_type TEXT,
            telegram_username TEXT,
            machine_id TEXT,
            spoof_limit INTEGER,
            spoof_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            hwid_locked BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

@app.route("/generate_trial", methods=["POST"])
def generate_trial():
    data = request.json
    machine_id = data.get("machine_id")
    telegram_username = data.get("telegram_username")
    if not machine_id or not telegram_username:
        return jsonify({"status": "error", "message": "Missing machine_id or telegram_username"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE machine_id=? OR telegram_username=?", (machine_id, telegram_username))
    if c.fetchone():
        conn.close()
        return jsonify({"status": "denied", "message": "Trial already issued."}), 403

    license_key = "TRIAL-" + uuid.uuid4().hex[:12].upper()
    c.execute("INSERT INTO licenses (license_key, license_type, telegram_username, machine_id, spoof_limit, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (license_key, "trial", telegram_username, machine_id, 5, datetime.utcnow()))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "license_key": license_key})

@app.route("/check_license", methods=["POST"])
def check_license():
    data = request.json
    license_key = data.get("license_key")
    machine_id = data.get("machine_id")
    if not license_key or not machine_id:
        return jsonify({"status": "error", "message": "Missing license_key or machine_id"}), 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT spoof_limit, spoof_count, machine_id FROM licenses WHERE license_key=?", (license_key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": "invalid", "message": "License not found"}), 404

    spoof_limit, spoof_count, stored_machine_id = row
    if stored_machine_id != machine_id:
        return jsonify({"status": "invalid", "message": "License locked to different machine"}), 403
    if spoof_count >= spoof_limit:
        return jsonify({"status": "blocked", "message": "Spoof limit reached"}), 403

    return jsonify({"status": "valid", "remaining_spoofs": spoof_limit - spoof_count})

@app.route("/increment_spoof", methods=["POST"])
def increment_spoof():
    data = request.json
    license_key = data.get("license_key")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE licenses SET spoof_count = spoof_count + 1 WHERE license_key=?", (license_key,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Spoof count incremented"})

if __name__ == "__main__":
    init_db()
    import os

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
