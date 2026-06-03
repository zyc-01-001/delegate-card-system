from app import app, init_db

# 启动时初始化数据库
init_db()

if __name__ == "__main__":
    app.run()
