from flask import Flask, render_template, request, redirect, session, flash
import os
import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

if not app.secret_key:
    raise ValueError("No SECRET_KEY set for Flask application")
from urllib.parse import urlparse


def get_db_connection():
    try:
        database_url = os.environ.get('DATABASE_URL')

        print(f"🔍 DEBUG: DATABASE_URL = {database_url}")

        if not database_url:
            # Локальная разработка
            conn = psycopg2.connect(
                host=os.environ["host"],
                user=os.environ["user"],
                password=os.environ["password"],
                port=os.environ["port"],
                dbname=os.environ["dbname"],
                client_encoding='utf-8'
            )
            print("✅ Connected to local database")
            return conn

        # Исправляем URL если нужно
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            print("🔍 DEBUG: Fixed URL protocol")

        # Парсим URL для проверки
        parsed_url = urlparse(database_url)
        print(f"🔍 DEBUG: Database name = {parsed_url.path[1:]}")  # Убираем первый /

        # Подключаемся с SSL
        conn = psycopg2.connect(
            dsn=database_url,
            sslmode='require'
        )
        print("✅ Connected to Render PostgreSQL successfully!")
        return conn

    except psycopg2.OperationalError as e:
        print(f"❌ Database operational error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect('/login')
        return f(*args, **kwargs)

    return decorated_function


def team_leader_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect('/login')
        if session.get('role') != 'team_leader':
            flash('У вас нет прав для выполнения этого действия', 'error')
            return redirect('/tasks')
        return f(*args, **kwargs)

    return decorated_function


# Регистрация
@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', '')

        if not username or not password or not role:
            flash('Все поля обязательны для заполнения', 'error')
            return render_template("register.html")

        if len(username) < 3:
            flash('Имя пользователя должно содержать минимум 3 символа', 'error')
            return render_template("register.html")

        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return render_template("register.html")

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template("register.html")

        try:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                flash('Пользователь с таким именем уже существует', 'error')
                return render_template("register.html")

            password_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, password_hash, role)
            )
            conn.commit()
            flash('Регистрация успешна! Теперь войдите в систему.', 'success')
            return redirect('/login')

        except psycopg2.Error as e:
            conn.rollback()
            flash(f'Ошибка при регистрации: {e}', 'error')
            return render_template("register.html")
        finally:
            cur.close()
            conn.close()

    return render_template("register.html")


# Вход в систему
@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Все поля обязательны для заполнения', 'error')
            return render_template("login.html")

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template("login.html")

        try:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()

            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash(f'Добро пожаловать, {user["username"]}!', 'success')
                return redirect('/tasks')
            else:
                flash('Неверное имя пользователя или пароль', 'error')
                return render_template("login.html")

        except psycopg2.Error as e:
            flash(f'Ошибка при входе: {e}', 'error')
            return render_template("login.html")
        finally:
            cur.close()
            conn.close()

    return render_template("login.html")


# Выход
@app.route("/logout")
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect('/')


# Главная страница
@app.route("/")
@app.route("/main")
def main():
    return render_template("main.html")


# Страница задач
@app.route("/tasks")
@login_required
def tasks():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template("tasks.html", tasks=[], now=datetime.now())

    try:
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute("""
            SELECT 
                ti.id as task_info_id,
                n.id,
                n.title,
                n.preview as content,
                n.created_at,
                author.username as author_name,
                assigned_by.username as assigned_by_name,
                assigned_to.username as assigned_to_name,
                ti.assigned_to,
                ti.deadline,
                ti.status
            FROM news n
            LEFT JOIN users author ON n.author_id = author.id
            LEFT JOIN task_info ti ON n.id = ti.news_id
            LEFT JOIN users assigned_by ON ti.assigned_by = assigned_by.id
            LEFT JOIN users assigned_to ON ti.assigned_to = assigned_to.id
            ORDER BY n.created_at DESC
        """)
        tasks = cur.fetchall()

        return render_template("tasks.html", tasks=tasks, now=datetime.now())

    except psycopg2.Error as e:
        flash(f'Ошибка при загрузке задач: {e}', 'error')
        return render_template("tasks.html", tasks=[], now=datetime.now())
    finally:
        cur.close()
        conn.close()


# Отметка задачи как выполненной
@app.route("/complete_task/<int:task_id>", methods=['POST'])
@login_required
def complete_task(task_id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect('/tasks')

    try:
        cur = conn.cursor(cursor_factory=DictCursor)

        # Проверяем существование задачи и права пользователя
        cur.execute("""
            SELECT ti.id, ti.assigned_to, n.author_id, ti.status 
            FROM task_info ti 
            JOIN news n ON ti.news_id = n.id 
            WHERE ti.id = %s
        """, (task_id,))
        task = cur.fetchone()

        if not task:
            flash('Задача не найдена', 'error')
            return redirect('/tasks')

        # Проверяем права: исполнитель или team_leader
        can_complete = (session['user_id'] == task['assigned_to'] or
                        session['role'] == 'team_leader')

        if not can_complete:
            flash('У вас нет прав для выполнения этого действия', 'error')
            return redirect('/tasks')

        # Обновляем статус задачи
        cur.execute(
            "UPDATE task_info SET status = 'completed' WHERE id = %s",
            (task_id,)
        )
        conn.commit()

        flash('Задача отмечена как выполненная!', 'success')

    except psycopg2.Error as e:
        conn.rollback()
        flash(f'Ошибка при обновлении задачи: {e}', 'error')
    finally:
        cur.close()
        conn.close()

    return redirect('/tasks')


# Добавление задачи (только для team_leader)
@app.route("/addtask", methods=['GET', 'POST'])
@login_required
@team_leader_required
def addtask():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        task = request.form.get('task', '').strip()
        assigned_to = request.form.get('assigned_to')
        deadline = request.form.get('deadline')

        if not title or not task:
            flash('Название и описание задачи обязательны', 'error')
            return redirect('/addtask')

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect('/addtask')

        try:
            cur = conn.cursor(cursor_factory=DictCursor)

            # Добавляем задачу в news
            cur.execute(
                "INSERT INTO news (title, preview, author_id) VALUES (%s, %s, %s) RETURNING id",
                (title, task, session['user_id'])
            )
            news_id = cur.fetchone()['id']

            # Добавляем информацию о задаче в task_info
            if assigned_to:
                cur.execute(
                    "INSERT INTO task_info (news_id, assigned_by, assigned_to, deadline) VALUES (%s, %s, %s, %s)",
                    (news_id, session['user_id'], assigned_to, deadline)
                )

            conn.commit()
            flash('Задача успешно добавлена!', 'success')
            return redirect('/tasks')

        except psycopg2.Error as e:
            conn.rollback()
            flash(f'Ошибка при добавлении задачи: {e}', 'error')
            return redirect('/addtask')
        finally:
            cur.close()
            conn.close()

    else:
        # GET запрос - показываем форму
        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template("addtask.html", users=[])

        try:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT id, username FROM users WHERE role = 'crew'")
            users = cur.fetchall()
            return render_template("addtask.html", users=users)
        except psycopg2.Error as e:
            flash(f'Ошибка при загрузке пользователей: {e}', 'error')
            return render_template("addtask.html", users=[])
        finally:
            cur.close()
            conn.close()


@app.route("/about")
def about():
    return render_template("about.html")

