@echo off
start "Admin Panel" /min cmd /k "cd /d D:\tourist_bot && D:\Python314\python.exe admin.py"
echo Админка запущена — открой http://localhost:5000
timeout /t 3
