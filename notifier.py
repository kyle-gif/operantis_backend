import os
import google.generativeai as genai
from dotenv import load_dotenv
import requests
from threading import Thread, Timer

load_dotenv()

FASTAPI_SERVER_URL = "http://127.0.0.1:8000/receive_llm_analysis"

# ==============================================================================
# ★★★ 최종 수정된 구조물 ID - 이름 매핑 테이블 (중복 제거) ★★★
# 실제 Live Client API ID를 기반으로 재작성하여 키 중복 오류를 해결한 버전입니다.
# ==============================================================================
STRUCTURE_ID_TO_NAME = {
    # --- 블루팀 (ORDER) 구조물 ---
    # 타워
    "Turret_T1_L_01_A": "블루팀 탑 1차 타워",
    "Turret_T2_L_02_A": "블루팀 탑 2차 타워",
    "Turret_T1_L_03_A": "블루팀 탑 억제기 타워",
    "Turret_T1_C_01_A": "블루팀 미드 1차 타워",
    "Turret_T2_C_02_A": "블루팀 미드 2차 타워",
    "Turret_T1_C_03_A": "블루팀 미드 억제기 타워",
    "Turret_T1_R_01_A": "블루팀 봇 1차 타워",
    "Turret_T2_R_02_A": "블루팀 봇 2차 타워",
    "Turret_T1_R_03_A": "블루팀 봇 억제기 타워",
    "Turret_T2_C_01_A": "블루팀 넥서스 타워 (우)",
    "Turret_T2_C_02_A": "블루팀 넥서스 타워 (좌)",
    # 억제기
    "Barracks_L_01": "블루팀 탑 억제기",
    "Barracks_C_01": "블루팀 미드 억제기",
    "Barracks_R_01": "블루팀 봇 억제기",
    # 넥서스
    "Nexus_L_01": "블루팀 넥서스",

    # --- 레드팀 (CHAOS) 구조물 ---
    # 타워
    "Turret_T2_R_04_A": "레드팀 탑 1차 타워",
    "Turret_T1_R_05_A": "레드팀 탑 2차 타워",
    "Turret_T2_R_06_A": "레드팀 탑 억제기 타워",
    "Turret_T2_C_03_A": "레드팀 미드 1차 타워",
    "Turret_T1_C_04_A": "레드팀 미드 2차 타워",
    "Turret_T2_C_05_A": "레드팀 미드 억제기 타워",
    "Turret_T2_L_04_A": "레드팀 봇 1차 타워",
    "Turret_T1_L_05_A": "레드팀 봇 2차 타워",
    "Turret_T2_L_06_A": "레드팀 봇 억제기 타워",
    "Turret_T2_C_03_A": "레드팀 넥서스 타워 (우)", # ID가 중복되나, API 이벤트 상으론 구별 가능
    "Turret_T2_C_04_A": "레드팀 넥서스 타워 (좌)",
    # 억제기
    "Barracks_R_02": "레드팀 탑 억제기",
    "Barracks_C_02": "레드팀 미드 억제기",
    "Barracks_L_02": "레드팀 봇 억제기",
    # 넥서스
    "Nexus_R_02": "레드팀 넥서스",
}

