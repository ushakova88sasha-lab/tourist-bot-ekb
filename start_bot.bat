@echo off
for /f "tokens=1" %%p in ('wmic process where "name='python.exe' and commandline like '%%bot.py%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do taskkill /f /pid %%p >nul 2>&1
call secrets.bat
start "Tourist Bot" /min cmd /k "cd /d D:\tourist_bot && D:\Python314\python.exe bot.py"
echo Бот запущен в фоне (свёрнутое окно на панели задач)
timeout /t 3
