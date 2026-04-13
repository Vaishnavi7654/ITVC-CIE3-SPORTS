from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime, date
import hashlib
import os

app = Flask(__name__)
app.secret_key = 'sports_booking_secret_123'

DB = 'sports.db'

# ─── Database Setup ────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'student'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sport TEXT NOT NULL,
        capacity INTEGER DEFAULT 10,
        description TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        FOREIGN KEY(facility_id) REFERENCES facilities(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        facility_id INTEGER,
        slot_id INTEGER,
        booking_date TEXT NOT NULL,
        status TEXT DEFAULT 'confirmed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(facility_id) REFERENCES facilities(id),
        FOREIGN KEY(slot_id) REFERENCES slots(id)
    )''')

    # Seed admin
    admin_pw = hashlib.sha256('admin123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users(name,email,password,role) VALUES(?,?,?,?)",
              ('Admin', 'admin@college.com', admin_pw, 'admin'))

    # Seed facilities
    facilities = [
        ('Cricket Ground', 'Cricket', 22, 'Full size cricket ground with pitch'),
        ('Football Field', 'Football', 22, 'Standard football field'),
        ('Basketball Court', 'Basketball', 10, 'Indoor basketball court'),
        ('Badminton Court A', 'Badminton', 4, 'Synthetic badminton court'),
        ('Badminton Court B', 'Badminton', 4, 'Synthetic badminton court'),
        ('Swimming Pool', 'Swimming', 20, 'Olympic size swimming pool'),
    ]
    for f in facilities:
        c.execute("INSERT OR IGNORE INTO facilities(name,sport,capacity,description) VALUES(?,?,?,?)", f)

    # Seed time slots
    time_slots = [
        ('06:00', '08:00'), ('08:00', '10:00'), ('10:00', '12:00'),
        ('12:00', '14:00'), ('14:00', '16:00'), ('16:00', '18:00'),
        ('18:00', '20:00'),
    ]
    fac_ids = [r[0] for r in c.execute("SELECT id FROM facilities").fetchall()]
    for fid in fac_ids:
        for s, e in time_slots:
            c.execute("INSERT OR IGNORE INTO slots(facility_id,start_time,end_time) VALUES(?,?,?)", (fid, s, e))

    conn.commit()
    conn.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ─── Auth Routes ───────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pw    = hash_pw(request.form['password'])
        conn  = get_db()
        user  = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw)).fetchone()
        conn.close()
        if user:
            session['user_id']   = user['id']
            session['user_name'] = user['name']
            session['role']      = user['role']
            return redirect(url_for('dashboard'))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name  = request.form['name']
        email = request.form['email']
        pw    = hash_pw(request.form['password'])
        try:
            conn = get_db()
            conn.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)", (name, email, pw))
            conn.commit()
            conn.close()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already registered.', 'error')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── Student Routes ────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    # upcoming bookings for this user
    bookings = conn.execute('''
        SELECT b.*, f.name as fname, f.sport, s.start_time, s.end_time
        FROM bookings b
        JOIN facilities f ON b.facility_id=f.id
        JOIN slots s ON b.slot_id=s.id
        WHERE b.user_id=? AND b.booking_date >= ? AND b.status='confirmed'
        ORDER BY b.booking_date, s.start_time
        LIMIT 5
    ''', (session['user_id'], date.today().isoformat())).fetchall()
    conn.close()
    return render_template('dashboard.html', facilities=facilities, bookings=bookings)

@app.route('/book/<int:facility_id>', methods=['GET','POST'])
def book(facility_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    facility = conn.execute("SELECT * FROM facilities WHERE id=?", (facility_id,)).fetchone()
    if not facility:
        flash('Facility not found.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        slot_id      = request.form['slot_id']
        booking_date = request.form['booking_date']

        # Check clash
        clash = conn.execute('''SELECT id FROM bookings
            WHERE facility_id=? AND slot_id=? AND booking_date=? AND status='confirmed'
        ''', (facility_id, slot_id, booking_date)).fetchone()
        if clash:
            flash('Sorry! This slot is already booked. Please choose another.', 'error')
        else:
            conn.execute('''INSERT INTO bookings(user_id,facility_id,slot_id,booking_date)
                VALUES(?,?,?,?)''', (session['user_id'], facility_id, slot_id, booking_date))
            conn.commit()
            flash('Booking confirmed!', 'success')
            conn.close()
            return redirect(url_for('my_bookings'))

    slots = conn.execute("SELECT * FROM slots WHERE facility_id=?", (facility_id,)).fetchall()
    conn.close()
    return render_template('book.html', facility=facility, slots=slots, today=date.today().isoformat())

@app.route('/api/available_slots')
def available_slots():
    facility_id  = request.args.get('facility_id')
    booking_date = request.args.get('date')
    conn = get_db()
    all_slots = conn.execute("SELECT * FROM slots WHERE facility_id=?", (facility_id,)).fetchall()
    booked    = conn.execute('''SELECT slot_id FROM bookings
        WHERE facility_id=? AND booking_date=? AND status='confirmed'
    ''', (facility_id, booking_date)).fetchall()
    conn.close()
    booked_ids = {r['slot_id'] for r in booked}
    result = [{'id': s['id'], 'start': s['start_time'], 'end': s['end_time'],
               'available': s['id'] not in booked_ids} for s in all_slots]
    return jsonify(result)

@app.route('/my_bookings')
def my_bookings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    bookings = conn.execute('''
        SELECT b.*, f.name as fname, f.sport, s.start_time, s.end_time
        FROM bookings b
        JOIN facilities f ON b.facility_id=f.id
        JOIN slots s ON b.slot_id=s.id
        WHERE b.user_id=?
        ORDER BY b.booking_date DESC, s.start_time
    ''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings, today=date.today().isoformat())

@app.route('/cancel/<int:booking_id>')
def cancel(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=? AND user_id=?",
                 (booking_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Booking cancelled.', 'info')
    return redirect(url_for('my_bookings'))

# ─── Admin Routes ──────────────────────────────────────────────────
@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    bookings = conn.execute('''
        SELECT b.*, u.name as uname, u.email, f.name as fname, f.sport, s.start_time, s.end_time
        FROM bookings b
        JOIN users u ON b.user_id=u.id
        JOIN facilities f ON b.facility_id=f.id
        JOIN slots s ON b.slot_id=s.id
        ORDER BY b.booking_date DESC, s.start_time
    ''').fetchall()
    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    users      = conn.execute("SELECT * FROM users WHERE role='student'").fetchall()
    stats = {
        'total_bookings':    conn.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'").fetchone()[0],
        'total_users':       conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        'total_facilities':  conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0],
        'today_bookings':    conn.execute("SELECT COUNT(*) FROM bookings WHERE booking_date=? AND status='confirmed'",
                                          (date.today().isoformat(),)).fetchone()[0],
    }
    conn.close()
    return render_template('admin.html', bookings=bookings, facilities=facilities, users=users, stats=stats)

@app.route('/admin/cancel/<int:booking_id>')
def admin_cancel(booking_id):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()
    flash('Booking cancelled by admin.', 'info')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)