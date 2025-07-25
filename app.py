from flask import Flask, request, jsonify
import sqlite3
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

DB_PATH = 'licenses.db'
MASTER_KEY = 'spectre-master-7788'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Drop and recreate table (if needed during dev)
    cursor.execute('DROP TABLE IF EXISTS licenses')
    cursor.execute('''
        CREATE TABLE licenses (
            key TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 5000,
            tier TEXT DEFAULT 'lite',
            issued_to TEXT,
            created_at TEXT,
            expires_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def key_exists(key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM licenses WHERE key = ?', (key,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

@app.route('/')
def index():
    return jsonify({"status": "Spectre License API running."})

@app.route('/verify', methods=['POST'])
def verify_key():
    data = request.json
    user_key = data.get('key', '').strip()
    if user_key == MASTER_KEY:
        return jsonify({'valid': True, 'tier': 'master', 'credits': 999999})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT tier, credits, expires_at FROM licenses WHERE key = ?', (user_key,))
    result = cursor.fetchone()
    conn.close()

    if result:
        tier, credits, expires_at = result
        if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
            return jsonify({'valid': False, 'reason': 'License expired'}), 403
        return jsonify({'valid': True, 'tier': tier, 'credits': credits})
    else:
        return jsonify({'valid': False}), 403

@app.route('/generate_key', methods=['GET', 'POST'])
def generate_key():
    tier = request.args.get('tier') or request.form.get('tier')
    credits = request.args.get('credits') or request.form.get('credits')
    issued_to = request.args.get('issued_to') or request.form.get('issued_to')

    if not tier or not credits or not issued_to:
        return jsonify({'error': 'Missing tier, credits, or issued_to'}), 400

    new_key = str(uuid.uuid4()).replace('-', '')
    created_at = datetime.utcnow().isoformat()
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO licenses (key, tier, credits, issued_to, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (new_key, tier, int(credits), issued_to, created_at, expires_at))
    conn.commit()
    conn.close()

    return jsonify({'generated_key': new_key})

@app.route('/edit_key', methods=['POST'])
def edit_key():
    data = request.get_json()
    key = data.get('key')
    new_tier = data.get('tier')
    new_credits = data.get('credits')
    new_issued_to = data.get('issued_to')

    if not key:
        return jsonify({"error": "Missing 'key' field"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updates = []
    params = []

    if new_tier:
        updates.append("tier = ?")
        params.append(new_tier)
    if new_credits is not None:
        updates.append("credits = ?")
        params.append(new_credits)
    if new_issued_to:
        updates.append("issued_to = ?")
        params.append(new_issued_to)

    if not updates:
        return jsonify({"error": "No fields to update"}), 400

    params.append(key)
    query = f"UPDATE licenses SET {', '.join(updates)} WHERE key = ?"
    cursor.execute(query, params)
    conn.commit()
    conn.close()

    return jsonify({"message": "Key updated successfully"})

@app.route('/view_keys', methods=['GET'])
def view_keys():
    tier_filter = request.args.get('tier')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if tier_filter:
        cursor.execute('SELECT key, tier, credits, issued_to, created_at, expires_at FROM licenses WHERE tier = ?', (tier_filter,))
    else:
        cursor.execute('SELECT key, tier, credits, issued_to, created_at, expires_at FROM licenses')

    rows = cursor.fetchall()
    conn.close()

    keys = [{
        'key': row[0],
        'tier': row[1],
        'credits': row[2],
        'issued_to': row[3],
        'created_at': row[4],
        'expires_at': row[5]
    } for row in rows]

    return jsonify({'keys': keys})

@app.route('/delete_key', methods=['POST'])
def delete_key():
    data = request.get_json()
    license_key = data.get('key')

    if not license_key:
        return jsonify({'error': 'Missing license key'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM licenses WHERE key = ?', (license_key,))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Key deleted successfully'})

@app.route('/extend_key', methods=['POST'])
def extend_key():
    data = request.get_json()
    key = data.get('key')
    new_tier = data.get('new_tier')
    additional_credits = data.get('additional_credits', 0)

    if not key or not new_tier:
        return jsonify({"error": "Missing 'key' or 'new_tier'"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT tier, credits FROM licenses WHERE key = ?', (key,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({"error": "Key not found"}), 404

    current_credits = result[1]
    updated_credits = current_credits + int(additional_credits)
    new_expiry = (datetime.utcnow() + timedelta(days=30)).isoformat()

    cursor.execute('''
        UPDATE licenses
        SET tier = ?, credits = ?, expires_at = ?
        WHERE key = ?
    ''', (new_tier, updated_credits, new_expiry, key))
    conn.commit()
    conn.close()

    return jsonify({"message": "Key extended successfully"})

@app.route('/check_expired_keys', methods=['GET'])
def check_expired_keys():
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT key, tier, credits, issued_to, created_at, expires_at
        FROM licenses
        WHERE expires_at IS NOT NULL AND expires_at < ?
    ''', (now,))
    rows = cursor.fetchall()
    conn.close()

    expired = [{
        'key': row[0],
        'tier': row[1],
        'credits': row[2],
        'issued_to': row[3],
        'created_at': row[4],
        'expires_at': row[5]
    } for row in rows]

    return jsonify({'expired_keys': expired})

@app.route('/key_stats', methods=['POST'])
def key_stats():
    data = request.get_json()
    key = data.get('key')

    if not key:
        return jsonify({'error': 'Missing key'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT key, tier, credits, issued_to, created_at, expires_at FROM licenses WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Key not found'}), 404

    created = datetime.fromisoformat(row[4])
    days_active = (datetime.utcnow() - created).days

    return jsonify({
        'key': row[0],
        'tier': row[1],
        'credits': row[2],
        'issued_to': row[3],
        'created_at': row[4],
        'expires_at': row[5],
        'days_since_created': days_active
    })

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
