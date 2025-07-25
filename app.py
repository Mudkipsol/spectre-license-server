from flask import Flask, request, jsonify
import sqlite3
import uuid
import datetime

app = Flask(__name__)

DB_PATH = 'licenses.db'
MASTER_KEY = 'spectre-master-7788'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 5000,
            tier TEXT DEFAULT 'lite',
            issued_to TEXT,
            created_at TEXT
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
    cursor.execute('SELECT tier, credits FROM licenses WHERE key = ?', (user_key,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return jsonify({'valid': True, 'tier': result[0], 'credits': result[1]})
    else:
        return jsonify({'valid': False}), 403

@app.route('/generate_key', methods=['POST'])
def generate_key():
    data = request.json or {}
    input_key = data.get('key', '').strip()
    tier = data.get('tier', 'lite')
    credits = int(data.get('credits', 5000))
    issued_to = data.get('issued_to', '')

    if not input_key:
        input_key = str(uuid.uuid4()).split('-')[0].upper() + '-' + str(uuid.uuid4()).split('-')[1].upper()

    if key_exists(input_key):
        return jsonify({'success': False, 'error': 'Key already exists'}), 400

    created_at = datetime.datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO licenses (key, credits, tier, issued_to, created_at) VALUES (?, ?, ?, ?, ?)',
                   (input_key, credits, tier, issued_to, created_at))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'key': input_key,
        'credits': credits,
        'tier': tier
    })

@app.route('/view_keys', methods=['GET'])
def view_keys():
    tier_filter = request.args.get('tier')  # optional: /view_keys?tier=premium
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if tier_filter:
        cursor.execute('SELECT key, tier, credits, issued_to, created_at FROM licenses WHERE tier = ?', (tier_filter,))
    else:
        cursor.execute('SELECT key, tier, credits, issued_to, created_at FROM licenses')

    rows = cursor.fetchall()
    conn.close()

    keys = [{
        'key': row[0],
        'tier': row[1],
        'credits': row[2],
        'issued_to': row[3],
        'created_at': row[4]
    } for row in rows]

    return jsonify({'keys': keys})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
