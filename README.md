# Operantis Backend (LoL Game Analyzer)

## 프로젝트 소개

Beef는 리그 오브 레전드(League of Legends) 인게임 실시간 데이터와 미니맵 시각 데이터(Computer Vision)를 결합하여 게임 상황을 분석하고, AI(Gemini 1.5 Flash)를 통해 사용자에게 실시간 맞춤형 조언을 **음성(TTS)**으로 제공하는 백엔드 시스템입니다.

프로게이머 수준의 분석력을 바탕으로, 복잡한 인게임 텍스트나 데이터를 직접 확인할 필요 없이 게임 플레이 도중 자연스럽게 브리핑을 받을 수 있도록 설계되었습니다.

---

## 주요 기능

- **실시간 데이터 수집 (Live Client API)**
  - 로컬 게임 클라이언트에서 제공하는 API를 통해 플레이어 KDA, 룬, 스펠, 아이템, 목표물 파괴, 킬 이벤트 등을 10초 주기로 모니터링합니다.
- **미니맵 분석 엔진 (YOLO + OpenCV)**
  - `mss`를 통해 화면을 캡처하고 사전 학습된 YOLO 모델(`best_8.pt`)로 미니맵 상의 챔피언 위치, 주요 정글 몹, 포탑 상태 등을 추적합니다.
- **동적 포지션 추론 시스템**
  - 강타(Smite) 스펠 여부, 서포터 전용 아이템(세계의 아틀라스 등) 구매 이력 및 초반 라인 출현 빈도를 종합하여 각 플레이어의 라인(탑, 정글, 미드, 원딜, 서포터)을 자동 추론합니다.
- **LLM 데이터 분석 및 피드백 (Gemini 1.5)**
  - 게임 내 오프젝트 처치, 포탑 파괴, 유의미한 킬 등의 이벤트가 발생할 경우, 실시간 누적 데이터 스냅샷을 구성해 Gemini 모델에 전송합니다. 생성된 **한 줄의 핵심 조언**이 사용자에게 피드백으로 돌아옵니다.
- **실시간 음성 출력 (ElevenLabs TTS)**
  - 생성된 핵심 조언을 로컬에 띄워진 FastAPI 메인 서버가 수신하여, ElevenLabs의 자연스러운 다국어 TTS 모델을 통해 현장감 있게 즉치 출력합니다.

---

## 시스템 구조 및 주요 파일

- **`main.py`** : 수신된 LLM 분석 결과를 음성(TTS)으로 즉각 재생하는 FastAPI 웹 서버
- **`league.py`** : 데이터 수집, 미니맵 탐지 제어, 실행 루프 및 상태 로깅(`game_log.json`)을 총괄하는 코어 모듈
- **`detector.py`** : 화면 내 미니맵 관심영역(ROI)을 설정하고 YOLOv8 구조를 기반으로 미니맵 내 챔피언과 오브젝트 위치를 식별하는 구조
- **`tracker.py`** : 탐지 기반 누적 위치 빈도를 통해 팀원 및 적군의 롤(포지션)을 스마트하게 역추적
- **`notifier.py`** : 이전 상태와 현재 상태를 비교해 주요 이벤트를 필터링하고 그룹화하여 Gemini 프롬프트를 빌드 및 FastAPI에 전달

---

## 설치 및 실행 방법

### 1. 사전 요구사항 (Prerequisites)

- Python 3.8 +
- 사전 설정이 필요한 환경변수 파일(`.env`)를 프로젝트 루트 디렉토리에 생성해야 합니다.

**`.env` 예시:**

```env
GOOGLE_API_KEY="your_gemini_api_key_here"
ELEVENLABS_API_KEY="your_elevenlabs_api_key_here"
POLL_START_INTERVAL=5
POLL_GAME_INTERVAL=10
```

### 2. 패키지 설치

가상환경(`venv`) 생성 후 의존성 패키지를 설치하는 것을 권장합니다.

```bash
# 가상환경 생성 (.venv)
python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
# 가상환경 활성화 (Mac/Linux)
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 3. 서버 및 분석기 실행

제공된 시작 스크립트를 사용하면 FastAPI 서버(백그라운드)와 메인 게임 분석기(포어그라운드)를 한 번에 실행할 수 있습니다.

**Windows 환경:**

```cmd
start.bat
```

**Mac/Linux 환경:**

```bash
bash start.sh
```

---

## 이용시 주의사항 및 커스텀 환경 가이드

1. **게임 실행 여부**: Live Client API는 인게임에 완전히 진입한 뒤 활성화되므로 서버를 먼저 켜두면 자동으로 게임 시작을 대기합니다.
2. **캡처 영역 스케일**: 미니맵 영역을 탐지할 때, `detector.py`의 `MINIMAP_SCALE = 0.25` 부분을 사용자의 해상도 및 미니맵 크기에 맞게 미세조정 해야할 수 있습니다.
3. **디스플레이 모니터 인덱스**: `mss.monitors[1]`을 통해 캡처를 수행하므로 시스템 또는 듀얼/주 모니터 세팅에 따라 번호 조정이 필요할 수 있습니다.
4. **모델 파일 경로**: `best_8.pt` 가 루트 경로에 존재해야 객체 탐지 엔진이 정상 로드됩니다.
