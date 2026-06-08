import os
import sqlite3
import qrcode
import io
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'delegate_card_secret_key_2025')

# 上传文件夹使用绝对路径，确保在不同环境下都能正确找到文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'static', 'uploads'))
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

# 数据库配置 - 支持 PostgreSQL 和 SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRESQL = bool(DATABASE_URL)

# SQLite 配置（本地开发）
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'instance', 'delegates.db'))

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ========== 统一数据库包装类 ==========
class DB:
    """统一数据库包装类，自动处理 SQLite 和 PostgreSQL 的差异"""

    def __init__(self):
        if USE_POSTGRESQL:
            import psycopg2
            import psycopg2.extras
            from urllib.parse import urlparse

            parsed = urlparse(DATABASE_URL)
            self._conn = psycopg2.connect(
                database=parsed.path[1:],
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port
            )
        else:
            self._conn = sqlite3.connect(DB_PATH)
            self._conn.row_factory = sqlite3.Row

    def cursor(self):
        if USE_POSTGRESQL:
            import psycopg2.extras
            return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            return self._conn.cursor()

    def execute(self, sql, params=None):
        sql = self._adapt_sql(sql)
        c = self.cursor()
        c.execute(sql, params or ())
        return c

    def executemany(self, sql, params_list):
        sql = self._adapt_sql(sql)
        c = self.cursor()
        c.executemany(sql, params_list)
        return c

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    @staticmethod
    def _adapt_sql(sql):
        """将 SQLite 风格的 SQL 适配为 PostgreSQL 风格"""
        if not USE_POSTGRESQL:
            return sql
        # 将 ? 占位符替换为 %s
        return sql.replace('?', '%s')

    @property
    def IntegrityError(self):
        """返回当前数据库对应的完整性错误异常类"""
        if USE_POSTGRESQL:
            import psycopg2.errors
            return psycopg2.errors.UniqueViolation
        else:
            return sqlite3.IntegrityError


_db_initialized = False

def get_db():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception:
            pass  # 初始化失败，下次请求再试
    return DB()


# 数据库初始化
def init_db():
    try:
        if USE_POSTGRESQL:
            import psycopg2
            from urllib.parse import urlparse

            parsed = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=parsed.path[1:],
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port
            )
            c = conn.cursor()

            # 学生信息表
            c.execute('''
                CREATE TABLE IF NOT EXISTS delegates (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    student_id TEXT NOT NULL UNIQUE,
                    gender TEXT,
                    political_status TEXT,
                    delegation TEXT NOT NULL,
                    delegation_type TEXT NOT NULL,
                    class_name TEXT,
                    photo_path TEXT,
                    status TEXT DEFAULT 'pending',
                    card_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checked_in INTEGER DEFAULT 0,
                    check_in_time TIMESTAMP
                )
            ''')

            # 管理员表
            c.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL
                )
            ''')

            # 插入默认管理员（5个管理员同时核销，每人负责约20人）
            default_admins = [
                ('admin01', 'admin123'),
                ('admin02', 'admin123'),
                ('admin03', 'admin123'),
                ('admin04', 'admin123'),
                ('admin05', 'admin123')
            ]
            for username, password in default_admins:
                try:
                    c.execute("INSERT INTO admins (username, password) VALUES (%s, %s)",
                              (username, password))
                except psycopg2.errors.UniqueViolation:
                    pass  # 管理员已存在

            conn.commit()
            conn.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # 学生信息表
            c.execute('''
                CREATE TABLE IF NOT EXISTS delegates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    student_id TEXT NOT NULL UNIQUE,
                    gender TEXT,
                    political_status TEXT,
                    delegation TEXT NOT NULL,
                    delegation_type TEXT NOT NULL,
                    class_name TEXT,
                    photo_path TEXT,
                    status TEXT DEFAULT 'pending',
                    card_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checked_in INTEGER DEFAULT 0,
                    check_in_time TIMESTAMP
                )
            ''')

            # 管理员表
            c.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL
                )
            ''')

            # 插入默认管理员（5个管理员同时核销，每人负责约20人）
            default_admins = [
                ('admin01', 'admin123'),
                ('admin02', 'admin123'),
                ('admin03', 'admin123'),
                ('admin04', 'admin123'),
                ('admin05', 'admin123')
            ]
            for username, password in default_admins:
                c.execute("INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)",
                          (username, password))

            conn.commit()
            conn.close()
    except Exception as e:
        print(f"数据库初始化错误: {e}")
        import traceback
        traceback.print_exc()

