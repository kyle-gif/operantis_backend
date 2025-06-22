@echo off
ECHO =======================================
ECHO  LoL Game Analyzer 자동 실행 스크립트
ECHO =======================================

:: 가상환경 폴더 존재 여부 확인
IF NOT EXIST .\.venv\ (
    ECHO [ERROR] .venv cannot find venv file.
    PAUSE
    EXIT /B
)

:: 가상환경 활성화
ECHO.
ECHO Activating python venv
CALL .\.venv\Scripts\activate.bat

:: FastAPI 서버를 새 창에서 백그라운드로 실행
ECHO starting fastapi server
START "LoL Analyzer - FastAPI Server" uvicorn server:app --host 127.0.0.1 --port 8000

:: 서버가 시작될 때까지 잠시 대기 (3초)
ECHO waiting for server to start
TIMEOUT /T 3 /NOBREAK > NUL

:: 메인 분석 프로그램을 현재 창에서 실행
ECHO starting analysis program
python league.py

ECHO.
ECHO program ended
PAUSE