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

    cursor.execute('DROP TABLE IF EXISTS licenses')  # Optional: only if you're fine resetting

    cursor.execute('''
        CREATE TABLE licenses (
            key TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 5000,
            tier TEXT DEFAULT 'lite',
            issued_to TEXT,
            created_at TEXT,
            expires_at TEXT,
            hwid TEXT
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
    hwid = data.get('hwid', '').strip()

    if user_key == MASTER_KEY:
        return jsonify({'valid': True, 'tier': 'master', 'credits': 999999})

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT tier, credits, expires_at, hwid FROM licenses WHERE key = ?', (user_key,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'valid': False, 'reason': 'Key not found'}), 403

    tier, credits, expires_at, stored_hwid = result

    # Check expiration
    if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
        conn.close()
        return jsonify({'valid': False, 'reason': 'License expired'}), 403

    # If no HWID stored yet, bind it to current request
    if not stored_hwid:
        cursor.execute('UPDATE licenses SET hwid = ? WHERE key = ?', (hwid, user_key))
        conn.commit()
        conn.close()
        return jsonify({'valid': True, 'tier': tier, 'credits': credits, 'bound': True})

    # HWID mismatch
    if hwid != stored_hwid:
        conn.close()
        return jsonify({'valid': False, 'reason': 'HWID mismatch'}), 403

    # Valid key and HWID match
    conn.close()
    return jsonify({'valid': True, 'tier': tier, 'credits': credits})

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
    new_expires_at = data.get('expires_at')

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
    if new_expires_at:
        updates.append("expires_at = ?")
        params.append(new_expires_at)

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
        cursor.execute('SELECT key, tier, credits, issued_to, created_at, expires_at, hwid FROM licenses')

    rows = cursor.fetchall()
    conn.close()

    keys = [{
        'key': row[0],
        'tier': row[1],
        'credits': row[2],
        'issued_to': row[3],
        'created_at': row[4],
        'expires_at': row[5],
        'hwid': row[6]
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
    now = datetime.utcnow()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT key, tier, credits, issued_to, created_at, expires_at
        FROM licenses
        WHERE expires_at IS NOT NULL
    ''')
    rows = cursor.fetchall()
    conn.close()

    expired = []
    for row in rows:
        try:
            exp_date = datetime.fromisoformat(row[5])
            if exp_date < now:
                expired.append({
                    'key': row[0],
                    'tier': row[1],
                    'credits': row[2],
                    'issued_to': row[3],
                    'created_at': row[4],
                    'expires_at': row[5]
                })
        except Exception:
            continue

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

@app.route('/reset_hwid', methods=['POST'])
def reset_hwid():
    data = request.get_json()
    key = data.get('key')
    admin_password = data.get('admin_password')

    if not key or not admin_password:
        return jsonify({'error': 'Missing key or admin password'}), 400

    if admin_password != MASTER_KEY:
        return jsonify({'error': 'Unauthorized'}), 403

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT key FROM licenses WHERE key = ?', (key,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Key not found'}), 404

    cursor.execute('UPDATE licenses SET hwid = NULL WHERE key = ?', (key,))
    conn.commit()
    conn.close()

    return jsonify({'message': 'HWID reset successfully'})

@app.route('/consume_credits', methods=['POST'])
def consume_credits():
    data = request.get_json()
    key = data.get('key')
    amount = data.get('amount', 1)  # default to 1 credit per use

    if not key:
        return jsonify({'error': 'Missing key'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT credits FROM licenses WHERE key = ?', (key,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'error': 'Key not found'}), 404

    current_credits = result[0]
    if current_credits < amount:
        conn.close()
        return jsonify({'error': 'Insufficient credits'}), 403

    updated_credits = current_credits - amount
    cursor.execute('UPDATE licenses SET credits = ? WHERE key = ?', (updated_credits, key))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Credits consumed', 'remaining_credits': updated_credits})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
