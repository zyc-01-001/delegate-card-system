from app import app, init_db

# 启动时初始化数据库
try:
    init_db()
except Exception as e:
    print(f"启动时数据库初始化失败（将在首次请求时重试）: {e}")

if __name__ == "__main__":
    app.run()
