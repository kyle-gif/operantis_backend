import os
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from threading import Thread, Timer

load_dotenv()

FASTAPI_SERVER_URL = "http://127.0.0.1:8000/receive_llm_analysis"

# structire code mapping
STRUCTURE_ID_TO_NAME = {
    # Blue Team
    "Turret_T1_L_01_A": "Blue Top T1 Turret",
    "Turret_T2_L_02_A": "Blue Top T2 Turret",
    "Turret_T1_L_03_A": "Blue Top Inhibitor Turret",
    "Turret_T1_C_01_A": "Blue Mid T1 Turret",
    "Turret_T2_C_02_A": "Blue Mid T2 Turret",
    "Turret_T1_C_03_A": "Blue Mid Inhibitor Turret",
    "Turret_T1_R_01_A": "Blue Bot T1 Turret",
    "Turret_T2_R_02_A": "Blue Bot T2 Turret",
    "Turret_T1_R_03_A": "Blue Bot Inhibitor Turret",
    "Turret_T2_C_01_A": "Blue Nexus Turret (Top)",
    "Turret_T2_C_02_A": "Blue Nexus Turret (Bot)",
    "Barracks_L_01": "Blue Top Inhibitor",
    "Barracks_C_01": "Blue Mid Inhibitor",
    "Barracks_R_01": "Blue Bot Inhibitor",
    "Nexus_L_01": "Blue Nexus",

    # Red Team
    "Turret_T2_R_04_A": "Red Top T1 Turret",
    "Turret_T1_R_05_A": "Red Top T2 Turret",
    "Turret_T2_R_06_A": "Red Top Inhibitor Turret",
    "Turret_T2_C_03_A": "Red Mid T1 Turret",
    "Turret_T1_C_04_A": "Red Mid T2 Turret",
    "Turret_T2_C_05_A": "Red Mid Inhibitor Turret",
    "Turret_T2_L_04_A": "Red Bot T1 Turret",
    "Turret_T1_L_05_A": "Red Bot T2 Turret",
    "Turret_T2_L_06_A": "Red Bot Inhibitor Turret",
    "Turret_T2_C_03_A": "Red Nexus Turret (Top)",
    "Turret_T2_C_04_A": "Red Nexus Turret (Bot)",
    "Barracks_R_02": "Red Top Inhibitor",
    "Barracks_C_02": "Red Mid Inhibitor",
    "Barracks_L_02": "Red Bot Inhibitor",
    "Nexus_R_02": "Red Nexus",
}