# 初始化/重置管理员账号（用于部署后创建新管理员）
@app.route('/init-admins')
def init_admins():
    """初始化所有管理员账号，访问此路由可创建/重置管理员账号"""
    db = get_db()
    
    default_admins = [
        ('admin01', 'admin123'),
        ('admin02', 'admin123'),
        ('admin03', 'admin123'),
        ('admin04', 'admin123'),
        ('admin05', 'admin123')
    ]
    
    created = []
    skipped = []
    
    for username, password in default_admins:
        try:
            c = db.execute("SELECT * FROM admins WHERE username = ?", (username,))
            existing = c.fetchone()
            if existing:
                # 更新密码
                db.execute("UPDATE admins SET password = ? WHERE username = ?",
                          (password, username))
                skipped.append(username)
            else:
                db.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                          (username, password))
                created.append(username)
        except Exception as e:
            return jsonify({'success': False, 'message': f'创建 {username} 失败: {str(e)}'}), 500
    
    db.commit()
    db.close()
    
    return jsonify({
        'success': True,
        'message': f'管理员账号初始化完成：新建 {len(created)} 个，更新 {len(skipped)} 个',
        'created': created,
        'updated': skipped,
        'all_admins': [a[0] for a in default_admins]
    })

# 生成代表证编号
def generate_card_number():
    db = get_db()
    c = db.execute("SELECT COUNT(*) AS count FROM delegates WHERE status = 'approved'")
    row = c.fetchone()
    count = (row['count'] if isinstance(row, dict) else row[0]) + 1
    db.close()
    return f"{datetime.now().year}{count:04d}"

