import os
from flask import Blueprint, render_template, request, redirect, url_for, current_app, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from auth_utils import login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

ALLOWED_AVATAR_EXT = {'png', 'jpg', 'jpeg'}

def allowed_avatar(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AVATAR_EXT

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']

        if not name or not email or not password:
            return "All fields required", 400

        conn = current_app.db_pool.get_connection()
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cur.fetchone():
                    return "Email already exists", 400
                pw_hash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                    (name, email, pw_hash)
                )
                conn.commit()
        finally:
            conn.close()

        return redirect(url_for('auth.login'))

    return render_template('signup.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = current_app.db_pool.get_connection()
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT id, name, email, password_hash FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
        finally:
            conn.close()

        if not user:
            flash("Invalid credentials. Want to sign up?", "error")
            return redirect(url_for('auth.login'))

        if not check_password_hash(user['password_hash'], password):
            flash("Invalid credentials. Want to sign up?", "error")
            return redirect(url_for('auth.login'))

        session['user_id'] = user['id']
        session['user_name'] = user['name']

        return redirect(url_for('dashboard.index'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = current_app.db_pool.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            if request.method == 'POST':
                name = request.form['name'].strip()
                if name:
                    cur.execute("UPDATE users SET name=%s WHERE id=%s", (name, session['user_id']))
                    session['user_name'] = name

                file = request.files.get('avatar')
                if file and file.filename:
                    if allowed_avatar(file.filename):
                        filename = secure_filename(file.filename)
                        filename = f"user{session['user_id']}_{filename}"
                        os.makedirs(current_app.config['AVATAR_FOLDER'], exist_ok=True)
                        file.save(os.path.join(current_app.config['AVATAR_FOLDER'], filename))
                        cur.execute("UPDATE users SET avatar_filename=%s WHERE id=%s", (filename, session['user_id']))
                        session['avatar'] = filename
                conn.commit()

            cur.execute("SELECT id, name, email, avatar_filename FROM users WHERE id=%s", (session['user_id'],))
            user = cur.fetchone()
    finally:
        conn.close()

    return render_template('profile.html', user=user)