class GameEventNotifier:
    def __init__(self, main_player_info):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[Warning] GOOGLE_API_KEY not found in .env file. LLM features will be disabled.")
            self.llm_enabled = False
            return

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.llm_enabled = True
        print("✔ LLM integration enabled (Gemini).")
        self.main_player_info = main_player_info
        self.previous_state = {}
        self.last_event_id = -1
        self.event_buffer = []
        self.event_timer: Timer = None
        self.EVENT_TIMER_DURATION = 5.0  # seconds

    def process_buffered_events(self):
        if not self.event_buffer or not self.llm_enabled:
            return
        print(f"[Event Grouping] Processing {len(self.event_buffer)} buffered events.")

        last_inferred_positions = self.previous_state.get('inferredPositions', {})
        team_context = self._create_team_context(self.previous_state, last_inferred_positions)
        self.trigger_llm_analysis(self.event_buffer, team_context, self.previous_state)
        self.event_buffer = []

    def check_for_new_events(self, current_state, game_events):
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

            print(f"  ... Scheduling LLM analysis in {self.EVENT_TIMER_DURATION} seconds (timer reset) ...")
            self.event_timer = Timer(self.EVENT_TIMER_DURATION, self.process_buffered_events)
            self.event_timer.start()

        self.previous_state = current_state

    def _check_system_events(self, game_events):
        new_events = []
        events_data = game_events.get('Events', [])
        for event in events_data:
            event_id = event.get('EventID', 0)
            if event_id > self.last_event_id:
                event_name = event.get('EventName')
                event_message = ""

                if event_name in ["DragonKill", "BaronKill", "HeraldKill"]:
                    killer_name = event.get('KillerName', 'Unknown')
                    obj_type = event.get('DragonType', event_name) if event_name == "DragonKill" else event_name
                    event_message = f"Objective Secured: {killer_name} killed {obj_type}."

                elif event_name == "TurretKilled":
                    killer_name = event.get('KillerName', 'Unknown')
                    structure_id = event.get('TurretKilled', 'Unknown Turret')
                    structure_name = STRUCTURE_ID_TO_NAME.get(structure_id, structure_id)
                    event_message = f"Structure Lost: {killer_name} destroyed '{structure_name}'."

                elif event_name == "InhibKilled":
                    killer_name = event.get('KillerName', 'Unknown')
                    structure_id = event.get('InhibKilled', 'Unknown Inhibitor')
                    structure_name = STRUCTURE_ID_TO_NAME.get(structure_id, structure_id)
                    event_message = f"Inhibitor Down: {killer_name} destroyed '{structure_name}'."

                if event_message:
                    print(f"[System Event Detected] {event_message}")
                    new_events.append(event_message)

        if events_data:
            self.last_event_id = events_data[-1].get('EventID', self.last_event_id)

        return new_events

    def _check_player_events(self, current_state):
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
                        event_message = (f"Player Kill: {current_player['championName']} ({summoner_name}) "
                                         f"got a kill! (KDA: {current_player['kda']})")
                        print(f"[Kill Event Detected] {event_message}")
                        new_events.append(event_message)
                except (ValueError, IndexError):
                    continue
        return new_events

    def _create_team_context(self, state, inferred_positions):
        team_context = {"ORDER": [], "CHAOS": []}
        position_order = {"TOP": 0, "JUNGLE": 1, "MID": 2, "BOT": 3, "UTILITY": 4, "UNKNOWN": 5}
        player_info_list = []
        for player in state.get('players', []):
            summoner_name = player.get('summonerName')
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

    def trigger_llm_analysis(self, events, team_context, full_game_state):
        event_summary = "\n- ".join(events)

        game_state_json = json.dumps(full_game_state, indent=2, ensure_ascii=False)

        prompt = f"""
        You are a Korean world-champion professional League of Legends player and analyst. You are known for your sharp, predictive insights and calm, strategic guidance.
        I am currently playing '{self.main_player_info['championName']}' on the {self.main_player_info['team']} team.

        Analyze the complete real-time game data provided below. Based on this data and the most recent events, give me one single, concise, and crucial piece of advice for what I, as '{self.main_player_info['championName']}', should focus on right now to maximize our chances of winning.

        Your advice must be a single sentence. Be direct and actionable.
        
        Always give advice with Korean.
        
        Do not say "End fast" or "빠르게 게임을 끝내세요", "게임을 끝내세요" or these kind of things. It gives stress.

        [Full Real-Time Game Data]
        ```json
        {game_state_json}
        ```

        {team_context}

        [Most Recent Events]
        - {event_summary}

        Your key advice for the '{self.main_player_info['championName']}' player (one sentence):
        """

        def gemini_and_post():
            try:
                response = self.model.generate_content(prompt)
                llm_response_text = response.text.strip()
                post_data = {"analysis_text": llm_response_text}
                api_response = requests.post(FASTAPI_SERVER_URL, json=post_data)
                api_response.raise_for_status()
                print(f"[LLM Analysis Sent] Advice: {llm_response_text}")
            except requests.exceptions.RequestException as e:
                print(f"[Error] Failed to send analysis to FastAPI server: {e}")
            except Exception as e:
                print(f"[Error] An error occurred during LLM analysis or posting: {e}")

        if self.llm_enabled:
            llm_thread = Thread(target=gemini_and_post)
            llm_thread.start()