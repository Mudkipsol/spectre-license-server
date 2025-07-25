from flask import Flask, request, jsonify
import sqlite3
import uuid
from datetime import datetime

app = Flask(__name__)
DB_FILE = "licenses.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            tier TEXT,
            credits INTEGER,
            issued_to TEXT,
            date_created TEXT,
            active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

@app.route("/generate_key", methods=["POST"])
def generate_key():
    data = request.json
    tier = data.get("tier", "lite").lower()
    credits = int(data.get("credits", 5000))
    issued_to = data.get("issued_to", "unknown")
    custom_key = data.get("custom_key")

    if tier not in ["trial", "lite", "premium", "custom"]:
        return jsonify({"error": "Invalid tier"}), 400

    key = custom_key or str(uuid.uuid4())

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO licenses (key, tier, credits, issued_to, date_created, active) VALUES (?, ?, ?, ?, ?, ?)", (
        key, tier, credits, issued_to, datetime.utcnow().isoformat(), 1
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "key": key,
        "tier": tier,
        "credits": credits,
        "issued_to": issued_to
    })

@app.route("/validate_key", methods=["POST"])
def validate_key():
    data = request.json
    submitted_key = data.get("key")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT tier, credits, active FROM licenses WHERE key = ?", (submitted_key,))
    row = c.fetchone()
    conn.close()

    if row:
        tier, credits, active = row
        if active:
            return jsonify({"valid": True, "tier": tier, "credits": credits})
        else:
            return jsonify({"valid": False, "error": "Key is inactive"})
    else:
        return jsonify({"valid": False, "error": "Key not found"})

@app.route("/view_keys", methods=["GET"])
def view_keys():
    tier = request.args.get("tier")
    issued_to = request.args.get("issued_to")
    active = request.args.get("active")
    specific_key = request.args.get("key")

    query = "SELECT key, tier, credits, issued_to, date_created, active FROM licenses WHERE 1=1"
    params = []

    if specific_key:
        query += " AND key = ?"
        params.append(specific_key)
    if tier:
        query += " AND tier = ?"
        params.append(tier.lower())
    if issued_to:
        query += " AND issued_to = ?"
        params.append(issued_to)
    if active is not None:
        try:
            active_int = 1 if active.lower() == "true" else 0
            query += " AND active = ?"
            params.append(active_int)
        except:
            pass

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    keys = []
    for row in rows:
        keys.append({
            "key": row[0],
            "tier": row[1],
            "credits": row[2],
            "issued_to": row[3],
            "date_created": row[4],
            "active": bool(row[5])
        })

    return jsonify(keys)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
