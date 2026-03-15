@echo off
cd /d %~dp0
set WECHAT_DIGEST_MOCK=1
python src/app.py
pause
