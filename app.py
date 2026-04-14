from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import sqlite3
import os
import json
from werkzeug.security import check_password_hash

app = Flask(__name__, static_folder='.', static_url_path='')

# Config - Railway ready
ADMIN_PASSWORD = 'admin123'  # Change in production!
DB_PATH = os.environ.get('DATABASE_URL', 'recipes.db')
RECIPES_DIR = 'static/recipes'
os.makedirs(RECIPES_DIR, exist_ok=True)

def get_db():
    """Thread-safe SQLite for gunicorn"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  short_desc TEXT,
                  prep_time TEXT,
                  image_data TEXT,
                  full_recipe TEXT)''')
    
    # Default recipes if empty
    c.execute('SELECT COUNT(*) FROM recipes')
    if c.fetchone()[0] == 0:
        default_recipes = [
            {
                'title': "Chicken Tagine with Olives & Lemon",
                'short_desc': "Classic Moroccan slow-cooked chicken with salted lemons and green olives.",
                'prep_time': "1h 15min",
                'image_data': "",
                'full_recipe': "Brown chicken with onions, garlic, saffron. Add olives, preserved lemons, water. Simmer 1 hour."
            },
            {
                'title': "Lamb Couscous with Vegetables",
                'short_desc': "Fluffy couscous topped with tender lamb and seasonal veggies.",
                'prep_time': "1h 30min",
                'image_data': "",
                'full_recipe': "Cook lamb with turmeric, add carrots, zucchini, chickpeas. Steam couscous separately."
            }
        ]
        for r in default_recipes:
            c.execute('INSERT INTO recipes (title, short_desc, prep_time, image_data, full_recipe) VALUES (?, ?, ?, ?, ?)',
                      (r['title'], r['short_desc'], r['prep_time'], r['image_data'], r['full_recipe']))
        conn.commit()
    conn.close()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'recipes_count': get_recipes_count()})

def get_recipes_count():
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM recipes').fetchone()[0]
    conn.close()
    return count

@app.route('/api/recipes')
def api_recipes():
    conn = get_db()
    recipes = [dict(row) for row in conn.execute('SELECT * FROM recipes ORDER BY id DESC').fetchall()]
    conn.close()
    return jsonify(recipes)

@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def api_delete_recipe(recipe_id):
    pwd = request.headers.get('Authorization', '').replace('Basic ', '')
    if pwd != ADMIN_PASSWORD:
        abort(401)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    deleted = c.rowcount > 0
    conn.commit()
    
    # Delete HTML file
    html_path = os.path.join(RECIPES_DIR, f'recipe{recipe_id}.html')
    if os.path.exists(html_path):
        os.remove(html_path)
    
    conn.close()
    return jsonify({'deleted': deleted})

@app.route('/admin')
def admin():
    return send_from_directory('templates', 'admin.html')

@app.route('/admin/add', methods=['POST'])
def admin_add():
    pwd = request.form.get('password')
    if pwd != ADMIN_PASSWORD:
        abort(401)
    
    title = request.form['title']
    short_desc = request.form['short_desc']
    prep_time = request.form['prep_time']
    image_data = request.form.get('image_data', '')
    full_recipe = request.form['full_recipe']
    
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO recipes (title, short_desc, prep_time, image_data, full_recipe) VALUES (?, ?, ?, ?, ?)',
              (title, short_desc, prep_time, image_data, full_recipe))
    recipe_id = c.lastrowid
    conn.commit()
    conn.close()
    
    generate_recipe_html(recipe_id)
    
    return f'<h2>✅ Recipe added! ID: {recipe_id}</h2><a href="/admin">← Back to Admin</a> <script>setTimeout(() => location.href=\'/admin\', 2000);</script>'

def generate_recipe_html(recipe_id):
    conn = get_db()
    recipe = dict(conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone())
    conn.close()
    
    html_content = generate_recipe_page(recipe)
    path = os.path.join(RECIPES_DIR, f'recipe{recipe_id}.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html_content)

def generate_recipe_page(recipe):
    css = """
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');
    body { font-family: 'Poppins', sans-serif; background: linear-gradient(135deg, #fffaf5 0%, #f8f4f0 100%); margin: 0; padding: 20px; }
    .recipe-detail-container { max-width: 900px; margin: 50px auto; padding: 50px; background: white; border-radius: 32px; box-shadow: 0 32px 64px rgba(0,0,0,0.1); }
    h1 { color: #d97706; font-weight: 700; margin-bottom: 24px; }
    img { width: 100%; max-height: 400px; object-fit: cover; border-radius: 24px; margin-bottom: 24px; }
    .meta { display: flex; gap: 24px; color: #6b7280; margin-bottom: 24px; }
    .instructions { line-height: 1.8; color: #374151; }
    a { color: #d97706; text-decoration: none; font-weight: 500; }
    """
    
    img_src = recipe['image_data'] or f"https://via.placeholder.com/800x400/d97706/ffffff?text={recipe['title'][:20]}..."
    
    return f"""<!DOCTYPE html>
<html><head><title>{recipe['title']} - Receprotine</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>{css}</style></head>
<body>
<div class="recipe-detail-container">
    <h1>{recipe['title']}</h1>
    <img src="{img_src}" alt="{recipe['title']}" loading="lazy">
    <div class="meta">
        <strong>⏱️ Prep time:</strong> {recipe['prep_time']}
        <strong>🍽️ Portions:</strong> 4-6
    </div>
    <p>{recipe['short_desc']}</p>
    <h2>📋 Instructions</h2>
    <div class="instructions">{recipe['full_recipe'].replace('\\n', '<br>')}</div>
    <br><a href="/">&larr; العودة للوصفات</a>
</div>
</body></html>"""

@app.route('/recipe/<int:recipe_id>')
def recipe_page(recipe_id):
    path = os.path.join(RECIPES_DIR, f'recipe{recipe_id}.html')
    if os.path.exists(path):
        return send_from_directory(RECIPES_DIR, f'recipe{recipe_id}.html')
    return abort(404)

@app.route('/sse')
def sse():
    def event_stream():
        last_count = 0
        while True:
            count = get_recipes_count()
            if count != last_count:
                yield f"data: {{recipes_count: {count}}}\n\n"
                last_count = count
            yield ': heartbeat\n\n'
            import time
            time.sleep(1)
    return app.response_class(event_stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
