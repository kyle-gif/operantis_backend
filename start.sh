#!/bin/bash
echo "======================================="
echo " LoL Game Analyzer 자동 실행 스크립트"
echo "======================================="

# 가상환경 폴더 존재 여부 확인
if [ ! -d ".venv" ]; then
    echo "[오류] .venv 가상환경 폴더를 찾을 수 없습니다."
    echo "먼저 터미널에서 환경 설정을 완료해주세요."
    exit 1
fi

# 가상환경 활성화
echo ""
echo "1. 파이썬 가상환경을 활성화합니다..."
source ./.venv/bin/activate

# FastAPI 서버를 백그라운드로 실행하고 프로세스 ID(PID) 저장
echo "2. FastAPI 서버를 백그라운드에서 시작합니다..."
uvicorn server:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

# 서버가 시작될 때까지 잠시 대기 (3초)
echo "3. 서버가 준비되기를 기다립니다..."
sleep 3

# 메인 스크립트 종료 시(Ctrl+C 등) 서버도 함께 종료되도록 설정
trap "echo '...'; echo 'FastAPI 서버(PID: $SERVER_PID)를 종료합니다.'; kill $SERVER_PID" INT TERM EXIT

# 메인 분석 프로그램을 포어그라운드에서 실행
echo "4. 메인 분석 프로그램을 시작합니다. Ctrl+C를 눌러 종료하세요."
python asdf.py

echo ""
echo "프로그램이 종료되었습니다."