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
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

# 数据库路径（生产环境使用绝对路径）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'instance', 'delegates.db'))

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 数据库初始化
def init_db():
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
    
    # 插入默认管理员
    c.execute("INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)", 
              ('admin', 'admin123'))
    
    conn.commit()
    conn.close()

# 获取数据库连接
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 生成代表证编号
def generate_card_number():
    conn = get_db()
    c = conn.cursor()
    year = datetime.now().year
    c.execute("SELECT COUNT(*) FROM delegates WHERE status = 'approved'")
    count = c.fetchone()[0] + 1
    conn.close()
    return f"{year}{count:04d}"

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
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(photo_path)
        
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO delegates (name, student_id, gender, political_status, 
                delegation, delegation_type, class_name, photo_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, student_id, gender, political_status, delegation, 
                  delegation_type, class_name, photo_path))
            conn.commit()
            flash('信息提交成功！请等待管理员审核。', 'success')
            return redirect(url_for('apply_success'))
        except sqlite3.IntegrityError:
            flash('该学号已提交过申请，请勿重复提交。', 'error')
        finally:
            conn.close()
    
    return render_template('apply.html')

@app.route('/apply/success')
def apply_success():
    return render_template('apply_success.html')

@app.route('/query', methods=['GET', 'POST'])
def query():
    delegate = None
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['student_id']
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM delegates WHERE name = ? AND student_id = ?", 
                  (name, student_id))
        delegate = c.fetchone()
        conn.close()
        
        if not delegate:
            flash('未找到相关代表信息，请检查姓名和学号是否正确。', 'error')
    
    return render_template('query.html', delegate=delegate)

@app.route('/card/<int:delegate_id>')
def show_card(delegate_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()
    conn.close()
    
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
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()
    conn.close()
    
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
    img = Image.new('RGB', (width, height), color='#FFF5F0')
    draw = ImageDraw.Draw(img)
    
    # 尝试加载字体
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 36)
        font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 24)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 20)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 16)
    except:
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
    if delegate['photo_path'] and os.path.exists(delegate['photo_path']):
        try:
            photo = Image.open(delegate['photo_path'])
            photo = photo.resize((150, 200))
            img.paste(photo, (width//2 - 75, photo_y))
        except:
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
        ("班级", delegate['class_name'] or ''),
        ("代表类型", delegate['delegation_type']),
        ("编号", delegate['card_number'] or ''),
    ]
    
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
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM delegates WHERE id = ?", (delegate_id,))
    delegate = c.fetchone()
    
    if not delegate:
        conn.close()
        return render_template('checkin_result.html', success=False, message="代表证不存在")
    
    if delegate['status'] != 'approved':
        conn.close()
        return render_template('checkin_result.html', success=False, message="代表证未通过审核")
    
    if delegate['checked_in']:
        conn.close()
        return render_template('checkin_result.html', success=True, 
                             message="已签到", delegate=delegate, already=True)
    
    c.execute("UPDATE delegates SET checked_in = 1, check_in_time = ? WHERE id = ?",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), delegate_id))
    conn.commit()
    conn.close()
    
    return render_template('checkin_result.html', success=True, 
                         message="签到成功！", delegate=delegate, already=False)

# ========== 管理后台 ==========

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM admins WHERE username = ? AND password = ?", 
                  (username, password))
        admin = c.fetchone()
        conn.close()
        
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
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM delegates ORDER BY created_at DESC")
    delegates = c.fetchall()
    
    # 统计
    c.execute("SELECT COUNT(*) FROM delegates")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM delegates WHERE status = 'pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM delegates WHERE status = 'approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM delegates WHERE checked_in = 1")
    checked_in = c.fetchone()[0]
    
    conn.close()
    
    return render_template('admin_dashboard.html', delegates=delegates, 
                         stats={'total': total, 'pending': pending, 
                                'approved': approved, 'checked_in': checked_in})

@app.route('/admin/approve/<int:delegate_id>')
def approve_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    card_number = generate_card_number()
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE delegates SET status = 'approved', card_number = ? WHERE id = ?",
              (card_number, delegate_id))
    conn.commit()
    conn.close()
    
    flash('审核通过！', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:delegate_id>')
def reject_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE delegates SET status = 'rejected' WHERE id = ?", (delegate_id,))
    conn.commit()
    conn.close()
    
    flash('已拒绝', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:delegate_id>')
def delete_delegate(delegate_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT photo_path FROM delegates WHERE id = ?", (delegate_id,))
    result = c.fetchone()
    if result and result['photo_path'] and os.path.exists(result['photo_path']):
        os.remove(result['photo_path'])
    
    c.execute("DELETE FROM delegates WHERE id = ?", (delegate_id,))
    conn.commit()
    conn.close()
    
    flash('已删除', 'info')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db()
    # 生产环境使用环境变量配置端口，默认5000
    port = int(os.environ.get('PORT', 5000))
    # 生产环境关闭debug模式
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
