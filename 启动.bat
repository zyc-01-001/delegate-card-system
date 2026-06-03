@echo off
chcp 65001 >nul
echo 正在安装依赖（首次需要几分钟）...
pip install -r requirements.txt
echo.
echo 正在启动电子代表证系统...
echo 启动成功后，请用浏览器访问：http://127.0.0.1:5000
echo.
python app.py
pause
