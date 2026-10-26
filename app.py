from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
import sqlite3, csv, io, json
from datetime import date, timedelta
import calendar

app = Flask(__name__)
app.secret_key = 'foodwaste_secret_key_2024'
DB_NAME = 'food_waste.db'
WASTE_ALERT_PCT = 40
CATEGORIES = ['Veg', 'Non-Veg', 'Dairy', 'Bakery', 'Beverages', 'Snacks', 'Fruits', 'Other']
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
def today():
    return date.today().isoformat()
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT "admin")''')
    c.execute('''CREATE TABLE IF NOT EXISTS food_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_name TEXT NOT NULL,
        category TEXT DEFAULT "Other",
        prepared_qty REAL NOT NULL,
        wasted_qty REAL NOT NULL,
        date TEXT NOT NULL,
        notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_name TEXT NOT NULL,
        donated_qty REAL NOT NULL,
        recipient TEXT NOT NULL,
        date TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT,
        timestamp TEXT NOT NULL)''')

    try:
        c.execute("ALTER TABLE food_records ADD COLUMN category TEXT DEFAULT 'Other'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
    except Exception:
        pass
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username,password,role) VALUES ('admin','admin123','superadmin')")
    conn.commit()
    conn.close()

def log_action(username, action, detail=''):
    conn = get_db()
    from datetime import datetime
    conn.execute(
        "INSERT INTO activity_log (username, action, detail, timestamp) VALUES (?,?,?,?)",
        (username, action, detail, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()

def get_waste_alerts(conn):
    rows = conn.execute("""
        SELECT food_name, SUM(prepared_qty) AS prep, SUM(wasted_qty) AS waste
        FROM food_records GROUP BY LOWER(food_name) HAVING prep > 0
    """).fetchall()
    alerts = []
    for r in rows:
        pct = (r['waste'] / r['prep']) * 100
        if pct >= WASTE_ALERT_PCT:
            alerts.append({'food': r['food_name'], 'pct': round(pct,1), 'waste': r['waste'], 'prep': r['prep']})
    alerts.sort(key=lambda x: x['pct'], reverse=True)
    return alerts

def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def require_superadmin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'superadmin':
            flash('Only the super admin can do that.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?", (username, password)
        ).fetchone()
        conn.close()
        if user:
            session['user'] = username
            session['role'] = user['role']
            log_action(username, 'LOGIN', 'Logged in')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user' in session:
        log_action(session['user'], 'LOGOUT', 'Logged out')
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@require_login
def dashboard():
    conn = get_db()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records").fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records").fetchone()[0] or 0
    total_donated  = conn.execute("SELECT SUM(donated_qty)  FROM donations").fetchone()[0]    or 0
    total_records  = conn.execute("SELECT COUNT(*) FROM food_records").fetchone()[0] or 0
    alerts         = get_waste_alerts(conn)
    # today's stats for live refresh
    today_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records WHERE date=?", (today(),)).fetchone()[0] or 0
    today_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records WHERE date=?", (today(),)).fetchone()[0] or 0
    conn.close()
    return render_template('dashboard.html',
        total_prepared=total_prepared, total_wasted=total_wasted,
        total_donated=total_donated, total_records=total_records,
        today=today(), alerts=alerts, WASTE_ALERT_PCT=WASTE_ALERT_PCT,
        today_prepared=today_prepared, today_wasted=today_wasted
    )

@app.route('/api/stats')
@require_login
def api_stats():
    """JSON endpoint for live dashboard auto-refresh."""
    conn = get_db()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records").fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records").fetchone()[0] or 0
    total_donated  = conn.execute("SELECT SUM(donated_qty)  FROM donations").fetchone()[0]    or 0
    total_records  = conn.execute("SELECT COUNT(*) FROM food_records").fetchone()[0] or 0
    today_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records WHERE date=?", (today(),)).fetchone()[0] or 0
    today_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records WHERE date=?", (today(),)).fetchone()[0] or 0
    conn.close()
    waste_pct = round(total_wasted / total_prepared * 100, 1) if total_prepared > 0 else 0
    return jsonify(total_prepared=total_prepared, total_wasted=total_wasted,
                   total_donated=total_donated, total_records=total_records,
                   waste_pct=waste_pct, today_prepared=today_prepared, today_wasted=today_wasted)

@app.route('/add', methods=['GET', 'POST'])
@require_login
def add_food():
    if request.method == 'POST':
        food_name = request.form['food_name'].strip()
        category  = request.form.get('category', 'Other')
        date_val  = request.form['date']
        notes     = request.form.get('notes', '').strip()
        try:
            prepared_qty = float(request.form['prepared_qty'])
            wasted_qty   = float(request.form['wasted_qty'])
        except ValueError:
            flash('Please enter valid numbers for quantities.', 'error')
            return render_template('add_food.html', today=today(), categories=CATEGORIES)

        errors = []
        if not food_name: errors.append('Food name cannot be empty.')
        if prepared_qty <= 0: errors.append('Prepared quantity must be > 0 kg.')
        elif prepared_qty > 100000: errors.append('Prepared quantity cannot exceed 100,000 kg.')
        if wasted_qty <= 0: errors.append('Wasted quantity must be > 0 kg.')
        if prepared_qty > 0 and wasted_qty > prepared_qty:
            errors.append('Wasted quantity cannot exceed prepared quantity.')
        if date_val != today(): errors.append("Date must be today's date (" + today() + ").")
        if category not in CATEGORIES: category = 'Other'

        if errors:
            for e in errors: flash(e, 'error')
            return render_template('add_food.html', today=today(), categories=CATEGORIES)

        conn = get_db()
        conn.execute(
            "INSERT INTO food_records (food_name, category, prepared_qty, wasted_qty, date, notes) VALUES (?,?,?,?,?,?)",
            (food_name, category, prepared_qty, wasted_qty, date_val, notes)
        )
        conn.commit()
        conn.close()
        waste_pct = (wasted_qty / prepared_qty * 100) if prepared_qty > 0 else 0
        log_action(session['user'], 'ADD_FOOD', f'{food_name} ({category}): {prepared_qty}kg prepared, {wasted_qty}kg wasted')
        if waste_pct >= WASTE_ALERT_PCT:
            flash(f'⚠️ High waste alert: {waste_pct:.1f}% of {food_name} was wasted!', 'warning')
        return redirect(url_for('success', action='food'))
    return render_template('add_food.html', today=today(), categories=CATEGORIES)


@app.route('/records')
@require_login
def view_records():
    search    = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to   = request.args.get('date_to', '').strip()
    category  = request.args.get('category', '').strip()
    conn = get_db()
    query  = "SELECT * FROM food_records WHERE 1=1"
    params = []
    if search:
        query += " AND LOWER(food_name) LIKE ?"
        params.append(f'%{search.lower()}%')
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY date DESC"
    records = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('records.html', records=records,
                           search=search, date_from=date_from, date_to=date_to,
                           category=category, categories=CATEGORIES)


@app.route('/edit/<int:record_id>', methods=['GET', 'POST'])
@require_login
def edit_food(record_id):
    conn = get_db()
    record = conn.execute("SELECT * FROM food_records WHERE id=?", (record_id,)).fetchone()
    if not record:
        flash('Record not found.', 'error')
        return redirect(url_for('view_records'))
    if request.method == 'POST':
        food_name = request.form['food_name'].strip()
        category  = request.form.get('category', 'Other')
        date_val  = request.form['date']
        notes     = request.form.get('notes', '').strip()
        try:
            prepared_qty = float(request.form['prepared_qty'])
            wasted_qty   = float(request.form['wasted_qty'])
        except ValueError:
            flash('Please enter valid numbers.', 'error')
            conn.close()
            return render_template('edit_food.html', record=record, today=today(), categories=CATEGORIES)

        errors = []
        if not food_name: errors.append('Food name cannot be empty.')
        if prepared_qty <= 0: errors.append('Prepared quantity must be > 0 kg.')
        elif prepared_qty > 100000: errors.append('Max 100,000 kg.')
        if wasted_qty <= 0: errors.append('Wasted quantity must be > 0 kg.')
        if prepared_qty > 0 and wasted_qty > prepared_qty: errors.append('Wasted cannot exceed prepared.')
        if date_val != today(): errors.append("Date must be today (" + today() + ").")

        if errors:
            for e in errors: flash(e, 'error')
            conn.close()
            return render_template('edit_food.html', record=record, today=today(), categories=CATEGORIES)

        conn.execute(
            "UPDATE food_records SET food_name=?, category=?, prepared_qty=?, wasted_qty=?, date=?, notes=? WHERE id=?",
            (food_name, category, prepared_qty, wasted_qty, date_val, notes, record_id)
        )
        conn.commit()
        conn.close()
        log_action(session['user'], 'EDIT_FOOD', f'Record #{record_id} updated')
        return redirect(url_for('success', action='edit'))
    conn.close()
    return render_template('edit_food.html', record=record, today=today(), categories=CATEGORIES)


@app.route('/delete/<int:record_id>')
@require_login
def delete_food(record_id):
    conn = get_db()
    rec = conn.execute("SELECT food_name FROM food_records WHERE id=?", (record_id,)).fetchone()
    conn.execute("DELETE FROM food_records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    if rec:
        log_action(session['user'], 'DELETE_FOOD', f'Deleted: {rec["food_name"]} (#{record_id})')
    flash('Record deleted successfully.', 'success')
    return redirect(url_for('view_records'))

@app.route('/donate', methods=['GET', 'POST'])
@require_login
def donate():
    if request.method == 'POST':
        food_name = request.form['food_name'].strip()
        recipient = request.form['recipient'].strip()
        date_val  = request.form['date']
        try:
            donated_qty = float(request.form['donated_qty'])
        except ValueError:
            flash('Please enter a valid number.', 'error')
            return render_template('donate.html', today=today())

        conn_check = get_db()
        row = conn_check.execute(
            "SELECT SUM(wasted_qty) FROM food_records WHERE LOWER(food_name)=LOWER(?) AND date=?",
            (food_name, today())
        ).fetchone()
        total_wasted_today = row[0] or 0
        conn_check.close()

        errors = []
        if not food_name: errors.append('Food name cannot be empty.')
        if not recipient: errors.append('Recipient name cannot be empty.')
        if donated_qty <= 0:
            errors.append('Donated quantity must be > 0 kg.')
        elif total_wasted_today == 0:
            errors.append(f"No wasted food recorded today for '{food_name}'. Add a food record first.")
        elif donated_qty > total_wasted_today:
            errors.append(f"Donated qty ({donated_qty} kg) cannot exceed today's waste for '{food_name}' ({total_wasted_today} kg).")
        if date_val != today(): errors.append("Date must be today (" + today() + ").")

        if errors:
            for e in errors: flash(e, 'error')
            return render_template('donate.html', today=today())

        conn = get_db()
        conn.execute(
            "INSERT INTO donations (food_name, donated_qty, recipient, date) VALUES (?,?,?,?)",
            (food_name, donated_qty, recipient, date_val)
        )
        conn.commit()
        conn.close()
        log_action(session['user'], 'DONATION', f'{donated_qty}kg {food_name} → {recipient}')
        return redirect(url_for('success', action='donation'))
    return render_template('donate.html', today=today())


@app.route('/donations')
@require_login
def view_donations():
    conn = get_db()
    donations = conn.execute("SELECT * FROM donations ORDER BY date DESC").fetchall()
    conn.close()
    return render_template('donations.html', donations=donations)

# ---------- Charts ----------

@app.route('/charts')
@require_login
def charts():
    conn = get_db()
    food_data = conn.execute("""
        SELECT food_name, SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted
        FROM food_records GROUP BY LOWER(food_name) ORDER BY prepared DESC
    """).fetchall()
    daily_data = conn.execute("""
        SELECT date, SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted
        FROM food_records GROUP BY date ORDER BY date DESC LIMIT 7
    """).fetchall()
    donation_data = conn.execute("""
        SELECT food_name, SUM(donated_qty) AS donated
        FROM donations GROUP BY LOWER(food_name) ORDER BY donated DESC
    """).fetchall()
    category_data = conn.execute("""
        SELECT category, SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted
        FROM food_records GROUP BY category ORDER BY wasted DESC
    """).fetchall()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records").fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records").fetchone()[0] or 0
    total_donated  = conn.execute("SELECT SUM(donated_qty)  FROM donations").fetchone()[0]    or 0
    conn.close()
    return render_template("charts.html",
        food_data=[dict(r) for r in food_data],
        daily_data=[dict(r) for r in reversed(list(daily_data))],
        donation_data=[dict(r) for r in donation_data],
        category_data=[dict(r) for r in category_data],
        total_prepared=total_prepared, total_wasted=total_wasted,
        total_donated=total_donated, total_used=max(0, total_prepared - total_wasted)
    )

# ---------- Calendar View ----------

@app.route('/calendar')
@require_login
def calendar_view():
    year  = int(request.args.get('year',  date.today().year))
    month = int(request.args.get('month', date.today().month))

    conn = get_db()
    rows = conn.execute("""
        SELECT date, SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted
        FROM food_records
        WHERE strftime('%Y', date)=? AND strftime('%m', date)=?
        GROUP BY date
    """, (str(year), f'{month:02d}')).fetchall()
    conn.close()

    day_data = {r['date']: {'prepared': r['prepared'], 'wasted': r['wasted']} for r in rows}
    cal = calendar.monthcalendar(year, month)
    month_name = date(year, month, 1).strftime('%B %Y')

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    return render_template('calendar.html',
        cal=cal, year=year, month=month, month_name=month_name,
        day_data=day_data, today=today(),
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year
    )

# ---------- Activity Log ----------

@app.route('/log')
@require_login
def activity_log():
    conn = get_db()
    logs = conn.execute("SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 200").fetchall()
    conn.close()
    return render_template('activity_log.html', logs=logs)

# ---------- User Management ----------

@app.route('/users')
@require_superadmin
def manage_users():
    conn = get_db()
    users = conn.execute("SELECT id, username, role FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@require_superadmin
def add_user():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role     = request.form.get('role', 'admin')
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('add_user.html')
        if role not in ('admin', 'superadmin'):
            role = 'admin'
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (username, password, role))
            conn.commit()
            log_action(session['user'], 'ADD_USER', f'Created user: {username} ({role})')
            flash(f'User "{username}" created successfully.', 'success')
        except sqlite3.IntegrityError:
            flash(f'Username "{username}" already exists.', 'error')
        finally:
            conn.close()
        return redirect(url_for('manage_users'))
    return render_template('add_user.html')

@app.route('/users/delete/<int:user_id>')
@require_superadmin
def delete_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT username, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'error')
    elif user['role'] == 'superadmin':
        flash('Cannot delete the super admin account.', 'error')
    elif user['username'] == session['user']:
        flash('You cannot delete your own account.', 'error')
    else:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        log_action(session['user'], 'DELETE_USER', f'Deleted user: {user["username"]}')
        flash(f'User "{user["username"]}" deleted.', 'success')
    conn.close()
    return redirect(url_for('manage_users'))

@app.route('/change-password', methods=['GET', 'POST'])
@require_login
def change_password():
    if request.method == 'POST':
        current  = request.form['current_password']
        new_pw   = request.form['new_password'].strip()
        confirm  = request.form['confirm_password'].strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?", (session['user'], current)
        ).fetchone()
        errors = []
        if not user: errors.append('Current password is incorrect.')
        if len(new_pw) < 4: errors.append('New password must be at least 4 characters.')
        if new_pw != confirm: errors.append('New passwords do not match.')
        if errors:
            for e in errors: flash(e, 'error')
            conn.close()
            return render_template('change_password.html')
        conn.execute("UPDATE users SET password=? WHERE username=?", (new_pw, session['user']))
        conn.commit()
        conn.close()
        log_action(session['user'], 'CHANGE_PASSWORD', 'Password changed')
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('change_password.html')

# ---------- Summary Report ----------

@app.route('/report')
@require_login
def report():
    period   = request.args.get('period', 'weekly')
    today_dt = date.today()
    if period == 'monthly':
        start_dt = today_dt.replace(day=1)
        label    = today_dt.strftime('%B %Y')
    else:
        start_dt = today_dt - timedelta(days=today_dt.weekday())
        label    = f"Week of {start_dt.strftime('%d %b %Y')}"
    start = start_dt.isoformat()
    end   = today_dt.isoformat()
    conn  = get_db()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0] or 0
    total_donated  = conn.execute("SELECT SUM(donated_qty)  FROM donations    WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0] or 0
    total_records  = conn.execute("SELECT COUNT(*) FROM food_records WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0] or 0
    food_breakdown = conn.execute("""
        SELECT food_name, category,
               SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted,
               ROUND(SUM(wasted_qty)*100.0/NULLIF(SUM(prepared_qty),0),1) AS waste_pct
        FROM food_records WHERE date BETWEEN ? AND ?
        GROUP BY LOWER(food_name) ORDER BY waste_pct DESC
    """, (start, end)).fetchall()
    daily_breakdown = conn.execute("""
        SELECT date, SUM(prepared_qty) AS prepared, SUM(wasted_qty) AS wasted
        FROM food_records WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date
    """, (start, end)).fetchall()
    top_donor = conn.execute("""
        SELECT recipient, SUM(donated_qty) AS total FROM donations WHERE date BETWEEN ? AND ?
        GROUP BY recipient ORDER BY total DESC LIMIT 1
    """, (start, end)).fetchone()
    alerts = get_waste_alerts(conn)
    conn.close()
    waste_pct = round(total_wasted / total_prepared * 100, 1) if total_prepared > 0 else 0
    return render_template('report.html',
        period=period, label=label, start=start, end=end,
        total_prepared=total_prepared, total_wasted=total_wasted,
        total_donated=total_donated, total_records=total_records,
        waste_pct=waste_pct, food_breakdown=food_breakdown,
        daily_breakdown=daily_breakdown, top_donor=top_donor,
        alerts=alerts, WASTE_ALERT_PCT=WASTE_ALERT_PCT, today=today()
    )

# ---------- Export ----------

@app.route('/export/food')
@require_login
def export_food_csv():
    conn = get_db()
    records = conn.execute("SELECT id, food_name, category, prepared_qty, wasted_qty, date, notes FROM food_records ORDER BY date DESC").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Food Name', 'Category', 'Prepared (kg)', 'Wasted (kg)', 'Waste %', 'Date', 'Notes'])
    for r in records:
        pct = round(r['wasted_qty'] / r['prepared_qty'] * 100, 1) if r['prepared_qty'] > 0 else 0
        writer.writerow([r['id'], r['food_name'], r['category'] or 'Other', r['prepared_qty'], r['wasted_qty'], f"{pct}%", r['date'], r['notes'] or ''])
    output.seek(0)
    log_action(session['user'], 'EXPORT', 'Exported food records CSV')
    return Response(output, mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=food_records_{today()}.csv'})

@app.route('/export/donations')
@require_login
def export_donations_csv():
    conn = get_db()
    donations = conn.execute("SELECT id, food_name, donated_qty, recipient, date FROM donations ORDER BY date DESC").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Food Name', 'Donated (kg)', 'Recipient', 'Date'])
    for d in donations:
        writer.writerow([d['id'], d['food_name'], d['donated_qty'], d['recipient'], d['date']])
    output.seek(0)
    log_action(session['user'], 'EXPORT', 'Exported donations CSV')
    return Response(output, mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=donations_{today()}.csv'})

# ---------- Print ----------

@app.route('/print')
@require_login
def print_report():
    conn = get_db()
    records   = conn.execute("SELECT * FROM food_records ORDER BY date DESC").fetchall()
    donations = conn.execute("SELECT * FROM donations ORDER BY date DESC").fetchall()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records").fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records").fetchone()[0] or 0
    total_donated  = conn.execute("SELECT SUM(donated_qty)  FROM donations").fetchone()[0]    or 0
    conn.close()
    waste_pct = round(total_wasted / total_prepared * 100, 1) if total_prepared > 0 else 0
    return render_template('print_report.html',
        records=records, donations=donations,
        total_prepared=total_prepared, total_wasted=total_wasted,
        total_donated=total_donated, waste_pct=waste_pct, today=today()
    )

# ---------- Success ----------

@app.route('/success')
@require_login
def success():
    action = request.args.get('action', 'food')
    return render_template('success.html', action=action)



@app.route('/public')
def public_page():
    """Public-facing donation transparency page — no login needed."""
    conn = get_db()
    total_donated   = conn.execute("SELECT SUM(donated_qty) FROM donations").fetchone()[0] or 0
    total_donations = conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0] or 0
    donations = conn.execute("""
        SELECT food_name, donated_qty, recipient, date
        FROM donations ORDER BY date DESC
    """).fetchall()
    top_recipients = conn.execute("""
        SELECT recipient, SUM(donated_qty) AS total, COUNT(*) AS times
        FROM donations GROUP BY recipient ORDER BY total DESC LIMIT 5
    """).fetchall()
    by_food = conn.execute("""
        SELECT food_name, SUM(donated_qty) AS total
        FROM donations GROUP BY LOWER(food_name) ORDER BY total DESC LIMIT 8
    """).fetchall()
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(donated_qty) AS total
        FROM donations GROUP BY month ORDER BY month DESC LIMIT 6
    """).fetchall()
    total_prepared = conn.execute("SELECT SUM(prepared_qty) FROM food_records").fetchone()[0] or 0
    total_wasted   = conn.execute("SELECT SUM(wasted_qty)   FROM food_records").fetchone()[0] or 0
    conn.close()
    return render_template('public.html',
        total_donated=total_donated,
        total_donations=total_donations,
        donations=[dict(d) for d in donations],
        top_recipients=[dict(r) for r in top_recipients],
        by_food=[dict(f) for f in by_food],
        monthly=[dict(m) for m in reversed(list(monthly))],
        total_prepared=total_prepared,
        total_wasted=total_wasted,
        today=today()
    )

# ---------- Run ----------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