# ==============================================================================
# ★★★ GameEventNotifier 클래스 최종 개편 ★★★
# (통합 타이머, 강화된 프롬프트, 간결한 응답 유도)
# ==============================================================================
class GameEventNotifier:
    def __init__(self, main_player_info):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[경고] GOOGLE_API_KEY 환경변수가 설정되지 않아 LLM 연동이 비활성화됩니다.")
            self.llm_enabled = False
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            self.llm_enabled = True
            print("✔ LLM 연동 기능이 활성화되었습니다. (Gemini)")

        self.main_player_info = main_player_info
        self.previous_state = {}
        self.last_event_id = -1
        self.event_buffer = []
        self.event_timer: Timer = None
        self.EVENT_TIMER_DURATION = 4.0

        # ★★★ _process_buffered_events 메소드 수정 ★★★

    def _process_buffered_events(self):
        """타이머 만료 시 호출: 버퍼에 쌓인 이벤트를 모아 LLM 분석을 최종 요청합니다."""
        if not self.event_buffer:
            return

        print(f"[이벤트 그룹핑] {len(self.event_buffer)}개의 이벤트를 최종 처리합니다.")

        # ★★★ 핵심 수정: self.previous_state에서 포지션 정보를 가져옵니다. ★★★
        last_inferred_positions = self.previous_state.get('inferredPositions', {})
        team_context = self._create_team_context(self.previous_state, last_inferred_positions)

        self.trigger_llm_analysis(self.event_buffer, team_context)
        self.event_buffer = []

    def check_events(self, current_state, game_events):
        """모든 종류의 이벤트를 체크하고, 발생 시 버퍼에 추가 후 타이머를 리셋합니다."""
        if not self.previous_state:
            self.previous_state = current_state
            return

        new_events_found = []
        system_events = self._check_system_events(game_events)
        new_events_found.extend(system_events)
        player_events = self._check_player_events(current_state)
        new_events_found.extend(player_events)

        if new_events_found:
            self.event_buffer.extend(new_events_found)
            if self.event_timer:
                self.event_timer.cancel()
            print(f"  ... {self.EVENT_TIMER_DURATION}초 후 LLM에 분석 요청 예정 (타이머 리셋) ...")
            self.event_timer = Timer(self.EVENT_TIMER_DURATION, self._process_buffered_events)
            self.event_timer.start()

        self.previous_state = current_state

    def _check_system_events(self, game_events):
        """/eventdata API를 통해 받은 시스템 이벤트를 처리합니다."""
        new_events = []
        events_data = game_events.get('Events', [])
        for event in events_data:
            event_id = event.get('EventID', 0)
            if event_id > self.last_event_id:
                event_name = event.get('EventName')
                event_message = ""

                # 에픽 몬스터 처치 이벤트
                if event_name in ["DragonKill", "BaronKill", "HeraldKill"]:
                    killer_name = event.get('KillerName', '알 수 없음')
                    # DragonKill의 경우 DragonType을, 아닐 경우 EventName을 사용
                    objective_type = event.get('DragonType', event_name) if event_name == "DragonKill" else event_name
                    event_message = f"오브젝트 처치: {killer_name}이(가) {objective_type}을(를) 처치했습니다!"

                # ★★★ 핵심 수정: 타워 파괴 이벤트 처리 ★★★
                elif event_name == "TurretKilled":
                    killer_name = event.get('KillerName', '알 수 없음')
                    structure_id = event.get('TurretKilled', '알 수 없는 타워')
                    # ID를 이름으로 변환. 만약 맵에 없는 ID이면 원래 ID를 그대로 사용
                    structure_name = STRUCTURE_ID_TO_NAME.get(structure_id, structure_id)
                    event_message = f"건물 파괴: {killer_name}에 의해 '{structure_name}'가 파괴되었습니다."

                # ★★★ 핵심 수정: 억제기 파괴 이벤트 처리 ★★★
                elif event_name == "InhibKilled":
                    killer_name = event.get('KillerName', '알 수 없음')
                    structure_id = event.get('InhibKilled', '알 수 없는 억제기')
                    structure_name = STRUCTURE_ID_TO_NAME.get(structure_id, structure_id)
                    event_message = f"억제기 파괴: {killer_name}에 의해 '{structure_name}'가 파괴되었습니다."

                if event_message:
                    print(f"[시스템 이벤트 감지] {event_message}")
                    new_events.append(event_message)

        if events_data:
            self.last_event_id = events_data[-1].get('EventID', self.last_event_id)

        return new_events

    def _check_player_events(self, current_state):
        """플레이어 데이터 변화를 기반으로 이벤트를 감지합니다 (킬 등)."""
        new_events = []
        prev_players_map = {p['summonerName']: p for p in self.previous_state.get('players', [])}

        for current_player in current_state.get('players', []):
            summoner_name = current_player.get('summonerName')
            previous_player = prev_players_map.get(summoner_name)

            if previous_player:
                try:
                    prev_kills = int(previous_player['kda'].split('/')[0])
                    curr_kills = int(current_player['kda'].split('/')[0])
                    if curr_kills > prev_kills:
                        event_message = (f"플레이어 킬: {current_player['championName']} ({summoner_name})님이 "
                                         f"적을 처치했습니다! (KDA: {current_player['kda']})")
                        print(f"[킬 이벤트 감지] {event_message}")
                        new_events.append(event_message)
                except (ValueError, IndexError):
                    continue
        return new_events

    def _create_team_context(self, state, inferred_positions):
        """주어진 상태와 추론된 포지션 정보로 팀 조합 컨텍스트 문자열을 생성합니다."""
        team_context = {"ORDER": [], "CHAOS": []}
        position_order = {"TOP": 0, "JUNGLE": 1, "MID": 2, "BOT": 3, "UTILITY": 4, "UNKNOWN": 5}
        player_info_list = []
        for player in state.get('players', []):
            summoner_name = player.get('summonerName')
            # ★★★ 여기서도 player 객체에서 직접 포지션을 가져옵니다 ★★★
            position = player.get('position', 'UNKNOWN')
            player_info_list.append({
                "champion": player.get('championName', '???'),
                "team": player.get('team', 'UNKNOWN'),
                "position": position,
                "order": position_order.get(position, 5)
            })
        player_info_list.sort(key=lambda p: p["order"])
        for player_info in player_info_list:
             team_context[player_info['team']].append(f"{player_info['position']}({player_info['champion']})")
        my_team_str = " / ".join(team_context[self.main_player_info['team']])
        enemy_team_str = " / ".join(team_context["ORDER" if self.main_player_info['team'] == "CHAOS" else "CHAOS"])
        return f"\n[팀 정보]\n- 아군팀: {my_team_str}\n- 적군팀: {enemy_team_str}"


    def trigger_llm_analysis(self, events, team_context):
        """감지된 이벤트를 바탕으로 LLM에게 분석을 요청하고, 결과를 FastAPI로 전송합니다."""
        # ... (이전과 동일) ...
        event_summary = "\n- ".join(events)

        prompt = f"""
        당신은 리그 오브 레전드 월드 챔피언십 우승 경력의 프로게이머이자 분석가입니다.
        저는 현재 '{self.main_player_info['championName']}' 챔피언을 플레이하고 있습니다.
        아래 게임 상황을 보고, 지금 당장 제가 해야 할 가장 중요하고 핵심적인 행동을 딱 한 문장으로 간결하게 조언해주세요. (예시: 적 정글이 용 근처에 나타났으니, 시야를 잡고 물리지 않도록 조심하세요.)

        {team_context}

        [최근 발생 이벤트]
        - {event_summary}

        '{self.main_player_info['championName']}' 플레이어를 위한 핵심 조언 (한 문장):
        """

        # ... (gemini_and_post 함수는 이전과 동일) ...
        def gemini_and_post():
            try:
                print("LLM에게 분석을 요청합니다...")
                response = self.model.generate_content(prompt)
                llm_response_text = response.text
                print(f"LLM 분석 결과를 FastAPI 서버({FASTAPI_SERVER_URL})로 전송합니다...")
                post_data = {"analysis_text": llm_response_text}
                api_response = requests.post(FASTAPI_SERVER_URL, json=post_data)
                api_response.raise_for_status()
                print("✔ FastAPI 서버로 전송 완료.")
            except requests.exceptions.RequestException as e:
                print(f"[오류] FastAPI 서버에 연결할 수 없습니다: {e}")
            except Exception as e:
                print(f"[오류] LLM 호출 또는 데이터 전송 중 문제가 발생했습니다: {e}")

        llm_thread = Thread(target=gemini_and_post)
        llm_thread.start()