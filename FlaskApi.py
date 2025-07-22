from flask import Flask, render_template, request, redirect
import os

app = Flask(__name__)


import psycopg2
from psycopg2.extras import DictCursor

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.environ["host"],
            user=os.environ["user"],
            password=os.environ["password"],
            port=os.environ["port"],
            dbname=os.environ["dbname"],
            client_encoding = 'utf-8'
        )
        return conn
    except psycopg2.OperationalError as e:
            print(f"Ошибка подключения к БД: {e}")
            return None

@app.route("/main")
@app.route("/")
def main():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # Выполняем SQL-запрос
    cur.execute("SELECT * FROM news;")
    news = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("main.html", news=news)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/addtask", methods=['POST', 'GET'])
def addtask():
    if request.method == 'POST':
        title = request.form['title']
        task = request.form['task']
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=DictCursor)

            # Безопасный запрос с параметрами
            cur.execute(
                "INSERT INTO news (title, preview) VALUES (%s, %s)",
                (title, task)
            )

            conn.commit()  # Не забываем подтвердить изменения
            # flash('Новость успешно добавлена!', 'success')

        except psycopg2.Error as e:
            conn.rollback()  # Откатываем изменения при ошибке
            return (f'Ошибка при добавлении новости: {e}', 'danger')

        finally:
            if 'cur' in locals(): cur.close()
            if 'conn' in locals(): conn.close()
        return redirect('/')
    else:
        return render_template("addtask.html")



if __name__ == "__main__":
    app.run(debug=True)