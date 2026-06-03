# 电子代表证管理系统

## 系统简介

山西省财政税务专科学校 · 大数据学院第三届团员代表大会暨学生代表大会 电子代表证管理系统。

支持：学生信息申报、管理员审核、电子代表证生成、扫码签到。

## 快速部署（服务器）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 使用 Gunicorn 启动（生产环境）

```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

参数说明：
- `-w 4`：4个工作进程
- `-b 0.0.0.0:5000`：绑定到所有IP，端口5000
- `wsgi:app`：使用 wsgi.py 中的 app 对象

### 3. 后台运行（推荐）

使用 `nohup` 或 `systemd`：

```bash
# nohup 方式
nohup gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app > /dev/null 2>&1 &

# 查看进程
ps aux | grep gunicorn

# 停止进程
pkill -f gunicorn
```

### 4. Nginx 反向代理（可选）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static {
        alias /path/to/delegate_card_system/static;
    }
}
```

## 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | `delegate_card_secret_key_2025` | Flask密钥 |
| `PORT` | `5000` | 服务端口 |
| `DB_PATH` | `instance/delegates.db` | 数据库路径 |
| `UPLOAD_FOLDER` | `static/uploads` | 上传文件目录 |
| `FLASK_DEBUG` | `False` | 调试模式 |

## 默认管理员账号

- 用户名：`admin`
- 密码：`admin123`

**部署后请立即修改默认密码！**

## 系统功能

1. **信息自主申报** - 学生填写信息并上传照片
2. **查询代表证** - 输入姓名+学号查询电子代表证
3. **管理后台** - 审核申报、查看统计、生成证件
4. **扫码签到** - 扫描二维码完成会议签到

## 技术栈

- Python Flask
- SQLite
- HTML/CSS/JavaScript
- Pillow（图片处理）
- qrcode（二维码生成）
