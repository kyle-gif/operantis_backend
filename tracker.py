# ==============================================================================
# ★★★ PositionTracker 클래스 최종 완성본 (TypeError 수정) ★★★
# ==============================================================================
import itertools


class PositionTracker:
    def __init__(self):
        self.champion_positions = {}
        self.position_counters = {}
        # 서포터 전용 아이템 ID 목록 (시즌 14 기준)
        self.SUPPORT_ITEM_IDS = {
            4646,  # 세계의 아틀라스
            # 시즌 변경에 따라 다른 서포터 시작 아이템 ID 추가 가능
        }

    def update_sighting_counts(self, all_players, visible_champions):
        """미니맵에 보이는 챔피언들의 위치 카운트를 누적합니다."""
        for player in all_players:
            summoner_name = player.get('summonerName')
            if summoner_name and summoner_name not in self.position_counters:
                self.position_counters[summoner_name] = {'TOP': 0, 'MID': 0, 'BOT': 0}

        for champion_name, location in visible_champions.items():
            summoner_name = None
            for player in all_players:
                if player.get('championName') == champion_name:
                    summoner_name = player.get('summonerName')
                    break

            if not summoner_name:
                continue

            loc_lower = location.lower()
            if 'top' in loc_lower or '탑' in loc_lower:
                self.position_counters[summoner_name]['TOP'] += 1
            elif 'mid' in loc_lower or '미드' in loc_lower:
                self.position_counters[summoner_name]['MID'] += 1
            elif 'bot' in loc_lower or '봇' in loc_lower:
                self.position_counters[summoner_name]['BOT'] += 1

    def infer_and_assign_roles(self, all_players):
        """
        수집된 데이터를 바탕으로 팀별로 포지션을 중복 없이 최종 할당합니다.
        """
        teams = {'ORDER': [], 'CHAOS': []}
        for p in all_players:
            # 팀 정보가 없는 플레이어는 무시
            if p.get('team') in teams:
                teams[p.get('team')].append(p)

        final_roles = {}
        for team_name, team_players in teams.items():
            if len(team_players) != 5: continue

            assigned_in_team = {}
            unassigned_in_team = []

            # 1. 정글러, 서포터 우선 확정
            for p in team_players:
                summoner_name = p.get('summonerName')
                if not summoner_name: continue

                spells = p.get('spells', {})
                items = p.get('items', [])  # items는 딕셔너리의 리스트

                if '강타' in spells.get('spell1_name', '') or '강타' in spells.get('spell2_name', ''):
                    assigned_in_team[summoner_name] = 'JUNGLE'

                # ★★★ 핵심 수정: item 딕셔너리에서 'itemID'를 꺼내서 비교 ★★★
                elif any(item.get('itemID') in self.SUPPORT_ITEM_IDS for item in items):
                    assigned_in_team[summoner_name] = 'SUPPORT'
                else:
                    unassigned_in_team.append(summoner_name)

            # 2. 남은 라이너들에게 순차적으로 최적 포지션 할당
            available_lanes = ['TOP', 'MID', 'BOT']

            # 할당할 플레이어와 라인이 남아있는 동안 반복
            while unassigned_in_team and available_lanes:
                lane_to_assign = available_lanes.pop(0)  # 순서대로 TOP, MID, BOT 처리

                best_player_for_lane = None
                max_score = -1

                for summoner_name in unassigned_in_team:
                    score = self.position_counters.get(summoner_name, {}).get(lane_to_assign, 0)
                    if score > max_score:
                        max_score = score
                        best_player_for_lane = summoner_name

                if best_player_for_lane:
                    assigned_in_team[best_player_for_lane] = lane_to_assign
                    unassigned_in_team.remove(best_player_for_lane)
                # 만약 best_player_for_lane이 None이면 (모두 점수가 0), 그냥 첫번째 사람을 할당
                elif unassigned_in_team:
                    player_to_assign = unassigned_in_team.pop(0)
                    assigned_in_team[player_to_assign] = lane_to_assign

            final_roles.update(assigned_in_team)

        self.champion_positions = final_roles

    def get_positions(self):
        """현재까지 추론된 포지션 맵을 반환합니다."""
        return self.champion_positions