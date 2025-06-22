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

ZONE_DEFINITIONS = [
    #Objects
    {"name": "Baron Pit", "coords": (0.355, 0.245), "radius": 0.06},
    {"name": "Dragon Pit", "coords": (0.645, 0.755), "radius": 0.06},

    #Jungle
    {"name": "Blue Team's Blue Buff", "coords": (0.185, 0.65), "radius": 0.045},
    {"name": "Blue Team's Red Buff", "coords": (0.37, 0.81), "radius": 0.045},
    {"name": "Red Team's Blue Buff", "coords": (0.815, 0.35), "radius": 0.045},
    {"name": "Red Team's Red Buff", "coords": (0.63, 0.19), "radius": 0.045},

    #Blue Team
    # Top Lane
    {"name": "Blue Top T1 Tower", "coords": (0.09, 0.28), "radius": 0.035},
    {"name": "Blue Top T2 Tower", "coords": (0.19, 0.47), "radius": 0.04},
    {"name": "Blue Top T3 Tower", "coords": (0.16, 0.64), "radius": 0.04},
    {"name": "Blue Top Inhibitor", "coords": (0.1, 0.71), "radius": 0.03},
    # Mid Lane
    {"name": "Blue Mid T1 Tower", "coords": (0.40, 0.60), "radius": 0.04},
    {"name": "Blue Mid T2 Tower", "coords": (0.32, 0.68), "radius": 0.04},
    {"name": "Blue Mid T3 Tower", "coords": (0.24, 0.76), "radius": 0.04},
    {"name": "Blue Mid Inhibitor", "coords": (0.17, 0.81), "radius": 0.03},
    # Bot Lane
    {"name": "Blue Bot T1 Tower", "coords": (0.72, 0.91), "radius": 0.035},
    {"name": "Blue Bot T2 Tower", "coords": (0.53, 0.81), "radius": 0.04},
    {"name": "Blue Bot T3 Tower", "coords": (0.35, 0.86), "radius": 0.04},
    {"name": "Blue Bot Inhibitor", "coords": (0.28, 0.9), "radius": 0.03},
    # Nexus
    {"name": "Blue Nexus Turret (Top)", "coords": (0.1, 0.85), "radius": 0.03},
    {"name": "Blue Nexus Turret (Bottom)", "coords": (0.15, 0.9), "radius": 0.03},
    {"name": "Blue Nexus", "coords": (0.07, 0.93), "radius": 0.04},

    #Red Team
    # Top Lane
    {"name": "Red Top T1 Tower", "coords": (0.28, 0.09), "radius": 0.035},
    {"name": "Red Top T2 Tower", "coords": (0.47, 0.19), "radius": 0.04},
    {"name": "Red Top T3 Tower", "coords": (0.64, 0.16), "radius": 0.04},
    {"name": "Red Top Inhibitor", "coords": (0.72, 0.1), "radius": 0.03},
    # Mid Lane
    {"name": "Red Mid T1 Tower", "coords": (0.60, 0.40), "radius": 0.04},
    {"name": "Red Mid T2 Tower", "coords": (0.68, 0.32), "radius": 0.04},
    {"name": "Red Mid T3 Tower", "coords": (0.76, 0.24), "radius": 0.04},
    {"name": "Red Mid Inhibitor", "coords": (0.83, 0.19), "radius": 0.03},
    # Bot Lane
    {"name": "Red Bot T1 Tower", "coords": (0.91, 0.72), "radius": 0.035},
    {"name": "Red Bot T2 Tower", "coords": (0.81, 0.53), "radius": 0.04},
    {"name": "Red Bot T3 Tower", "coords": (0.86, 0.35), "radius": 0.04},
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
POLL_START_INTERVAL = int(os.getenv("POLL_START_INTERVAL", 5))
POLL_GAME_INTERVAL = int(os.getenv("POLL_GAME_INTERVAL", 10))

def get_location(x_norm, y_norm):
    """
    Finds the name of the zone containing the given coordinates.
    If no exact zone contains the coordinates, it finds the nearest zone.
    """
    for zone in ZONE_DEFINITIONS:
        dist = np.sqrt((x_norm - zone["coords"][0]) ** 2 + (y_norm - zone["coords"][1]) ** 2)
        if dist <= zone["radius"]:
            return zone["name"]

    min_distance = float('inf')
    closest_zone_name = None

    for zone in ZONE_DEFINITIONS:
        dist = np.sqrt((x_norm - zone["coords"][0]) ** 2 + (y_norm - zone["coords"][1]) ** 2)
        if dist < min_distance:
            min_distance = dist
            closest_zone_name = zone["name"]

    if closest_zone_name:
        return f"near {closest_zone_name}"

    return "Unknown Area"


def get_full_game_data(base_url):
    resp = requests.get(f"{base_url}/allgamedata", verify=False)
    resp.raise_for_status()
    return resp.json()

def get_events(base_url):
    try:
        resp = requests.get(f"{base_url}/eventdata", verify=False)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException:
        return {"Events": []}

def find_api():
    for port in range(2997, 3003):
        base_api_url = f"https://127.0.0.1:{port}/liveclientdata"
        try:
            resp = requests.get(f"{base_api_url}/allgamedata", verify=False, timeout=1)
            if resp.status_code == 200:
                print(f"✔ Live Client API connected: {base_api_url}")
                return base_api_url
        except requests.exceptions.RequestException:
            continue
    return None

def build_champion_name_map():
    print("Fetching the latest champion data from Riot Data Dragon...")
    try:
        versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        latest_version = requests.get(versions_url).json()[0]
        print(f"Latest game version: {latest_version}")
        champion_data_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/champion.json"
        all_champions_data = requests.get(champion_data_url).json()['data']
        champion_map = {champ_id.lower(): champ_info['name'] for champ_id, champ_info in all_champions_data.items()}
        print(f"✔ Mapped {len(champion_map)} champion names (lowercase).")
        return champion_map
    except Exception as e:
        print(f"Error: Failed to fetch champion data: {e}")
        return None

def get_active_player_name(base_url):
    try:
        resp = requests.get(f"{base_url}/activeplayername", verify=False)
        resp.raise_for_status()
        return resp.text.strip('"')
    except requests.exceptions.RequestException as e:
        print(f"[Error] Failed to get active player name: {e}")
        return None

def prepare_log_entry(data, minimap_objects, active_player_name, inferred_positions):
    players_summary = []
    for p in data.get('allPlayers', []):
        summoner_name = p.get('summonerName')
        scores = p.get('scores', {})
        items = [item.get('itemID') for item in p.get('items', [])]
        spells_data = p.get('summonerSpells', {})
        spells = {"spell1": spells_data.get('summonerSpellOne', {}).get('displayName', 'N/A'),
                  "spell2": spells_data.get('summonerSpellTwo', {}).get('displayName', 'N/A')}
        runes_data = p.get('runes', {})
        runes = {"primary_style": runes_data.get('primaryRuneTreeDisplayName', 'N/A'),
                 "secondary_style": runes_data.get('secondaryRuneTreeDisplayName', 'N/A'),
                 "keystone": runes_data.get('keystone', {}).get('displayName', 'N/A')}
        position = inferred_positions.get(summoner_name, 'UNKNOWN')

        player_data = {
            "summonerName": summoner_name,
            "championName": p.get('championName'),
            "inferredRole": position,
            "team": p.get('team'),
            "level": p.get('level'),
            "kda": f"{scores.get('kills', 0)}/{scores.get('deaths', 0)}/{scores.get('assists', 0)}",
            "items": items,
            "spells": spells,
            "runes": runes,
            "isMainPlayer": summoner_name == active_player_name
        }
        players_summary.append(player_data)

    clean_data = {
        "gameTime": data.get("gameData", {}).get("gameTime", 0),
        "players": players_summary,
        "detectedMinimapObjects": minimap_objects,
        "inferredPlayerPositions": inferred_positions
    }
    return clean_data

def monitor(base_url, detector, champion_name_map):
    print("▶ Game in progress... Starting data collection.")
    log_path = Path("game_log.json")
    game_log = {}
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            try:
                game_log = json.load(f)
            except json.JSONDecodeError:
                game_log = {}

    active_player_name = get_active_player_name(base_url)
    main_player_info = {}
    print(f"Active Player: {active_player_name}")

    try:
        initial_data = get_full_game_data(base_url)
        for p in initial_data.get('allPlayers', []):
            if p.get('summonerName') == active_player_name:
                main_player_info = {
                    "name": active_player_name,
                    "championName": p.get('championName'),
                    "team": p.get('team')
                }
                print(f"Active Player Info: {main_player_info}")
                break
    except requests.exceptions.RequestException as e:
        print(f"Failed to load initial game data: {e}. Retrying shortly.")
        time.sleep(5)
        try:
            initial_data = get_full_game_data(base_url)
            for p in initial_data.get('allPlayers', []):
                if p.get('summonerName') == active_player_name:
                    main_player_info = {"name": active_player_name, "championName": p.get('championName'), "team": p.get('team')}
        except requests.exceptions.RequestException:
             print("[Error] Failed to initialize player data. Exiting.")
             return

    position_tracker = PositionTracker()
    notifier = GameEventNotifier(main_player_info)
    champion_last_positions = {}

    try:
        while detector.running:
            data = get_full_game_data(base_url)
            game_events = get_events(base_url)

            current_champion_names = {p['championName'] for p in data.get('allPlayers', []) if p.get('championName')}
            if not current_champion_names:
                time.sleep(POLL_GAME_INTERVAL)
                continue

            raw_detections = detector.get_detected_objects()
            visible_champions = {}
            for obj in raw_detections:
                champion_id = obj['tag'].lower()
                champion_name = champion_name_map.get(champion_id)
                if champion_name and champion_name in current_champion_names:
                    location = get_location(obj['x_norm'], obj['y_norm'])
                    visible_champions[champion_name] = location
                    champion_last_positions[champion_name] = location

            position_tracker.update_sighting_counts(data.get('allPlayers', []), visible_champions)
            position_tracker.infer_and_assign_roles(data.get('allPlayers', []))
            inferred_positions = position_tracker.get_positions()

            final_minimap_objects = []
            for name in sorted(list(current_champion_names)):
                if name in visible_champions:
                    final_minimap_objects.append({"champion": name, "location": visible_champions[name]})
                elif name in champion_last_positions:
                    final_minimap_objects.append({"champion": name, "location": f"last seen {champion_last_positions[name]}"})
                else:
                    final_minimap_objects.append({"champion": name, "location": "Unknown"})

            log_entry = prepare_log_entry(data, final_minimap_objects, active_player_name, inferred_positions)

            elapsed = int(log_entry["gameTime"])
            timestamp = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            print(f"\n==========[Game Time {timestamp}] Data Snapshot=============")
            print(f"  - Player Summary: {len(log_entry['players'])} players")
            print(f"  - Minimap Detections/Tracking: {log_entry['detectedMinimapObjects']}")

            game_log[timestamp] = log_entry
            try:
                print(f"  - Attempting to save data to '{log_path.resolve()}'...")
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(game_log, f, ensure_ascii=False, indent=4)
                print("  - Save complete.")
            except Exception as e:
                print(f"  - [Error] Failed to save file: {e}")

            notifier.check_for_new_events(log_entry, game_events)

            time.sleep(POLL_GAME_INTERVAL)

    except requests.exceptions.RequestException:
        print("✖ Game connection lost. Returning to wait state.\n")
    except Exception as e:
        import traceback
        print(f"A critical error occurred during monitoring: {e}")
        traceback.print_exc()

def await_game_start():
    print("▶ Waiting for League of Legends game to start...")
    while True:
        base_url = find_api()
        if base_url:
            return base_url
        time.sleep(POLL_START_INTERVAL)

def main():
    champion_name_map = build_champion_name_map()
    if not champion_name_map:
        print("Could not retrieve champion name data. Exiting program.")
        return
    MODEL_PATH = 'best_8.pt'
    try:
        detector = MinimapDetector(MODEL_PATH, show_preview=False)
    except Exception as e:
        print(f"Error: Problem initializing YOLO model ('{MODEL_PATH}') or mss.")
        print(f"Details: {e}")
        return
    detection_thread = Thread(target=detector.start_detection_thread, args=(0.5,), daemon=True)
    detection_thread.start()
    try:
        while detection_thread.is_alive():
            base_url = await_game_start()
            if base_url:
                monitor(base_url, detector, champion_name_map)
            if not detector.running:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting program. (Ctrl+C)")
    finally:
        detector.stop()

if __name__ == "__main__":
    main()