@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if not exist ".env" (
    echo [경고] .env 파일이 없습니다. .env.example을 복사한 뒤 MySQL 접속 정보를 입력하세요.
)

"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

endlocal
