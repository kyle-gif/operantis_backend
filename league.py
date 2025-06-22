import os
import time
import json
import requests
from dotenv import load_dotenv
import urllib3
from threading import Thread
import numpy as np
from pathlib import Path
import logging
from notifier import GameEventNotifier
from detector import MinimapDetector
from tracker import PositionTracker

# ==============================================================================
# ★★★ Final Verified Zone Definitions (Tower Positions Re-calibrated) ★★★
# 사용자의 피드백을 반영하여 탑/봇 2,3차 및 미드 1,2,3차 타워 위치를 정밀 재조정한 버전입니다.
# ==============================================================================
ZONE_DEFINITIONS = [
    # --- Major Objectives (Neutral) ---
    {"name": "Baron Pit", "coords": (0.355, 0.245), "radius": 0.06},
    {"name": "Dragon Pit",   "coords": (0.645, 0.755), "radius": 0.06},

    # --- Jungle Camps ---
    {"name": "Blue Team Blue Buff", "coords": (0.185, 0.65), "radius": 0.045},
    {"name": "Blue Team Red Buff", "coords": (0.37, 0.81), "radius": 0.045},
    {"name": "Red Team Blue Buff", "coords": (0.815, 0.35), "radius": 0.045},
    {"name": "Red Team Red Buff", "coords": (0.63, 0.19), "radius": 0.045},

    # --- Blue Team Structures (Order / Bottom-Left) ---
    # Top Lane
    {"name": "Blue Top T1 Tower", "coords": (0.09, 0.28), "radius": 0.035},
    {"name": "Blue Top T2 Tower", "coords": (0.19, 0.47), "radius": 0.04},      # 수정됨
    {"name": "Blue Top T3 Tower", "coords": (0.16, 0.64), "radius": 0.04},      # 수정됨
    {"name": "Blue Top Inhibitor", "coords": (0.1, 0.71), "radius": 0.03},
    # Mid Lane
    {"name": "Blue Mid T1 Tower", "coords": (0.40, 0.60), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid T2 Tower", "coords": (0.32, 0.68), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid T3 Tower", "coords": (0.24, 0.76), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid Inhibitor", "coords": (0.17, 0.81), "radius": 0.03},
    # Bot Lane
    {"name": "Blue Bot T1 Tower", "coords": (0.72, 0.91), "radius": 0.035},
    {"name": "Blue Bot T2 Tower", "coords": (0.53, 0.81), "radius": 0.04},      # 수정됨
    {"name": "Blue Bot T3 Tower", "coords": (0.35, 0.86), "radius": 0.04},      # 수정됨
    {"name": "Blue Bot Inhibitor", "coords": (0.28, 0.9), "radius": 0.03},
    # Nexus
    {"name": "Blue Nexus Turret (Top)", "coords": (0.1, 0.85), "radius": 0.03},
    {"name": "Blue Nexus Turret (Bottom)", "coords": (0.15, 0.9), "radius": 0.03},
    {"name": "Blue Nexus", "coords": (0.07, 0.93), "radius": 0.04},

    # --- Red Team Structures (Chaos / Top-Right) ---
    # Top Lane
    {"name": "Red Top T1 Tower", "coords": (0.28, 0.09), "radius": 0.035},
    {"name": "Red Top T2 Tower", "coords": (0.47, 0.19), "radius": 0.04},      # 수정됨
    {"name": "Red Top T3 Tower", "coords": (0.64, 0.16), "radius": 0.04},      # 수정됨
    {"name": "Red Top Inhibitor", "coords": (0.72, 0.1), "radius": 0.03},
    # Mid Lane
    {"name": "Red Mid T1 Tower", "coords": (0.60, 0.40), "radius": 0.04},      # 수정됨
    {"name": "Red Mid T2 Tower", "coords": (0.68, 0.32), "radius": 0.04},      # 수정됨
    {"name": "Red Mid T3 Tower", "coords": (0.76, 0.24), "radius": 0.04},      # 수정됨
    {"name": "Red Mid Inhibitor", "coords": (0.83, 0.19), "radius": 0.03},
    # Bot Lane
    {"name": "Red Bot T1 Tower", "coords": (0.91, 0.72), "radius": 0.035},
    {"name": "Red Bot T2 Tower", "coords": (0.81, 0.53), "radius": 0.04},      # 수정됨
    {"name": "Red Bot T3 Tower", "coords": (0.86, 0.35), "radius": 0.04},      # 수정됨
    {"name": "Red Bot Inhibitor", "coords": (0.9, 0.28), "radius": 0.03},
    # Nexus
    {"name": "Red Nexus Turret (Top)", "coords": (0.85, 0.1), "radius": 0.03},
    {"name": "Red Nexus Turret (Bottom)", "coords": (0.9, 0.15), "radius": 0.03},
    {"name": "Red Nexus", "coords": (0.93, 0.07), "radius": 0.04},
]

MINIMAP_SCALE = 0.25
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("ultralytics").setLevel(logging.ERROR)
load_dotenv()
POLL_START = int(os.getenv("POLL_START_INTERVAL", 5))
POLL_GAME = int(os.getenv("POLL_GAME_INTERVAL", 10))

def map_coords_to_location(x_norm, y_norm):
    """
    정규화된 좌표(x, y)에 대해,
    1. 정확히 포함되는 존(Zone)이 있으면 해당 존의 이름을 반환합니다.
    2. 포함되는 존이 없으면, 가장 가까운 존을 찾아 'OO 근처' 형태로 반환합니다.
    """
    # 1. 정확한 존(Zone) 내부에 있는지 먼저 확인
    for zone in ZONE_DEFINITIONS:
        dist = np.sqrt((x_norm - zone["coords"][0]) ** 2 + (y_norm - zone["coords"][1]) ** 2)
        if dist <= zone["radius"]:
            return zone["name"]  # 정확히 안에 있으면 해당 존 이름 바로 반환

    # 2. 정확한 존에 속하지 않을 경우, 가장 가까운 존을 찾아 "근처"로 표기
    min_distance = float('inf')  # 최소 거리를 무한대로 초기화
    closest_zone_name = None

    for zone in ZONE_DEFINITIONS:
        dist = np.sqrt((x_norm - zone["coords"][0]) ** 2 + (y_norm - zone["coords"][1]) ** 2)
        if dist < min_distance:
            min_distance = dist
            closest_zone_name = zone["name"]

    # 가장 가까운 존이 있었다면, "근처" 태그를 붙여 반환
    if closest_zone_name:
        return f"{closest_zone_name} 근처"

    # ZONE_DEFINITIONS가 비어있는 극단적인 경우를 대비한 최종 fallback
    return "알 수 없는 지역"


# --- (API 호출 함수들 - fetch_active_player_name 추가) ---
def fetch_all_game_data(base_url):
    resp = requests.get(f"{base_url}/allgamedata", verify=False)
    resp.raise_for_status()
    return resp.json()

# ★★★ 신규 추가: 게임 이벤트 데이터 가져오는 함수 ★★★
def fetch_event_data(base_url):
    """/eventdata API로부터 게임 이벤트 목록을 가져옵니다."""
    try:
        resp = requests.get(f"{base_url}/eventdata", verify=False)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException:
        return {"Events": []} # 오류 발생 시 빈 목록 반환

def find_live_client_url():
    for port in range(2997, 3003):
        base = f"https://127.0.0.1:{port}/liveclientdata"
        try:
            resp = requests.get(f"{base}/allgamedata", verify=False, timeout=1)
            if resp.status_code == 200:
                print(f"✔ LiveClient API 연결됨: {base}")
                return base
        except requests.exceptions.RequestException:
            continue
    return None


def get_champion_name_map():
    print("라이엇 데이터 드래곤에서 최신 챔피언 정보를 가져옵니다...")
    try:
        versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        latest_version = requests.get(versions_url).json()[0]
        print(f"최신 게임 버전: {latest_version}")
        champion_data_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/champion.json"
        all_champions_data = requests.get(champion_data_url).json()['data']
        champion_map = {eng_id.lower(): champ_info['name'] for eng_id, champ_info in all_champions_data.items()}
        print(f"✔ {len(champion_map)}개의 챔피언 이름 매핑 완료. (소문자 기준)")
        return champion_map
    except Exception as e:
        print(f"오류: 챔피언 정보를 가져오는 데 실패했습니다: {e}")
        return None


# ★★★ 신규 추가: 현재 플레이어 이름 가져오는 함수 ★★★
def fetch_active_player_name(base_url):
    """현재 플레이어(스크립트 사용자)의 소환사명을 가져옵니다."""
    try:
        resp = requests.get(f"{base_url}/activeplayername", verify=False)
        resp.raise_for_status()
        # API가 이름을 따옴표로 감싸서 반환하므로 제거해줍니다.
        return resp.text.strip('"')
    except requests.exceptions.RequestException as e:
        print(f"[오류] 현재 플레이어 이름을 가져오는 데 실패했습니다: {e}")
        return None


# ==============================================================================
# ★★★ serialize_game_state_for_log 함수 수정 ★★★
# (inferred_positions를 최종 데이터에 포함)
# ==============================================================================
def serialize_game_state_for_log(all_data, minimap_objects, active_player_name, inferred_positions):
    """JSON 로그에 저장할 깔끔하고 상세한 형태의 데이터로 가공합니다."""
    players_summary = []
    for p in all_data.get('allPlayers', []):
        summoner_name = p.get('summonerName')
        scores = p.get('scores', {})
        items = [item.get('itemID') for item in p.get('items', [])]
        spells_data = p.get('summonerSpells', {})
        spells = {"spell1_name": spells_data.get('summonerSpellOne', {}).get('displayName', 'N/A'),
                  "spell2_name": spells_data.get('summonerSpellTwo', {}).get('displayName', 'N/A')}
        runes_data = p.get('runes', {})
        runes = {"primary_style_name": runes_data.get('primaryRuneTreeDisplayName', 'N/A'),
                 "secondary_style_name": runes_data.get('secondaryRuneTreeDisplayName', 'N/A'),
                 "keystone_name": runes_data.get('keystone', {}).get('displayName', 'N/A')}

        position = inferred_positions.get(summoner_name, 'UNKNOWN')

        player_data = {
            "summonerName": summoner_name,
            "championName": p.get('championName'),
            "position": position,
            "team": p.get('team'),
            "level": p.get('level'),
            "kda": f"{scores.get('kills', 0)}/{scores.get('deaths', 0)}/{scores.get('assists', 0)}",
            "items": items,
            "spells": spells,
            "runes": runes,
            "isMainPlayer": summoner_name == active_player_name
        }
        players_summary.append(player_data)

    # ★★★ 핵심 수정: 최종 데이터에 추론된 포지션 정보(inferred_positions)를 함께 저장 ★★★
    clean_data = {
        "gameTime": all_data.get("gameData", {}).get("gameTime", 0),
        "players": players_summary,
        "detectedMinimapObjects": minimap_objects,
        "inferredPositions": inferred_positions  # <-- 포지션 맵 추가
    }
    return clean_data


# ==============================================================================
# ★★★ monitor_game 함수 최종 완성본 (메소드 이름 오류 수정) ★★★
# ==============================================================================
def monitor_game(base_url, detector, champion_name_map):
    print("▶ 게임 진행 중… 데이터 수집을 시작합니다.")
    log_path = Path("game_log.json")
    game_log = {}
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            try:
                game_log = json.load(f)
            except json.JSONDecodeError:
                game_log = {}

    # 1. 게임 시작 시, 현재 플레이어의 기본 정보(이름, 챔피언, 팀)를 먼저 확정합니다.
    active_player_name = fetch_active_player_name(base_url)
    main_player_info = {}
    if not active_player_name:
        print("[경고] 현재 플레이어 이름을 특정할 수 없습니다. 일부 기능이 제한될 수 있습니다.")
    else:
        print(f"✔ 현재 플레이어: {active_player_name}")

    try:
        initial_data = fetch_all_game_data(base_url)
        for p in initial_data.get('allPlayers', []):
            if p.get('summonerName') == active_player_name:
                main_player_info = {
                    "name": active_player_name,
                    "championName": p.get('championName'),
                    "team": p.get('team')
                }
                print(f"✔ 현재 플레이어 정보: {main_player_info}")
                break
    except requests.exceptions.RequestException as e:
        print(f"게임 시작 데이터 로딩 실패: {e}. 잠시 후 재시도합니다.")
        time.sleep(5)
        try:
            initial_data = fetch_all_game_data(base_url)
            for p in initial_data.get('allPlayers', []):
                if p.get('summonerName') == active_player_name:
                    main_player_info = { "name": active_player_name, "championName": p.get('championName'), "team": p.get('team') }
        except requests.exceptions.RequestException:
             print("[오류] 플레이어 정보 초기화에 최종 실패했습니다. 프로그램을 종료합니다.")
             return

    # 2. 상태 추적 및 이벤트 알림을 위한 클래스 인스턴스 생성
    position_tracker = PositionTracker()
    notifier = GameEventNotifier(main_player_info)
    champion_last_positions = {}

    # 3. 메인 모니터링 루프 시작
    try:
        while detector.running:
            all_data = fetch_all_game_data(base_url)
            game_events = fetch_event_data(base_url)

            current_champion_names_kr = {p['championName'] for p in all_data.get('allPlayers', []) if p.get('championName')}
            if not current_champion_names_kr:
                time.sleep(POLL_GAME)
                continue

            raw_detections = detector.get_detected_objects()
            visible_champions = {}
            for obj in raw_detections:
                eng_tag = obj['tag'].lower()
                kor_tag = champion_name_map.get(eng_tag)
                if kor_tag and kor_tag in current_champion_names_kr:
                    location = map_coords_to_location(obj['x_norm'], obj['y_norm'])
                    visible_champions[kor_tag] = location
                    champion_last_positions[kor_tag] = location

            # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
            # ★★★ 핵심 수정: PositionTracker의 올바른 메소드 호출 ★★★
            # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
            # 3-3. 동적 포지션 추론기 업데이트 및 역할 배정
            # 1단계: 목격 횟수 누적
            position_tracker.update_sighting_counts(all_data.get('allPlayers', []), visible_champions)
            # 2단계: 누적된 데이터를 바탕으로 역할 최종 할당
            position_tracker.infer_and_assign_roles(all_data.get('allPlayers', []))
            # 3단계: 할당된 포지션 결과 가져오기
            inferred_positions = position_tracker.get_positions()
            # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

            final_minimap_objects = []
            for name_kr in sorted(list(current_champion_names_kr)):
                if name_kr in visible_champions:
                    final_minimap_objects.append({"tag": name_kr, "location": visible_champions[name_kr]})
                elif name_kr in champion_last_positions:
                    final_minimap_objects.append({"tag": name_kr, "location": f"last_seen_{champion_last_positions[name_kr]}"})
                else:
                    final_minimap_objects.append({"tag": name_kr, "location": "Unknown"})

            final_data_for_log = serialize_game_state_for_log(all_data, final_minimap_objects, active_player_name, inferred_positions)

            elapsed = int(final_data_for_log["gameTime"])
            timestamp = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            print(f"\n===== [게임 경과 {timestamp}] 데이터 수집 =====")
            print(f"  - 플레이어 요약: {len(final_data_for_log['players'])}명")
            print(f"  - 미니맵 탐지/추적 결과: {final_data_for_log['detectedMinimapObjects']}")

            game_log[timestamp] = final_data_for_log
            try:
                print(f"  - 데이터를 '{log_path.resolve()}' 파일에 저장 시도 중...")
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(game_log, f, ensure_ascii=False, indent=4)
                print("  - 저장 완료.")
            except Exception as e:
                print(f"  - [오류] 파일 저장에 실패했습니다: {e}")

            notifier.check_events(final_data_for_log, game_events)

            time.sleep(POLL_GAME)

    except requests.exceptions.RequestException:
        print("✖ 게임 연결 끊김. 대기 상태로 전환.\n")
    except Exception as e:
        import traceback
        print(f"모니터링 중 치명적 오류 발생: {e}")
        traceback.print_exc()


# --- (wait_for_game_start, main 함수 - 변경 없음) ---
def wait_for_game_start():
    print("▶ 리그 오브 레전드 게임 시작 대기 중...")
    while True:
        base_url = find_live_client_url()
        if base_url:
            return base_url
        time.sleep(POLL_START)


def main():
    champion_name_map = get_champion_name_map()
    if not champion_name_map:
        print("챔피언 이름 정보를 가져오지 못해 프로그램을 종료합니다.")
        return
    MODEL_PATH = 'best.pt'
    try:
        detector = MinimapDetector(MODEL_PATH, show_preview=True)
    except Exception as e:
        print(f"오류: YOLO 모델('{MODEL_PATH}') 또는 mss 초기화 중 문제 발생.")
        print(f"상세 정보: {e}")
        return
    detection_thread = Thread(target=detector.start_detection_thread, args=(0.5,), daemon=True)
    detection_thread.start()
    try:
        while detection_thread.is_alive():
            base_url = wait_for_game_start()
            if base_url:
                monitor_game(base_url, detector, champion_name_map)
            if not detector.running:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다. (Ctrl+C)")
    finally:
        detector.stop()


if __name__ == "__main__":
    main()