# 生成二维码
def generate_qr_code(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

@app.route('/')
def index():
    return render_template('index.html')

# ========== 学生端 ==========

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['student_id']
        gender = request.form.get('gender', '')
        political_status = request.form.get('political_status', '')
        delegation = request.form['delegation']
        delegation_type = request.form['delegation_type']
        class_name = request.form.get('class_name', '')

        # 处理照片上传
        photo = request.files.get('photo')
        photo_path = ''
        if photo and photo.filename:
            filename = secure_filename(f"{student_id}_{photo.filename}")
            abs_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(abs_photo_path)
            # 存储相对路径用于URL访问，格式: static/uploads/filename
            photo_path = os.path.join('static', 'uploads', filename)

        db = get_db()
        try:
            db.execute('''
                INSERT INTO delegates (name, student_id, gender, political_status,
                delegation, delegation_type, class_name, photo_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, student_id, gender, political_status, delegation,
                  delegation_type, class_name, photo_path))
            db.commit()
            flash('信息提交成功！请等待管理员审核。', 'success')
            return redirect(url_for('apply_success'))
        except db.IntegrityError:
            flash('该学号已提交过申请，请勿重复提交。', 'error')
        finally:
            db.close()

    return render_template('apply.html')

@app.route('/apply/success')
def apply_success():
    return render_template('apply_success.html')

@app.route('/query', methods=['GET', 'POST'])
def query():
    delegate = None
    qr_base64 = None
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['student_id']

        db = get_db()
        c = db.execute("SELECT * FROM delegates WHERE name = ? AND student_id = ?",
                       (name, student_id))
        delegate = c.fetchone()
        db.close()

        if not delegate:
            flash('未找到相关代表信息，请检查姓名和学号是否正确。', 'error')
        elif delegate['status'] == 'approved':
            # 生成签到二维码
            check_in_url = request.url_root + 'checkin/' + str(delegate['id'])
            qr_img = generate_qr_code(check_in_url)
            buffer = io.BytesIO()
            qr_img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template('query.html', delegate=delegate, qr_base64=qr_base64)

@app.route('/card/<int:delegate_id>')
def show_card(delegate_id):
    db = get_db()
    c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()
    db.close()

    if not delegate or delegate['status'] != 'approved':
        flash('代表证尚未生成或审核未通过。', 'error')
        return redirect(url_for('query'))

    # 生成签到二维码
    check_in_url = request.url_root + 'checkin/' + str(delegate_id)
    qr_img = generate_qr_code(check_in_url)

    # 将二维码转为base64
    buffer = io.BytesIO()
    qr_img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template('card.html', delegate=delegate, qr_base64=qr_base64)

@app.route('/card/image/<int:delegate_id>')
def card_image(delegate_id):
    db = get_db()
    c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()
    db.close()

    if not delegate:
        return "代表证不存在", 404

    # 生成代表证图片
    img = generate_card_image(delegate)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return send_file(buffer, mimetype='image/png')

def generate_card_image(delegate):
    # 创建画布
    width, height = 600, 900
    img = Image.new('RGB', (width, height), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    # 加载本地中文字体
    font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'NotoSansCJKsc-Regular.otf')
    font_title = None
    font_subtitle = None
    font_text = None
    font_small = None
    
    try:
        if os.path.exists(font_path):
            font_title = ImageFont.truetype(font_path, 36)
            font_subtitle = ImageFont.truetype(font_path, 24)
            font_text = ImageFont.truetype(font_path, 20)
            font_small = ImageFont.truetype(font_path, 16)
        else:
            print(f"字体文件不存在: {font_path}")
    except Exception as e:
        print(f"字体加载失败: {e}, 路径: {font_path}")
    
    # 如果字体加载失败，使用默认字体
    if font_title is None:
        font_title = ImageFont.load_default()
        font_subtitle = font_title
        font_text = font_title
        font_small = font_title

    # 顶部标题
    draw.rectangle([0, 0, width, 120], fill='#C41E3A')
    draw.text((width//2, 40), "山西省财政税务专科学校", font=font_title, fill='white', anchor='mm')
    draw.text((width//2, 85), "大数据学院第三届团员代表大会暨学生代表大会", font=font_subtitle, fill='white', anchor='mm')

    # 照片区域
    photo_y = 150
    photo_abs_path = None
    if delegate['photo_path']:
        # 尝试直接作为相对路径查找
        if os.path.exists(delegate['photo_path']):
            photo_abs_path = delegate['photo_path']
        else:
            # 尝试基于项目根目录查找
            alt_path = os.path.join(BASE_DIR, delegate['photo_path'])
            if os.path.exists(alt_path):
                photo_abs_path = alt_path
    
    if photo_abs_path:
        try:
            photo = Image.open(photo_abs_path)
            photo = photo.resize((150, 200))
            img.paste(photo, (width//2 - 75, photo_y))
        except Exception as e:
            print(f"照片加载失败: {e}, 路径: {photo_abs_path}")
            draw.rectangle([width//2 - 75, photo_y, width//2 + 75, photo_y + 200],
                          outline='#C41E3A', width=2)
            draw.text((width//2, photo_y + 100), "照片", font=font_text,
                     fill='#666666', anchor='mm')
    else:
        draw.rectangle([width//2 - 75, photo_y, width//2 + 75, photo_y + 200],
                      outline='#C41E3A', width=2)
        draw.text((width//2, photo_y + 100), "照片", font=font_text,
                 fill='#666666', anchor='mm')

    # 信息区域
    info_y = 380
    line_height = 45

    info_items = [
        ("姓名", delegate['name']),
        ("学号", delegate['student_id']),
        ("性别", delegate['gender'] or ''),
        ("政治面貌", delegate['political_status'] or ''),
        ("代表团", delegate['delegation']),
    ]
    # 只有大数据学院本学院代表才显示班级
    if delegate['class_name'] and '大数据' in delegate['class_name']:
        info_items.append(("班级", delegate['class_name']))
    info_items.extend([
        ("代表类型", delegate['delegation_type']),
        ("编号", delegate['card_number'] or ''),
    ])

    for i, (label, value) in enumerate(info_items):
        y = info_y + i * line_height
        draw.text((80, y), f"{label}:", font=font_text, fill='#333333')
        draw.text((200, y), str(value), font=font_text, fill='#000000')

    # 底部
    draw.rectangle([0, height - 60, width, height], fill='#C41E3A')
    draw.text((width//2, height - 30), "签发日期: " + datetime.now().strftime("%Y年%m月%d日"),
             font=font_small, fill='white', anchor='mm')

    return img

# ========== 签到 ==========

@app.route('/checkin/<int:delegate_id>')
def check_in(delegate_id):
    db = get_db()
    c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()

    if not delegate:
        db.close()
        return render_template('checkin_result.html', success=False, message="代表证不存在")

    if delegate['status'] != 'approved':
        db.close()
        return render_template('checkin_result.html', success=False, message="代表证未通过审核")

    if delegate['checked_in']:
        db.close()
        return render_template('checkin_result.html', success=True,
                             message="已签到", delegate=delegate, already=True)

    db.execute("UPDATE delegates SET checked_in = 1, check_in_time = ? WHERE id = ?",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), delegate_id))
    db.commit()
    db.close()

    return render_template('checkin_result.html', success=True,
                         message="签到成功！", delegate=delegate, already=False)

# ========== 管理后台 ==========

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        c = db.execute("SELECT * FROM admins WHERE username = ? AND password = ?",
                       (username, password))
        admin = c.fetchone()
        db.close()

        if admin:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    c = db.execute("SELECT * FROM delegates ORDER BY created_at DESC")
    delegates = c.fetchall()

    # 统计
    c = db.execute("SELECT COUNT(*) AS count FROM delegates")
    total = c.fetchone()['count']
    c = db.execute("SELECT COUNT(*) AS count FROM delegates WHERE status = 'pending'")
    pending = c.fetchone()['count']
    c = db.execute("SELECT COUNT(*) AS count FROM delegates WHERE status = 'approved'")
    approved = c.fetchone()['count']
    c = db.execute("SELECT COUNT(*) AS count FROM delegates WHERE checked_in = 1")
    checked_in = c.fetchone()['count']

    db.close()

    return render_template('admin_dashboard.html', delegates=delegates,
                         stats={'total': total, 'pending': pending,
                                'approved': approved, 'checked_in': checked_in})

@app.route('/admin/approve/<int:delegate_id>')
def approve_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    card_number = generate_card_number()

    db = get_db()
    db.execute("UPDATE delegates SET status = 'approved', card_number = ? WHERE id = ?",
              (card_number, delegate_id))
    db.commit()
    db.close()

    flash('审核通过！', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:delegate_id>')
def reject_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    db.execute("UPDATE delegates SET status = 'rejected' WHERE id = ?", (delegate_id,))
    db.commit()
    db.close()

    flash('已拒绝', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:delegate_id>')
def delete_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    c = db.execute("SELECT photo_path FROM delegates WHERE id = ?", (delegate_id,))
    result = c.fetchone()
    if result and result['photo_path']:
        # 尝试删除照片文件（支持相对路径和绝对路径）
        photo_path = result['photo_path']
        if os.path.exists(photo_path):
            os.remove(photo_path)
        else:
            alt_path = os.path.join(BASE_DIR, photo_path)
            if os.path.exists(alt_path):
                os.remove(alt_path)

    db.execute("DELETE FROM delegates WHERE id = ?", (delegate_id,))
    db.commit()
    db.close()

    flash('已删除', 'info')
    return redirect(url_for('admin_dashboard'))

# ========== 批量审核API ==========

@app.route('/api/batch-approve', methods=['POST'])
def batch_approve():
    """批量审核通过API"""
    if not session.get('admin'):
        return jsonify({'success': False, 'message': '未授权'}), 403

    data = request.get_json()
    delegate_ids = data.get('delegate_ids', [])

    if not delegate_ids:
        return jsonify({'success': False, 'message': '未选择代表'}), 400

    db = get_db()

    success_count = 0
    failed_count = 0

    for delegate_id in delegate_ids:
        c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
        delegate = c.fetchone()

        if delegate and delegate['status'] == 'pending':
            card_number = generate_card_number()
            db.execute("UPDATE delegates SET status = 'approved', card_number = ? WHERE id = ?",
                      (card_number, delegate_id))
            success_count += 1
        else:
            failed_count += 1

    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': f'批量审核完成：成功 {success_count} 人，跳过 {failed_count} 人',
        'success_count': success_count,
        'failed_count': failed_count
    })

# ========== 批量签到API ==========

@app.route('/api/batch-checkin', methods=['POST'])
def batch_checkin():
    """批量签到API - 用于管理员批量操作"""
    if not session.get('admin'):
        return jsonify({'success': False, 'message': '未授权'}), 403

    data = request.get_json()
    delegate_ids = data.get('delegate_ids', [])

    if not delegate_ids:
        return jsonify({'success': False, 'message': '未选择代表'}), 400

    db = get_db()

    success_count = 0
    failed_count = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for delegate_id in delegate_ids:
        c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
        delegate = c.fetchone()

        if delegate and delegate['status'] == 'approved' and not delegate['checked_in']:
            db.execute("UPDATE delegates SET checked_in = 1, check_in_time = ? WHERE id = ?",
                      (now, delegate_id))
            success_count += 1
        else:
            failed_count += 1

    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': f'批量签到完成：成功 {success_count} 人，跳过 {failed_count} 人',
        'success_count': success_count,
        'failed_count': failed_count
    })

@app.route('/api/checkin-by-card', methods=['POST'])
def checkin_by_card():
    """通过卡号签到API"""
    if not session.get('admin'):
        return jsonify({'success': False, 'message': '未授权'}), 403

    data = request.get_json()
    card_number = data.get('card_number', '').strip()

    if not card_number:
        return jsonify({'success': False, 'message': '请输入卡号'}), 400

    db = get_db()
    c = db.execute("SELECT * FROM delegates WHERE card_number = ?", (card_number,))
    delegate = c.fetchone()

    if not delegate:
        db.close()
        return jsonify({'success': False, 'message': '卡号不存在'}), 404

    if delegate['status'] != 'approved':
        db.close()
        return jsonify({'success': False, 'message': '代表证未通过审核'}), 400

    if delegate['checked_in']:
        db.close()
        return jsonify({
            'success': True,
            'message': '该代表已签到',
            'delegate': {
                'name': delegate['name'],
                'student_id': delegate['student_id'],
                'check_in_time': delegate['check_in_time']
            },
            'already': True
        })

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE delegates SET checked_in = 1, check_in_time = ? WHERE id = ?",
              (now, delegate['id']))
    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': f"{delegate['name']} 签到成功！",
        'delegate': {
            'name': delegate['name'],
            'student_id': delegate['student_id'],
            'check_in_time': now
        },
        'already': False
    })

@app.route('/api/search-delegate', methods=['GET'])
def search_delegate():
    """搜索代表API - 按姓名或学号搜索"""
    if not session.get('admin'):
        return jsonify({'success': False, 'message': '未授权'}), 403

    keyword = request.args.get('keyword', '').strip()

    if not keyword:
        return jsonify({'success': False, 'message': '请输入搜索关键词'}), 400

    db = get_db()
    # 支持姓名或学号模糊搜索
    c = db.execute("""
        SELECT id, name, student_id, delegation, delegation_type,
               status, checked_in, check_in_time, card_number, photo_path
        FROM delegates
        WHERE name LIKE ? OR student_id LIKE ?
        ORDER BY
            CASE WHEN status = 'approved' THEN 0 ELSE 1 END,
            created_at DESC
    """, (f'%{keyword}%', f'%{keyword}%'))

    rows = c.fetchall()
    db.close()

    results = []
    for row in rows:
        results.append({
            'id': row['id'],
            'name': row['name'],
            'student_id': row['student_id'],
            'delegation': row['delegation'],
            'delegation_type': row['delegation_type'],
            'status': row['status'],
            'checked_in': bool(row['checked_in']),
            'check_in_time': row['check_in_time'],
            'card_number': row['card_number'],
            'photo_path': row['photo_path']
        })

    return jsonify({
        'success': True,
        'results': results,
        'count': len(results)
    })

@app.route('/api/checkin-by-id', methods=['POST'])
def checkin_by_id():
    """通过ID签到API"""
    if not session.get('admin'):
        return jsonify({'success': False, 'message': '未授权'}), 403

    data = request.get_json()
    delegate_id = data.get('delegate_id')

    if not delegate_id:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    db = get_db()
    c = db.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()

    if not delegate:
        db.close()
        return jsonify({'success': False, 'message': '代表不存在'}), 404

    if delegate['status'] != 'approved':
        db.close()
        return jsonify({'success': False, 'message': '代表证未通过审核'}), 400

    if delegate['checked_in']:
        db.close()
        return jsonify({
            'success': True,
            'message': f"{delegate['name']} 已签到",
            'delegate': {
                'name': delegate['name'],
                'student_id': delegate['student_id'],
                'check_in_time': delegate['check_in_time']
            },
            'already': True
        })

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE delegates SET checked_in = 1, check_in_time = ? WHERE id = ?",
              (now, delegate_id))
    db.commit()
    db.close()

    return jsonify({
        'success': True,
        'message': f"{delegate['name']} 签到成功！",
        'delegate': {
            'name': delegate['name'],
            'student_id': delegate['student_id'],
            'check_in_time': now
        },
        'already': False
    })

if __name__ == '__main__':
    init_db()
    # 生产环境使用环境变量配置端口，默认5000
    port = int(os.environ.get('PORT', 5000))
    # 生产环境关闭debug模式
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
