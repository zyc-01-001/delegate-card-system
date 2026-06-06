from app import app, init_db

# 启动时初始化数据库
init_db()

# 开发调试：显示详细错误信息（部署稳定后可移除）
@app.errorhandler(500)
def internal_error(error):
    import traceback
    tb = traceback.format_exc()
    return f"<h1>500 Internal Server Error</h1><pre>{tb}</pre>", 500

@app.errorhandler(Exception)
def handle_exception(error):
    import traceback
    tb = traceback.format_exc()
    return f"<h1>Error</h1><pre>{tb}</pre>", 500

if __name__ == "__main__":
    app.run()
