import random
import time
import json
import os
import re
import sys
from datetime import datetime
from collections import Counter
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog


def get_app_dir() -> str:
    """Return the directory of the executable (if frozen) or the script file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class Theme:
    """Modern, bright light-mode dashboard color palette."""
    BG_DARKEST = "#ffffff"       # Crisp white top bar / banner surface
    BG_MAIN = "#f1f5f9"          # Airy cool-slate main app background
    BG_CARD = "#ffffff"          # Pure white card surface
    BG_CARD_HEADER = "#f8fafc"   # Soft slate card header / toolbar surface
    BG_ROW_ALT = "#f8fafc"       # Subtle alternating row / player pod strip
    BG_INPUT = "#ffffff"         # Clean white input fields
    BORDER = "#cbd5e1"           # Crisp slate border
    BORDER_LIGHT = "#94a3b8"     # Stronger accent border

    TEXT_PRIMARY = "#0f172a"     # Deep slate-black primary text
    TEXT_SECONDARY = "#334155"   # Medium-dark slate secondary text
    TEXT_MUTED = "#64748b"       # Muted slate helper text
    TEXT_DISABLED = "#94a3b8"    # Soft gray disabled text

    CRIMSON = "#e11d48"
    CRIMSON_HOVER = "#be123c"
    EMERALD = "#10b981"
    EMERALD_HOVER = "#059669"
    EMERALD_TEXT = "#15803d"
    BLUE = "#2563eb"
    BLUE_HOVER = "#1d4ed8"
    VIOLET = "#7c3aed"
    VIOLET_HOVER = "#6d28d9"
    AMBER = "#f59e0b"
    AMBER_HOVER = "#d97706"
    AMBER_TEXT = "#b45309"
    SLATE_BTN = "#475569"
    SLATE_BTN_HOVER = "#334155"
    DANGER = "#ef4444"
    DANGER_HOVER = "#dc2626"

    GOLD = "#f59e0b"
    SILVER = "#64748b"
    BRONZE = "#d97706"


class Player:
    def __init__(self, name: str, is_rdv: bool = False):
        self.name = name
        self.points = 0
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.opponents = Counter()  # {opponent_name: times_played}
        self.dropped = False
        self.is_rdv = is_rdv
        self.paid = True if is_rdv else False  # RDV tagged players are always paid by default
        self.locked_table: int | None = None  # 0-based index of locked table/pod, or None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "points": self.points,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "opponents": dict(self.opponents),
            "dropped": self.dropped,
            "is_rdv": self.is_rdv,
            "paid": self.paid,
            "locked_table": self.locked_table
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Player':
        p = cls(data["name"], is_rdv=data.get("is_rdv", False))
        p.points = data.get("points", 0)
        p.wins = data.get("wins", 0)
        p.draws = data.get("draws", 0)
        p.losses = data.get("losses", 0)
        p.opponents = Counter(data.get("opponents", {}))
        p.dropped = data.get("dropped", False)
        p.paid = True if p.is_rdv else data.get("paid", False)
        p.locked_table = data.get("locked_table", None)
        return p


class Team2HG:
    def __init__(self, player1: str, player2: str):
        self.player1 = player1
        self.player2 = player2
        self.points = 0
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.opponents = Counter()  # {other_team_name: times_played}
        self.dropped = False
        self.locked_table: int | None = None

    @property
    def name(self) -> str:
        return f"{self.player1} & {self.player2}"

    def to_dict(self) -> dict:
        return {
            "player1": self.player1,
            "player2": self.player2,
            "points": self.points,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "opponents": dict(self.opponents),
            "dropped": self.dropped,
            "locked_table": self.locked_table
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Team2HG':
        t = cls(data["player1"], data["player2"])
        t.points = data.get("points", 0)
        t.wins = data.get("wins", 0)
        t.draws = data.get("draws", 0)
        t.losses = data.get("losses", 0)
        t.opponents = Counter(data.get("opponents", {}))
        t.dropped = data.get("dropped", False)
        t.locked_table = data.get("locked_table", None)
        return t


class CommanderEvent:
    STATE_FILE = os.path.join(get_app_dir(), "rdvccc_state.json")

    def __init__(self):
        self.players: dict[str, Player] = {}
        self.current_pods: list[list[Player]] = []
        self.pod_outcomes: list[dict | None] = []
        self.pod_warnings: list[str] = []
        self.round_history: list[dict] = []
        self.round_number = 0
        self.max_rounds = 3
        self.random_winners: list[str] = []
        self.global_swap_selection: tuple[int, Player] | None = None
        self.global_team_swap_selection: tuple[int, Team2HG] | None = None

        # Two-Headed Giant State
        self.is_2hg_mode = False
        self.teams_2hg: list[Team2HG] = []

    def get_player_team(self, player_name: str) -> Team2HG | None:
        for team in self.teams_2hg:
            if team.player1 == player_name or team.player2 == player_name:
                return team
        return None

    def get_player_team_index(self, player_name: str) -> int | None:
        for idx, team in enumerate(self.teams_2hg):
            if team.player1 == player_name or team.player2 == player_name:
                return idx + 1
        return None

    def get_pod_teams_2hg(self, pod: list[Player]) -> list[Team2HG]:
        """Extract ordered Team2HG objects from a pod's player list (paired in 2s)."""
        teams: list[Team2HG] = []
        for idx in range(0, len(pod) - 1, 2):
            p1, p2 = pod[idx], pod[idx + 1]
            t_name = f"{p1.name} & {p2.name}"
            t_obj = next((t for t in self.teams_2hg if t.name == t_name), None)
            if not t_obj:
                t_obj = self.get_player_team(p1.name)
            if t_obj and t_obj not in teams:
                teams.append(t_obj)
        return teams

    def _build_round_snapshot(self, round_num: int, pods: list[list[Player]], outcomes: list[dict | None]) -> dict:
        """Create a serializable summary of a round's matchups and results."""
        matches = []
        for i, pod in enumerate(pods):
            outcome = outcomes[i] if i < len(outcomes) else None
            is_bye = (outcome is not None and outcome.get("type") == "BYE")

            if self.is_2hg_mode:
                pod_teams = self.get_pod_teams_2hg(pod)
                participants = [t.name for t in pod_teams]
                if outcome is None:
                    outcome_type = "IN_PROGRESS"
                    winner_name = None
                elif outcome["type"] == "BYE":
                    outcome_type = "BYE"
                    wt = outcome.get("winner_team")
                    winner_name = wt.name if isinstance(wt, Team2HG) else (str(wt) if wt else (participants[0] if participants else None))
                elif outcome["type"] == "DRAW":
                    outcome_type = "DRAW"
                    winner_name = None
                else:
                    outcome_type = "WIN"
                    wt = outcome.get("winner_team")
                    winner_name = wt.name if isinstance(wt, Team2HG) else (str(wt) if wt else None)
            else:
                participants = [p.name for p in pod]
                if outcome is None:
                    outcome_type = "IN_PROGRESS"
                    winner_name = None
                elif outcome["type"] == "DRAW":
                    outcome_type = "DRAW"
                    winner_name = None
                else:
                    outcome_type = "WIN"
                    wp = outcome.get("winner")
                    winner_name = wp.name if isinstance(wp, Player) else (str(wp) if wp else None)

            matches.append({
                "table": i + 1,
                "is_bye": is_bye,
                "participants": participants,
                "outcome_type": outcome_type,
                "winner_name": winner_name
            })

        return {
            "round": round_num,
            "is_2hg": self.is_2hg_mode,
            "matches": matches
        }

    def get_all_rounds_summary(self) -> list[dict]:
        """Return chronological snapshots of all prior rounds plus the active round."""
        rounds_map: dict[int, dict] = {}
        for r_snap in self.round_history:
            r_num = r_snap.get("round", 0)
            if r_num > 0:
                rounds_map[r_num] = r_snap

        if self.round_number > 0 and self.current_pods:
            rounds_map[self.round_number] = self._build_round_snapshot(
                self.round_number, self.current_pods, self.pod_outcomes
            )

        return [rounds_map[k] for k in sorted(rounds_map.keys())]

    def format_match_history_text(self) -> str:
        """Generate a clean, easily readable plain-text report of the night's matchups and winners."""
        now = datetime.now()
        date_display = now.strftime("%d/%m/%Y")
        mode_str = "Two-Headed Giant (2HG)" if self.is_2hg_mode else "Commander Pods"

        lines = [
            "========================================================================",
            f"  RED DRAGON'S VAULT — COMMANDER FNM ({date_display})",
            f"  Format: {mode_str}",
            "========================================================================",
            ""
        ]

        rounds_summary = self.get_all_rounds_summary()
        for r_data in rounds_summary:
            r_num = r_data.get("round", 1)
            matches = r_data.get("matches", [])
            lines.append(f"------------------------------------------------------------------------")
            lines.append(f"  ROUND {r_num}")
            lines.append(f"------------------------------------------------------------------------")

            for m in matches:
                t_num = m.get("table", 1)
                is_bye = m.get("is_bye", False)
                outcome_type = m.get("outcome_type", "IN_PROGRESS")
                winner_name = m.get("winner_name")
                participants = m.get("participants", [])

                table_label = "BYE POD" if is_bye else f"Table {t_num}"
                if outcome_type == "BYE":
                    res_str = f"Automatic Bye — {winner_name} (+3 pts)"
                elif outcome_type == "WIN":
                    res_str = f"Winner: {winner_name} (+3 pts)"
                elif outcome_type == "DRAW":
                    res_str = "Match Draw (+1 pt each)" if r_data.get("is_2hg") else "Pod Draw (+1 pt each)"
                else:
                    res_str = "In Progress"

                lines.append(f"  {table_label}: {res_str}")
                for part_name in participants:
                    is_win = (outcome_type in ("WIN", "BYE") and part_name == winner_name)
                    if is_win:
                        tag = "[WIN] "
                    elif outcome_type == "DRAW":
                        tag = "[DRAW]"
                    else:
                        tag = "  •   "
                    lines.append(f"      {tag} {part_name}")
                lines.append("")

        # Standings Summary Section
        lines.append("========================================================================")
        lines.append("  STANDINGS SUMMARY")
        lines.append("========================================================================")
        if self.is_2hg_mode:
            sorted_teams = self.get_sorted_teams_standings()
            for idx, t in enumerate(sorted_teams, start=1):
                opp_pts = self.get_team_opponent_points(t)
                record = f"{t.wins}-{t.losses}-{t.draws}"
                p1 = self.players.get(t.player1)
                p2 = self.players.get(t.player2)
                has_rdv = (p1 and p1.is_rdv) or (p2 and p2.is_rdv)
                rdv_tag = " [RDV]" if has_rdv else ""
                drop_tag = " [DROPPED]" if t.dropped else ""
                lines.append(
                    f"  #{idx:<3} {t.name}{rdv_tag}{drop_tag} — {t.points} pts "
                    f"(Opp Pts: {opp_pts} | W-L-D: {record})"
                )
        else:
            sorted_players = self.get_sorted_standings()
            for idx, p in enumerate(sorted_players, start=1):
                opp_pts = self.get_opponent_points(p)
                record = f"{p.wins}-{p.losses}-{p.draws}"
                rdv_tag = " [RDV]" if p.is_rdv else ""
                drop_tag = " [DROPPED]" if p.dropped else ""
                lines.append(
                    f"  #{idx:<3} {p.name}{rdv_tag}{drop_tag} — {p.points} pts "
                    f"(Opp Pts: {opp_pts} | W-L-D: {record})"
                )

        if self.random_winners:
            lines.append("")
            lines.append("========================================================================")
            lines.append("  RANDOM PRIZE WHEEL WINNERS")
            lines.append("========================================================================")
            for idx, w_name in enumerate(self.random_winners, start=1):
                lines.append(f"  {idx}. {w_name}")

        lines.append("")
        return "\n".join(lines)

    def _apply_bye_2hg(self, pod_index: int, team: Team2HG):
        """Award automatic +3 pts and +1 win to a 2HG team placed in the Bye pod."""
        team.points += 3
        team.wins += 1
        team.opponents["BYE"] += 1
        for p_name in (team.player1, team.player2):
            if p_name in self.players:
                self.players[p_name].points += 3
                self.players[p_name].wins += 1
        self.pod_outcomes[pod_index] = {"type": "BYE", "winner_team": team}

    def _revert_bye_2hg(self, pod_index: int):
        """Revert automatic +3 pts and +1 win from a 2HG team when swapped out or re-podded."""
        if pod_index < 0 or pod_index >= len(self.pod_outcomes):
            return
        outcome = self.pod_outcomes[pod_index]
        if not outcome or outcome.get("type") != "BYE":
            return
        team = outcome.get("winner_team")
        if team:
            team.points -= 3
            team.wins -= 1
            team.opponents["BYE"] -= 1
            if team.opponents["BYE"] <= 0:
                del team.opponents["BYE"]
            for p_name in (team.player1, team.player2):
                if p_name in self.players:
                    self.players[p_name].points -= 3
                    self.players[p_name].wins -= 1
        self.pod_outcomes[pod_index] = None

    def save_state(self):
        try:
            state_data = {
                "round_number": self.round_number,
                "random_winners": self.random_winners,
                "is_2hg_mode": self.is_2hg_mode,
                "teams_2hg": [t.to_dict() for t in self.teams_2hg],
                "players": {name: p.to_dict() for name, p in self.players.items()},
                "current_pods": [[p.name for p in pod] for pod in self.current_pods],
                "pod_outcomes": [
                    (
                        None if o is None
                        else {
                            "type": o["type"],
                            "winner": (
                                o["winner"].name
                                if isinstance(o.get("winner"), Player)
                                else o.get("winner")
                            ),
                            "winner_team": (
                                o["winner_team"].name
                                if isinstance(o.get("winner_team"), Team2HG)
                                else o.get("winner_team")
                            )
                        }
                    )
                    for o in self.pod_outcomes
                ],
                "pod_warnings": self.pod_warnings,
                "round_history": self.round_history
            }
            temp_file = f"{self.STATE_FILE}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
            os.replace(temp_file, self.STATE_FILE)
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_state(self) -> bool:
        if not os.path.exists(self.STATE_FILE):
            return False
        try:
            with open(self.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.round_number = data.get("round_number", 0)
            self.random_winners = data.get("random_winners", [])
            self.is_2hg_mode = data.get("is_2hg_mode", False)
            self.teams_2hg = [Team2HG.from_dict(t_data) for t_data in data.get("teams_2hg", [])]
            self.round_history = data.get("round_history", [])

            self.players = {
                name: Player.from_dict(p_data)
                for name, p_data in data.get("players", {}).items()
            }

            raw_pods = data.get("current_pods", [])
            self.current_pods = []
            for pod_names in raw_pods:
                pod_objs = [self.players[name] for name in pod_names if name in self.players]
                if pod_objs:
                    self.current_pods.append(pod_objs)

            raw_outcomes = data.get("pod_outcomes", [])
            self.pod_outcomes = []
            for o in raw_outcomes:
                if o is None:
                    self.pod_outcomes.append(None)
                else:
                    if self.is_2hg_mode:
                        wt_name = o.get("winner_team")
                        winner_team_obj = next((t for t in self.teams_2hg if t.name == wt_name), None) if wt_name else None
                        self.pod_outcomes.append({"type": o["type"], "winner_team": winner_team_obj})
                    else:
                        winner_name = o.get("winner")
                        winner_obj = self.players.get(winner_name) if winner_name else None
                        self.pod_outcomes.append({"type": o["type"], "winner": winner_obj})

            if len(self.pod_outcomes) != len(self.current_pods):
                self.pod_outcomes = [None] * len(self.current_pods)

            self.recalculate_warnings()
            self.global_swap_selection = None
            self.global_team_swap_selection = None
            return True
        except Exception as e:
            print(f"Error loading state: {e}")
            return False

    @classmethod
    def clear_saved_state(cls):
        for path in (cls.STATE_FILE, f"{cls.STATE_FILE}.tmp"):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    @staticmethod
    def _parse_raw_name(raw_name: str, default_rdv: bool = False) -> tuple[str, bool]:
        name = raw_name.strip()
        if not name:
            return "", default_rdv

        is_rdv = default_rdv

        if name.endswith("*"):
            is_rdv = True
            name = name[:-1].strip()
        elif re.match(r"^rdv\s+", name, flags=re.IGNORECASE):
            is_rdv = True
            name = re.sub(r"^rdv\s+", "", name, flags=re.IGNORECASE).strip()
        elif re.search(r"\s+rdv$", name, flags=re.IGNORECASE):
            is_rdv = True
            name = re.sub(r"\s+rdv$", "", name, flags=re.IGNORECASE).strip()
        elif re.search(r"\(rdv\)", name, flags=re.IGNORECASE):
            is_rdv = True
            name = re.sub(r"\s*\(rdv\)\s*", " ", name, flags=re.IGNORECASE).strip()

        return name, is_rdv

    def add_player(self, raw_name: str) -> tuple[bool, str]:
        name, is_rdv = self._parse_raw_name(raw_name, default_rdv=False)
        if not name:
            return False, "Empty name."

        if name.lower() in (p.lower() for p in self.players):
            return False, f"'{name}' is already registered."

        self.players[name] = Player(name, is_rdv=is_rdv)
        tag_str = " (RDV Tagged)" if is_rdv else ""
        self.save_state()
        return True, f"Added {name}{tag_str}"

    def edit_player_name(self, old_name: str, new_raw_name: str) -> tuple[bool, str]:
        if old_name not in self.players:
            return False, f"Player '{old_name}' not found."

        player = self.players[old_name]
        new_name, is_rdv = self._parse_raw_name(new_raw_name, default_rdv=player.is_rdv)

        if not new_name:
            return False, "Empty name."

        if new_name == old_name and is_rdv == player.is_rdv:
            return True, f"No changes made to '{old_name}'."

        if new_name.lower() != old_name.lower() and new_name.lower() in (p.lower() for p in self.players):
            return False, f"'{new_name}' is already registered."

        updated_players = {}
        for k, v in self.players.items():
            if k == old_name:
                v.name = new_name
                v.is_rdv = is_rdv
                if is_rdv:
                    v.paid = True
                updated_players[new_name] = v
            else:
                updated_players[k] = v
        self.players = updated_players

        if old_name != new_name:
            for p in self.players.values():
                if old_name in p.opponents:
                    p.opponents[new_name] = p.opponents.pop(old_name)

            team_renames: dict[str, str] = {}
            for team in self.teams_2hg:
                old_team_name = team.name
                if team.player1 == old_name:
                    team.player1 = new_name
                if team.player2 == old_name:
                    team.player2 = new_name
                new_team_name = team.name
                if old_team_name != new_team_name:
                    team_renames[old_team_name] = new_team_name
                    for other_t in self.teams_2hg:
                        if old_team_name in other_t.opponents:
                            other_t.opponents[new_team_name] = other_t.opponents.pop(old_team_name)
                    self.random_winners = [new_team_name if w == old_team_name else w for w in self.random_winners]

            self.random_winners = [new_name if w == old_name else w for w in self.random_winners]

            # Update historical round snapshots if a player/team was renamed
            for r_snap in self.round_history:
                for m in r_snap.get("matches", []):
                    if r_snap.get("is_2hg"):
                        m["participants"] = [team_renames.get(part, part) for part in m.get("participants", [])]
                        if m.get("winner_name") in team_renames:
                            m["winner_name"] = team_renames[m["winner_name"]]
                    else:
                        m["participants"] = [new_name if part == old_name else part for part in m.get("participants", [])]
                        if m.get("winner_name") == old_name:
                            m["winner_name"] = new_name

        self.recalculate_warnings()
        self.save_state()
        return True, f"Successfully renamed '{old_name}' to '{new_name}'."

    def drop_player(self, name: str) -> tuple[bool, str]:
        if name not in self.players:
            return False, f"Player '{name}' not found."
        player = self.players[name]
        if player.dropped:
            return False, f"'{name}' has already been dropped."
        player.dropped = True

        if self.is_2hg_mode:
            team = self.get_player_team(name)
            if team:
                if self.round_number == 0:
                    p1 = self.players.get(team.player1)
                    p2 = self.players.get(team.player2)
                    if p1:
                        p1.locked_table = None
                    if p2:
                        p2.locked_table = None
                    self.teams_2hg.remove(team)
                    self.save_state()
                    return True, f"'{name}' dropped. Their 2HG team was disbanded, table locks cleared, and their partner is unassigned."
                else:
                    team.dropped = True
                    p1 = self.players.get(team.player1)
                    p2 = self.players.get(team.player2)
                    if p1:
                        p1.dropped = True
                    if p2:
                        p2.dropped = True
                    self.save_state()
                    return True, f"'{name}' and their 2HG team ('{team.name}') have been dropped from future rounds."

        self.save_state()
        return True, f"'{name}' has been dropped from future rounds."

    def toggle_rdv(self, name: str) -> tuple[bool, str]:
        if name not in self.players:
            return False, f"Player '{name}' not found."
        player = self.players[name]
        player.is_rdv = not player.is_rdv
        if player.is_rdv:
            player.paid = True
        status = "tagged as RDV (Paid enforced)" if player.is_rdv else "untagged from RDV"
        self.save_state()
        return True, f"'{player.name}' has been {status}."

    def toggle_paid(self, name: str) -> tuple[bool, str]:
        if name not in self.players:
            return False, f"Player '{name}' not found."
        player = self.players[name]
        if player.is_rdv:
            return False, "Players with an RDV tag must always maintain paid status."
        player.paid = not player.paid
        status = "Entry Paid" if player.paid else "Not Paid"
        self.save_state()
        return True, f"'{player.name}' status changed to: {status}."

    def get_active_players(self) -> list[Player]:
        return [p for p in self.players.values() if not p.dropped]

    def get_assigned_2hg_players(self) -> set[str]:
        assigned = set()
        for t in self.teams_2hg:
            if not t.dropped:
                assigned.add(t.player1)
                assigned.add(t.player2)
        return assigned

    def get_opponent_points(self, player: Player) -> int:
        if self.is_2hg_mode:
            team = self.get_player_team(player.name)
            if team:
                return self.get_team_opponent_points(team)
        return sum(
            self.players[opp_name].points * count
            for opp_name, count in player.opponents.items()
            if opp_name in self.players
        )

    def get_team_opponent_points(self, team: Team2HG) -> int:
        return sum(
            next((t.points * count for t in self.teams_2hg if t.name == opp_name), 0)
            for opp_name, count in team.opponents.items()
        )

    def get_sorted_standings(self) -> list[Player]:
        all_players = list(self.players.values())
        active_list = [p for p in all_players if not p.dropped]
        dropped_list = [p for p in all_players if p.dropped]

        active_list.sort(key=lambda p: (p.points, self.get_opponent_points(p)), reverse=True)
        dropped_list.sort(key=lambda p: (p.points, self.get_opponent_points(p)), reverse=True)
        return active_list + dropped_list

    def get_sorted_teams_standings(self) -> list[Team2HG]:
        all_teams = list(self.teams_2hg)
        active_list = [t for t in all_teams if not t.dropped]
        dropped_list = [t for t in all_teams if t.dropped]

        active_list.sort(key=lambda t: (t.points, self.get_team_opponent_points(t)), reverse=True)
        dropped_list.sort(key=lambda t: (t.points, self.get_team_opponent_points(t)), reverse=True)
        return active_list + dropped_list

    def get_top_3_eligible(self) -> list[Player]:
        sorted_all = self.get_sorted_standings()
        eligible = [p for p in sorted_all if not p.is_rdv]
        return eligible[:3]

    def get_top_3_eligible_teams(self) -> list[Team2HG]:
        sorted_all = self.get_sorted_teams_standings()
        eligible = []
        for t in sorted_all:
            p1 = self.players.get(t.player1)
            p2 = self.players.get(t.player2)
            if (not p1 or not p1.is_rdv) and (not p2 or not p2.is_rdv):
                eligible.append(t)
        return eligible[:3]

    def get_wheel_pool(self) -> list[str]:
        if self.is_2hg_mode:
            top3_names = {t.name for t in self.get_top_3_eligible_teams()}
            prior_winners = set(self.random_winners)
            return [
                t.name for t in self.teams_2hg
                if not t.dropped and t.name not in top3_names and t.name not in prior_winners
                and not any(self.players.get(p, Player(p)).is_rdv for p in (t.player1, t.player2))
            ]
        else:
            top3_names = {p.name for p in self.get_top_3_eligible()}
            prior_winners = set(self.random_winners)
            return [
                p.name for p in self.players.values()
                if not p.dropped and not p.is_rdv and p.name not in top3_names and p.name not in prior_winners
            ]

    def is_tournament_complete(self) -> bool:
        return (
            self.round_number == self.max_rounds
            and bool(self.current_pods)
            and all(o is not None for o in self.pod_outcomes)
        )

    def _calculate_pod_sizes(self, num_players: int) -> list[int]:
        if num_players == 5:
            return [5]
        remainder = num_players % 4
        num_threes = {0: 0, 1: 3, 2: 2, 3: 1}[remainder]
        num_fours = (num_players - (num_threes * 3)) // 4
        return [4] * num_fours + [3] * num_threes

    def _pod_cost(self, pod: list[Player]) -> int:
        cost = 0
        n = len(pod)
        for i in range(n):
            p1 = pod[i]
            for j in range(i + 1, n):
                p2 = pod[j]
                repeats = p1.opponents[p2.name]
                if repeats:
                    cost += (repeats ** 2) * 500
                pts_diff = p1.points - p2.points
                if pts_diff:
                    cost += (pts_diff ** 2) * 10
        return cost

    def _team_pod_cost(self, team_pod: list[Team2HG]) -> int:
        cost = 0
        n = len(team_pod)
        for i in range(n):
            t1 = team_pod[i]
            for j in range(i + 1, n):
                t2 = team_pod[j]
                repeats = t1.opponents[t2.name]
                if repeats:
                    cost += (repeats ** 2) * 500
                pts_diff = t1.points - t2.points
                if pts_diff:
                    cost += (pts_diff ** 2) * 10
        return cost

    def _optimize_pods(self, pods: list[list[Player]]):
        improved = True
        iterations = 0
        max_iterations = 100
        num_pods = len(pods)

        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            for i in range(num_pods):
                for j in range(i + 1, num_pods):
                    base_cost = self._pod_cost(pods[i]) + self._pod_cost(pods[j])
                    if base_cost == 0:
                        continue
                    for p1_idx in range(len(pods[i])):
                        for p2_idx in range(len(pods[j])):
                            p1 = pods[i][p1_idx]
                            p2 = pods[j][p2_idx]
                            if p1.locked_table is not None or p2.locked_table is not None:
                                continue

                            pods[i][p1_idx], pods[j][p2_idx] = pods[j][p2_idx], pods[i][p1_idx]
                            new_cost = self._pod_cost(pods[i]) + self._pod_cost(pods[j])
                            if new_cost < base_cost:
                                base_cost = new_cost
                                improved = True
                            else:
                                pods[i][p1_idx], pods[j][p2_idx] = pods[j][p2_idx], pods[i][p1_idx]

    def _optimize_2hg_pods(self, team_pods: list[list[Team2HG]]):
        improved = True
        iterations = 0
        max_iterations = 100
        num_pods = len(team_pods)

        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            for i in range(num_pods):
                for j in range(i + 1, num_pods):
                    base_cost = self._team_pod_cost(team_pods[i]) + self._team_pod_cost(team_pods[j])
                    if base_cost == 0:
                        continue
                    for t1_idx in range(len(team_pods[i])):
                        for t2_idx in range(len(team_pods[j])):
                            t1 = team_pods[i][t1_idx]
                            t2 = team_pods[j][t2_idx]
                            if t1.locked_table is not None or t2.locked_table is not None:
                                continue

                            team_pods[i][t1_idx], team_pods[j][t2_idx] = team_pods[j][t2_idx], team_pods[i][t1_idx]
                            new_cost = self._team_pod_cost(team_pods[i]) + self._team_pod_cost(team_pods[j])
                            if new_cost < base_cost:
                                base_cost = new_cost
                                improved = True
                            else:
                                team_pods[i][t1_idx], team_pods[j][t2_idx] = team_pods[j][t2_idx], team_pods[i][t1_idx]

    def recalculate_warnings(self):
        self.pod_warnings = [""] * len(self.current_pods)

    def _generate_pods_for_round(self, target_round: int):
        if self.is_2hg_mode:
            active_teams = [
                t for t in self.teams_2hg
                if not t.dropped
                and t.player1 in self.players
                and t.player2 in self.players
                and not self.players[t.player1].dropped
                and not self.players[t.player2].dropped
            ]
            num_teams = len(active_teams)
            if num_teams < 1:
                self.current_pods = []
                self.pod_outcomes = []
                return

            has_bye = (num_teams % 2 == 1)
            bye_team: Team2HG | None = None

            locked_teams = [t for t in active_teams if t.locked_table is not None]
            unlocked_teams = [t for t in active_teams if t.locked_table is None]

            if has_bye:
                bye_candidates = unlocked_teams if unlocked_teams else locked_teams
                if target_round == 1:
                    bye_team = random.choice(bye_candidates)
                else:
                    bye_candidates_sorted = sorted(
                        bye_candidates,
                        key=lambda t: (t.opponents["BYE"], t.points, self.get_team_opponent_points(t))
                    )
                    bye_team = bye_candidates_sorted[0]

                if bye_team in unlocked_teams:
                    unlocked_teams.remove(bye_team)
                elif bye_team in locked_teams:
                    locked_teams.remove(bye_team)

            num_tables = (len(locked_teams) + len(unlocked_teams)) // 2
            team_pods: list[list[Team2HG]] = [[] for _ in range(num_tables)]

            locked_teams.sort(key=lambda t: (t.points, self.get_team_opponent_points(t)), reverse=True)

            assigned_table_indices = set()
            for t in locked_teams:
                if num_tables == 0:
                    break
                target_idx = t.locked_table
                if target_idx < 0:
                    target_idx = 0
                if target_idx >= num_tables:
                    target_idx = num_tables - 1

                if target_idx in assigned_table_indices or len(team_pods[target_idx]) >= 2:
                    found = False
                    for offset in range(1, num_tables):
                        for candidate in (target_idx + offset, target_idx - offset):
                            if 0 <= candidate < num_tables and candidate not in assigned_table_indices and len(team_pods[candidate]) < 2:
                                target_idx = candidate
                                found = True
                                break
                        if found:
                            break

                team_pods[target_idx].append(t)
                assigned_table_indices.add(target_idx)

            if target_round > 1:
                unlocked_teams.sort(
                    key=lambda t: (t.points, self.get_team_opponent_points(t)),
                    reverse=True
                )
            else:
                random.shuffle(unlocked_teams)

            unlocked_idx = 0
            for table_idx in range(num_tables):
                needed = 2 - len(team_pods[table_idx])
                for _ in range(needed):
                    if unlocked_idx < len(unlocked_teams):
                        team_pods[table_idx].append(unlocked_teams[unlocked_idx])
                        unlocked_idx += 1

            while unlocked_idx < len(unlocked_teams) and team_pods:
                smallest_pod = min(team_pods, key=len)
                smallest_pod.append(unlocked_teams[unlocked_idx])
                unlocked_idx += 1

            if target_round > 1 and len(team_pods) > 1:
                self._optimize_2hg_pods(team_pods)

            player_pods = []
            for t_pod in team_pods:
                p_list = []
                for tm in t_pod:
                    p_list.append(self.players[tm.player1])
                    p_list.append(self.players[tm.player2])
                if p_list:
                    player_pods.append(p_list)

            if bye_team is not None:
                player_pods.append([
                    self.players[bye_team.player1],
                    self.players[bye_team.player2]
                ])

            self.current_pods = player_pods
            self.pod_outcomes = [None] * len(player_pods)
            self.global_swap_selection = None
            self.global_team_swap_selection = None

            if bye_team is not None:
                self._apply_bye_2hg(len(player_pods) - 1, bye_team)

            self.recalculate_warnings()
        else:
            active_players = self.get_active_players()
            num_players = len(active_players)
            pod_sizes = self._calculate_pod_sizes(num_players)
            num_pods = len(pod_sizes)

            pods: list[list[Player]] = [[] for _ in range(num_pods)]

            locked_players = [p for p in active_players if p.locked_table is not None]
            unlocked_players = [p for p in active_players if p.locked_table is None]

            locked_players.sort(key=lambda p: (p.points, self.get_opponent_points(p)), reverse=True)

            assigned_pod_indices = set()
            for p in locked_players:
                target_idx = p.locked_table
                if target_idx < 0:
                    target_idx = 0
                if target_idx >= num_pods:
                    target_idx = num_pods - 1

                if target_idx in assigned_pod_indices or len(pods[target_idx]) >= pod_sizes[target_idx]:
                    found = False
                    for offset in range(1, num_pods):
                        for candidate in (target_idx + offset, target_idx - offset):
                            if 0 <= candidate < num_pods and candidate not in assigned_pod_indices and len(pods[candidate]) < pod_sizes[candidate]:
                                target_idx = candidate
                                found = True
                                break
                        if found:
                            break

                pods[target_idx].append(p)
                assigned_pod_indices.add(target_idx)

            if target_round > 1:
                unlocked_players.sort(
                    key=lambda p: (p.points, self.get_opponent_points(p)),
                    reverse=True
                )
            else:
                random.shuffle(unlocked_players)

            unlocked_idx = 0
            for pod_idx in range(num_pods):
                needed = pod_sizes[pod_idx] - len(pods[pod_idx])
                for _ in range(needed):
                    if unlocked_idx < len(unlocked_players):
                        pods[pod_idx].append(unlocked_players[unlocked_idx])
                        unlocked_idx += 1

            while unlocked_idx < len(unlocked_players):
                smallest_pod = min(pods, key=len)
                smallest_pod.append(unlocked_players[unlocked_idx])
                unlocked_idx += 1

            if target_round > 1 and len(pods) > 1:
                self._optimize_pods(pods)

            self.current_pods = pods
            self.pod_outcomes = [None] * len(pods)
            self.global_swap_selection = None
            self.global_team_swap_selection = None
            self.recalculate_warnings()

    def _update_pod_opponents(self, pod: list[Player], delta: int):
        if self.is_2hg_mode:
            pod_teams = self.get_pod_teams_2hg(pod)
            for i in range(len(pod_teams)):
                for j in range(i + 1, len(pod_teams)):
                    t1, t2 = pod_teams[i], pod_teams[j]
                    t1.opponents[t2.name] += delta
                    if t1.opponents[t2.name] <= 0:
                        del t1.opponents[t2.name]
                    t2.opponents[t1.name] += delta
                    if t2.opponents[t1.name] <= 0:
                        del t2.opponents[t1.name]
        else:
            for i in range(len(pod)):
                for j in range(i + 1, len(pod)):
                    p1, p2 = pod[i], pod[j]
                    p1.opponents[p2.name] += delta
                    if p1.opponents[p2.name] <= 0:
                        del p1.opponents[p2.name]
                    p2.opponents[p1.name] += delta
                    if p2.opponents[p1.name] <= 0:
                        del p2.opponents[p1.name]

    def create_next_round(self) -> tuple[bool, str]:
        if self.round_number >= self.max_rounds:
            return False, "The tournament has already reached its 3-round limit and is finalized."

        if self.current_pods and any(outcome is None for outcome in self.pod_outcomes):
            missing = [str(i + 1) for i, o in enumerate(self.pod_outcomes) if o is None]
            return False, f"Please record results for Table(s): {', '.join(missing)} before advancing."

        if self.is_2hg_mode:
            active_players = self.get_active_players()
            assigned = self.get_assigned_2hg_players()
            unassigned = [p.name for p in active_players if p.name not in assigned]
            if unassigned:
                return False, f"Cannot start round: All active players must be assigned to a 2HG team. Unassigned: {', '.join(unassigned)}"
            active_teams = [t for t in self.teams_2hg if not t.dropped]
            if len(active_teams) < 2:
                return False, "Need at least 2 active 2HG teams to start a round."
        else:
            active_players = self.get_active_players()
            if len(active_players) < 3:
                return False, f"Need at least 3 active players to generate pods (currently {len(active_players)} active)."

        # Archive the completed round before advancing to the next round
        if self.round_number > 0 and self.current_pods:
            snapshot = self._build_round_snapshot(self.round_number, self.current_pods, self.pod_outcomes)
            self.round_history = [r for r in self.round_history if r.get("round") != self.round_number]
            self.round_history.append(snapshot)

        self.round_number += 1
        self._generate_pods_for_round(self.round_number)
        self.save_state()
        return True, f"Round {self.round_number} started!"

    def regenerate_current_round_pods(self) -> tuple[bool, str]:
        if not self.current_pods:
            return False, "No active round to re-pod."
        if any(outcome is not None and outcome.get("type") != "BYE" for outcome in self.pod_outcomes):
            return False, "Cannot re-pod after results have been recorded for this round."

        if self.is_2hg_mode:
            active_teams = [t for t in self.teams_2hg if not t.dropped]
            if len(active_teams) < 2:
                return False, "Need at least 2 active 2HG teams to re-pod."
        else:
            active_players = self.get_active_players()
            if len(active_players) < 3:
                return False, f"Need at least 3 active players to generate pods (currently {len(active_players)} active)."

        for idx, outcome in enumerate(self.pod_outcomes):
            if outcome is not None and outcome.get("type") == "BYE":
                self._revert_bye_2hg(idx)

        self._generate_pods_for_round(self.round_number)
        self.save_state()
        return True, f"Successfully re-podded for Round {self.round_number}!"

    def record_result(self, pod_index: int, winner: Player = None, is_draw: bool = False, winner_team: Team2HG = None):
        if self.pod_outcomes[pod_index] is not None:
            return

        pod = self.current_pods[pod_index]
        if self.is_2hg_mode:
            pod_teams = self.get_pod_teams_2hg(pod)
            if not pod_teams:
                return

            if is_draw:
                for tm in pod_teams:
                    tm.points += 1
                    tm.draws += 1
                for p in pod:
                    p.points += 1
                    p.draws += 1
                self.pod_outcomes[pod_index] = {"type": "DRAW", "winner_team": None}
            else:
                for tm in pod_teams:
                    if tm == winner_team:
                        tm.points += 3
                        tm.wins += 1
                        for p_name in (tm.player1, tm.player2):
                            if p_name in self.players:
                                self.players[p_name].points += 3
                                self.players[p_name].wins += 1
                    else:
                        tm.losses += 1
                        for p_name in (tm.player1, tm.player2):
                            if p_name in self.players:
                                self.players[p_name].losses += 1
                self.pod_outcomes[pod_index] = {"type": "WIN", "winner_team": winner_team}

            self._update_pod_opponents(pod, delta=1)
            self.global_team_swap_selection = None
            self.save_state()
        else:
            if is_draw:
                for p in pod:
                    p.points += 1
                    p.draws += 1
                self.pod_outcomes[pod_index] = {"type": "DRAW", "winner": None}
            else:
                for p in pod:
                    if p == winner:
                        p.points += 3
                        p.wins += 1
                    else:
                        p.losses += 1
                self.pod_outcomes[pod_index] = {"type": "WIN", "winner": winner}

            self._update_pod_opponents(pod, delta=1)
            self.global_swap_selection = None
            self.save_state()

    def undo_result(self, pod_index: int):
        outcome = self.pod_outcomes[pod_index]
        if outcome is None or outcome.get("type") == "BYE":
            return

        pod = self.current_pods[pod_index]
        if self.is_2hg_mode:
            pod_teams = self.get_pod_teams_2hg(pod)
            if not pod_teams:
                return

            if outcome["type"] == "DRAW":
                for tm in pod_teams:
                    tm.points -= 1
                    tm.draws -= 1
                for p in pod:
                    p.points -= 1
                    p.draws -= 1
            elif outcome["type"] == "WIN":
                winner_team = outcome["winner_team"]
                for tm in pod_teams:
                    if tm == winner_team:
                        tm.points -= 3
                        tm.wins -= 1
                        for p_name in (tm.player1, tm.player2):
                            if p_name in self.players:
                                self.players[p_name].points -= 3
                                self.players[p_name].wins -= 1
                    else:
                        tm.losses -= 1
                        for p_name in (tm.player1, tm.player2):
                            if p_name in self.players:
                                self.players[p_name].losses -= 1

            self._update_pod_opponents(pod, delta=-1)
            self.pod_outcomes[pod_index] = None
            self.save_state()
        else:
            if outcome["type"] == "DRAW":
                for p in pod:
                    p.points -= 1
                    p.draws -= 1
            elif outcome["type"] == "WIN":
                winner = outcome["winner"]
                for p in pod:
                    if p == winner:
                        p.points -= 3
                        p.wins -= 1
                    else:
                        p.losses -= 1

            self._update_pod_opponents(pod, delta=-1)
            self.pod_outcomes[pod_index] = None
            self.save_state()


class TeamBuilderWindow(tk.Toplevel):
    def __init__(self, parent, gui_app):
        super().__init__(parent)
        self.gui = gui_app
        self.event = gui_app.event
        self.title("Two-Headed Giant Team Builder")
        self.geometry("940x760")
        self.configure(bg=Theme.BG_MAIN)
        self.transient(parent)
        self.grab_set()

        self.first_selected_player = None
        self.build_ui()

    def build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()

        header_bar = tk.Frame(
            self,
            bg=Theme.BG_DARKEST,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=20,
            pady=14
        )
        header_bar.pack(fill=tk.X)

        tk.Label(
            header_bar,
            text="👥  TWO-HEADED GIANT TEAM BUILDER",
            font=("Segoe UI", 14, "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_DARKEST
        ).pack(side=tk.LEFT)

        tk.Label(
            header_bar,
            text="Click two available players sequentially to pair them into a 2HG team",
            font=("Segoe UI", 9),
            fg=Theme.TEXT_MUTED,
            bg=Theme.BG_DARKEST
        ).pack(side=tk.RIGHT)

        # --- Top Section: Available Players ---
        avail_outer = tk.Frame(
            self, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1
        )
        avail_outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 8))

        avail_hdr = tk.Frame(avail_outer, bg=Theme.BG_CARD_HEADER, padx=14, pady=8)
        avail_hdr.pack(fill=tk.X)
        tk.Label(
            avail_hdr,
            text="AVAILABLE UNASSIGNED PLAYERS",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD_HEADER
        ).pack(side=tk.LEFT)

        avail_body = tk.Frame(avail_outer, bg=Theme.BG_CARD, padx=10, pady=10)
        avail_body.pack(fill=tk.BOTH, expand=True)

        avail_canvas = tk.Canvas(avail_body, bg=Theme.BG_CARD, highlightthickness=0)
        avail_canvas._is_scrollable = True
        avail_scroll = ttk.Scrollbar(avail_body, orient=tk.VERTICAL, command=avail_canvas.yview)
        self.avail_grid_frame = tk.Frame(avail_canvas, bg=Theme.BG_CARD)

        self.avail_grid_frame.bind(
            "<Configure>",
            lambda e: avail_canvas.configure(scrollregion=avail_canvas.bbox("all"))
        )
        self.avail_canvas_window = avail_canvas.create_window((0, 0), window=self.avail_grid_frame, anchor="nw")
        avail_canvas.bind(
            "<Configure>",
            lambda e: avail_canvas.itemconfig(self.avail_canvas_window, width=e.width)
        )
        avail_canvas.configure(yscrollcommand=avail_scroll.set)

        avail_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        avail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Bottom Section: Created Teams ---
        teams_outer = tk.Frame(
            self, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1
        )
        teams_outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 16))

        teams_hdr = tk.Frame(teams_outer, bg=Theme.BG_CARD_HEADER, padx=14, pady=8)
        teams_hdr.pack(fill=tk.X)
        tk.Label(
            teams_hdr,
            text="REGISTERED 2HG TEAMS",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD_HEADER
        ).pack(side=tk.LEFT)

        teams_body = tk.Frame(teams_outer, bg=Theme.BG_CARD, padx=10, pady=10)
        teams_body.pack(fill=tk.BOTH, expand=True)

        teams_canvas = tk.Canvas(teams_body, bg=Theme.BG_CARD, highlightthickness=0)
        teams_canvas._is_scrollable = True
        teams_scroll = ttk.Scrollbar(teams_body, orient=tk.VERTICAL, command=teams_canvas.yview)
        self.teams_list_frame = tk.Frame(teams_canvas, bg=Theme.BG_CARD)

        self.teams_list_frame.bind(
            "<Configure>",
            lambda e: teams_canvas.configure(scrollregion=teams_canvas.bbox("all"))
        )
        self.teams_canvas_window = teams_canvas.create_window((0, 0), window=self.teams_list_frame, anchor="nw")
        teams_canvas.bind(
            "<Configure>",
            lambda e: teams_canvas.itemconfig(self.teams_canvas_window, width=e.width)
        )
        teams_canvas.configure(yscrollcommand=teams_scroll.set)

        teams_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        teams_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.populate_content()

    def populate_content(self):
        for widget in self.avail_grid_frame.winfo_children():
            widget.destroy()
        for widget in self.teams_list_frame.winfo_children():
            widget.destroy()

        assigned_players = self.event.get_assigned_2hg_players()
        active_players = [p for p in self.event.get_active_players() if p.name not in assigned_players]

        if not active_players:
            tk.Label(
                self.avail_grid_frame,
                text="All active players are assigned to a 2HG team.",
                font=("Segoe UI", 10, "italic"),
                fg=Theme.TEXT_MUTED,
                bg=Theme.BG_CARD
            ).pack(pady=24)
        else:
            self.avail_grid_frame.columnconfigure(0, weight=1)
            self.avail_grid_frame.columnconfigure(1, weight=1)
            self.avail_grid_frame.columnconfigure(2, weight=1)

            for idx, p in enumerate(active_players):
                r = idx // 3
                c = idx % 3

                is_selected = (self.first_selected_player == p.name)
                bg_color = Theme.BLUE if is_selected else "#e2e8f0"
                fg_color = "#ffffff" if is_selected else Theme.TEXT_PRIMARY

                btn = tk.Button(
                    self.avail_grid_frame,
                    text=f"{'✓ ' if is_selected else ''}{p.name}{' [RDV]' if p.is_rdv else ''}",
                    font=("Segoe UI", 10, "bold"),
                    bg=bg_color,
                    fg=fg_color,
                    activebackground=Theme.BLUE_HOVER,
                    activeforeground="#ffffff",
                    relief=tk.FLAT,
                    bd=0,
                    cursor="hand2",
                    padx=12,
                    pady=8,
                    command=lambda name=p.name: self.handle_player_click(name)
                )
                btn.grid(row=r, column=c, sticky="nsew", padx=5, pady=5)

        if not self.event.teams_2hg:
            tk.Label(
                self.teams_list_frame,
                text="No 2HG teams created yet.",
                font=("Segoe UI", 10, "italic"),
                fg=Theme.TEXT_MUTED,
                bg=Theme.BG_CARD
            ).pack(pady=24)
        else:
            can_split = (self.event.round_number == 0)
            for t_idx, team in enumerate(self.event.teams_2hg):
                row_frame = tk.Frame(
                    self.teams_list_frame,
                    bg=Theme.BG_ROW_ALT,
                    highlightbackground=Theme.BORDER,
                    highlightthickness=1,
                    padx=12,
                    pady=8
                )
                row_frame.pack(fill=tk.X, pady=4, padx=4)

                lock_str = f"   🔒 Table {team.locked_table + 1}" if team.locked_table is not None else ""
                dropped_str = "   [DROPPED]" if team.dropped else ""
                lbl_text = f"TEAM {t_idx + 1}   •   {team.player1}  &  {team.player2}{lock_str}{dropped_str}"
                tk.Label(
                    row_frame,
                    text=lbl_text,
                    font=("Segoe UI", 10, "bold"),
                    fg=Theme.DANGER if team.dropped else Theme.TEXT_PRIMARY,
                    bg=Theme.BG_ROW_ALT
                ).pack(side=tk.LEFT)

                split_btn = tk.Button(
                    row_frame,
                    text="Split Team",
                    font=("Segoe UI", 9, "bold"),
                    bg=Theme.DANGER if can_split else "#e2e8f0",
                    fg="#ffffff" if can_split else Theme.TEXT_DISABLED,
                    activebackground=Theme.DANGER_HOVER,
                    activeforeground="#ffffff",
                    relief=tk.FLAT,
                    bd=0,
                    padx=12,
                    pady=4,
                    state=tk.NORMAL if can_split else tk.DISABLED,
                    command=lambda t=team: self.handle_split_team(t)
                )
                split_btn.pack(side=tk.RIGHT)

    def handle_player_click(self, name: str):
        if self.first_selected_player is None:
            self.first_selected_player = name
            self.populate_content()
        elif self.first_selected_player == name:
            self.first_selected_player = None
            self.populate_content()
        else:
            p1_name = self.first_selected_player
            p2_name = name
            self.first_selected_player = None

            new_team = Team2HG(p1_name, p2_name)
            p1_obj = self.event.players.get(p1_name)
            p2_obj = self.event.players.get(p2_name)

            inherited_lock = None
            if p1_obj and p1_obj.locked_table is not None:
                inherited_lock = p1_obj.locked_table
            elif p2_obj and p2_obj.locked_table is not None:
                inherited_lock = p2_obj.locked_table

            if inherited_lock is not None:
                new_team.locked_table = inherited_lock
                if p1_obj:
                    p1_obj.locked_table = inherited_lock
                if p2_obj:
                    p2_obj.locked_table = inherited_lock

            self.event.teams_2hg.append(new_team)
            self.event.save_state()
            self.populate_content()
            self.gui.refresh_standings()
            self.gui.refresh_pods()
            self.gui.refresh_prizing()

    def handle_split_team(self, team: Team2HG):
        if self.event.round_number > 0:
            messagebox.showwarning("Locked", "Cannot split existing teams after Round 1 has started.")
            return
        if team in self.event.teams_2hg:
            p1_obj = self.event.players.get(team.player1)
            p2_obj = self.event.players.get(team.player2)
            if p1_obj:
                p1_obj.locked_table = None
            if p2_obj:
                p2_obj.locked_table = None

            self.event.teams_2hg.remove(team)
            self.event.save_state()
            self.populate_content()
            self.gui.refresh_standings()
            self.gui.refresh_pods()
            self.gui.refresh_prizing()


class CustomStartupDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Session Recovery")
        self.geometry("460x240")
        self.resizable(False, False)
        self.configure(bg=Theme.BG_CARD)
        self.transient(parent)
        self.grab_set()

        self.result = "new"

        self.update_idletasks()
        width = 460
        height = 240
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        banner = tk.Frame(
            self,
            bg=Theme.BG_CARD_HEADER,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            pady=14
        )
        banner.pack(fill=tk.X)
        tk.Label(
            banner,
            text="🐉  RED DRAGON'S VAULT",
            font=("Segoe UI", 12, "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_CARD_HEADER
        ).pack()

        tk.Label(
            self,
            text="Previous Tournament Session Detected",
            font=("Segoe UI", 11, "bold"),
            fg=Theme.TEXT_PRIMARY,
            bg=Theme.BG_CARD
        ).pack(pady=(20, 6))

        tk.Label(
            self,
            text="Would you like to resume your saved tournament or start fresh?",
            font=("Segoe UI", 9),
            fg=Theme.TEXT_MUTED,
            bg=Theme.BG_CARD
        ).pack(pady=(0, 22))

        btn_frame = tk.Frame(self, bg=Theme.BG_CARD)
        btn_frame.pack()

        continue_btn = tk.Button(
            btn_frame,
            text="Resume Saved Event",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.EMERALD,
            fg="#ffffff",
            activebackground=Theme.EMERALD_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=18,
            pady=8,
            command=self.on_continue
        )
        continue_btn.pack(side=tk.LEFT, padx=8)

        new_btn = tk.Button(
            btn_frame,
            text="Start New Event",
            font=("Segoe UI", 10, "bold"),
            bg=Theme.CRIMSON,
            fg="#ffffff",
            activebackground=Theme.CRIMSON_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=18,
            pady=8,
            command=self.on_new
        )
        new_btn.pack(side=tk.LEFT, padx=8)

        self.protocol("WM_DELETE_WINDOW", self.on_new)

    def on_continue(self):
        self.result = "continue"
        self.destroy()

    def on_new(self):
        self.result = "new"
        self.destroy()


class CommanderGUI:
    WHEEL_PANEL_WIDTH = 580
    WHEEL_PANEL_HEIGHT = 64.0

    DEMO_PLAYERS = [
        "Alice Smith", "Bob Jones", "Charlie Brown", "Dave Wilson", "Eve Adams (RDV)",
        "Frank Thomas", "Grace Taylor", "Heidi Moore", "Ivan Jackson", "Judy White (RDV)",
        "Mallory Harris (RDV)", "Nate Martin", "Olivia Clark", "Peggy Lewis", "Quentin Walker",
        "Sybil Hall (RDV)", "Trent Allen", "Victor Young", "Walter King", "Xavier Wright",
        "Yvonne Scott", "Zack Taylor", "Aaron Burr", "Betty Ross", "Cynthia Weaver",
        "Derek Vance", "Elena Fisher", "Felix Hawke", "Gemma Arterton", "Harrison Wells (RDV)",
        "Ian Malcolm", "Ellie Sattler", "Alan Grant", "John Hammond", "Lex Murphy", "Tim Murphy"
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Red Dragon's Vault — Commander Control Centre")
        self.root.geometry("1440x880")
        self.root.minsize(1200, 750)
        self.root.configure(bg=Theme.BG_MAIN)
        self._maximize_window(self.root)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.event = CommanderEvent()
        self.scroll_offset = 0.0
        self.is_spinning = False
        self.active_winner_banner: str | None = None
        self.pairings_win = None
        self.pairings_content_frame = None
        self.pairings_header_lbl = None
        self.standings_win = None
        self.team_builder_win = None
        self.tv_wheel_win = None
        self.tv_wheel_canvas = None
        self.tv_prize_labels: list[tk.Label] = []
        self.match_history_win = None
        self.match_history_content_frame = None
        self.match_history_canvas = None
        self.tree_anchor: str | None = None

        self._setup_styles()
        self._build_ui()
        self._setup_global_scroll()

        self.root.after(50, self._check_and_load_state)

    @staticmethod
    def _maximize_window(win: tk.Tk | tk.Toplevel):
        try:
            win.state("zoomed")
        except tk.TclError:
            try:
                win.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _setup_global_scroll(self):
        """Route mouse wheel scrolling to whichever Treeview or scrollable Canvas is under the cursor."""
        self.root.unbind_class("Treeview", "<MouseWheel>")
        self.root.unbind_class("Treeview", "<Button-4>")
        self.root.unbind_class("Treeview", "<Button-5>")

        def _on_global_mousewheel(event):
            try:
                target = self.root.winfo_containing(event.x_root, event.y_root)
            except Exception:
                target = event.widget

            if not target:
                return

            if getattr(event, "num", None) == 4:
                steps = -1
            elif getattr(event, "num", None) == 5:
                steps = 1
            elif getattr(event, "delta", 0):
                steps = int(-1 * (event.delta / 120))
                if steps == 0:
                    steps = -1 if event.delta > 0 else 1
            else:
                return

            curr = target
            while curr is not None:
                if isinstance(curr, ttk.Treeview):
                    curr.yview_scroll(steps, "units")
                    return "break"
                if isinstance(curr, tk.Canvas) and getattr(curr, "_is_scrollable", False):
                    curr.update_idletasks()
                    bbox = curr.bbox("all")
                    if bbox and (bbox[3] - bbox[1]) > curr.winfo_height():
                        curr.yview_scroll(steps, "units")
                    return "break"
                curr = getattr(curr, "master", None)

        self.root.bind_all("<MouseWheel>", _on_global_mousewheel)
        self.root.bind_all("<Button-4>", _on_global_mousewheel)
        self.root.bind_all("<Button-5>", _on_global_mousewheel)

    def _check_and_load_state(self):
        if os.path.exists(CommanderEvent.STATE_FILE):
            dialog = CustomStartupDialog(self.root)
            self.root.wait_window(dialog)
            if dialog.result == "continue":
                success = self.event.load_state()
                if not success:
                    messagebox.showwarning("Load Failed", "Could not successfully read the saved state file. Starting fresh.")
                else:
                    self._refresh_all_views()
            else:
                CommanderEvent.clear_saved_state()
        else:
            CommanderEvent.clear_saved_state()

    def _refresh_all_views(self):
        if self.event.players or self.event.round_number > 0:
            self.disable_demo_buttons()

        if self.event.round_number == 0:
            round_text = "REGISTRATION PHASE"
            self.next_round_btn.config(text="▶  Start Round 1 (Random)", state=tk.NORMAL)
            self.player_entry.config(state=tk.NORMAL)
            self.add_btn.config(state=tk.NORMAL)
        elif self.event.is_tournament_complete():
            round_text = "★  TOURNAMENT FINALIZED"
            self.next_round_btn.config(text="✓  Tournament Finalized", state=tk.DISABLED)
            self.player_entry.config(state=tk.DISABLED)
            self.add_btn.config(state=tk.DISABLED)
        elif self.event.round_number == self.event.max_rounds:
            round_text = f"ROUND {self.event.round_number} OF {self.event.max_rounds}  •  FINAL ROUND"
            self.next_round_btn.config(text="✓  Tournament Finalized", state=tk.DISABLED)
            self.player_entry.config(state=tk.DISABLED)
            self.add_btn.config(state=tk.DISABLED)
        else:
            mode = "RANDOM PAIRINGS" if self.event.round_number == 1 else "SWISS STANDINGS"
            round_text = f"ROUND {self.event.round_number} OF {self.event.max_rounds}  •  {mode}"
            self.next_round_btn.config(text=f"▶  Start Round {self.event.round_number + 1}", state=tk.NORMAL)

        if self.event.is_2hg_mode:
            self.mode_2hg_btn.config(text="👥  2HG Mode: ON", style="Accent.TButton")
            self.teams_btn.pack(side=tk.LEFT, padx=4)
            self.tree["columns"] = ("paid", "name", "team", "status", "pts", "opp_pts", "record")
        else:
            self.mode_2hg_btn.config(text="👥  2HG Mode: OFF", style="Slate.TButton")
            self.teams_btn.pack_forget()
            self.tree["columns"] = ("paid", "name", "status", "pts", "opp_pts", "record")

        headers = {
            "paid": ("PAYMENT", 120, tk.CENTER),
            "name": ("PLAYER NAME", 280, tk.W),
            "team": ("TEAM #", 100, tk.CENTER),
            "status": ("STATUS", 110, tk.CENTER),
            "pts": ("POINTS", 95, tk.CENTER),
            "opp_pts": ("OPP PTS (TB)", 115, tk.CENTER),
            "record": ("W - L - D", 115, tk.CENTER),
        }
        for col in self.tree["columns"]:
            text, width, anchor = headers[col][:3]
            self.tree.heading(col, text=text, command=lambda c=col: self.handle_column_sort(c))
            self.tree.column(col, width=width, anchor=anchor, stretch=False if col in ("paid", "team") else True)

        self.round_label.config(text=round_text)
        self._update_registration_locks()
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()

    def on_close(self):
        if messagebox.askyesno("Exit Confirmation", "Are you sure you want to close? Tournament state is automatically saved."):
            self.root.destroy()

    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(
            ".",
            background=Theme.BG_MAIN,
            foreground=Theme.TEXT_PRIMARY,
            font=("Segoe UI", 10),
            borderwidth=0,
            focuscolor="none"
        )

        style.configure("TFrame", background=Theme.BG_MAIN)
        style.configure("Card.TFrame", background=Theme.BG_CARD)
        style.configure("TLabel", background=Theme.BG_MAIN, foreground=Theme.TEXT_PRIMARY, font=("Segoe UI", 10))
        style.configure("TSeparator", background=Theme.BORDER)

        # Modern Bright Notebook Tabs
        style.configure("TNotebook", background=Theme.BG_MAIN, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure(
            "TNotebook.Tab",
            font=("Segoe UI", 10, "bold"),
            padding=[24, 10],
            background="#e2e8f0",
            foreground=Theme.TEXT_SECONDARY,
            borderwidth=0,
            focuscolor="none"
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", Theme.CRIMSON), ("active", "#cbd5e1")],
            foreground=[("selected", "#ffffff"), ("active", Theme.TEXT_PRIMARY)]
        )

        # Modern Bright Treeview
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background="#f1f5f9",
            foreground=Theme.TEXT_SECONDARY,
            relief="flat",
            borderwidth=0,
            padding=(10, 10)
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#e2e8f0")],
            foreground=[("active", Theme.TEXT_PRIMARY)]
        )
        style.configure(
            "Treeview",
            font=("Segoe UI", 10),
            rowheight=36,
            background=Theme.BG_CARD,
            fieldbackground=Theme.BG_CARD,
            foreground=Theme.TEXT_PRIMARY,
            borderwidth=0,
            relief="flat"
        )
        style.map(
            "Treeview",
            background=[("selected", Theme.BLUE)],
            foreground=[("selected", "#ffffff")]
        )

        # Modern Light Scrollbar
        style.configure(
            "Vertical.TScrollbar",
            background="#cbd5e1",
            troughcolor=Theme.BG_MAIN,
            bordercolor=Theme.BG_MAIN,
            arrowcolor=Theme.TEXT_SECONDARY,
            relief="flat"
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#94a3b8")]
        )

        # Modern Light Entry & Combobox
        style.configure(
            "TEntry",
            fieldbackground=Theme.BG_INPUT,
            foreground=Theme.TEXT_PRIMARY,
            insertcolor=Theme.TEXT_PRIMARY,
            bordercolor=Theme.BORDER,
            lightcolor=Theme.BORDER,
            darkcolor=Theme.BORDER,
            borderwidth=1,
            padding=(10, 6)
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", "#f1f5f9")],
            foreground=[("disabled", Theme.TEXT_DISABLED)]
        )
        style.configure(
            "TCombobox",
            fieldbackground=Theme.BG_INPUT,
            background="#e2e8f0",
            foreground=Theme.TEXT_PRIMARY,
            arrowcolor=Theme.TEXT_PRIMARY,
            bordercolor=Theme.BORDER,
            padding=5
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", Theme.BG_INPUT)],
            foreground=[("readonly", Theme.TEXT_PRIMARY)]
        )

        # Helper to register flat, solid-color modern buttons
        def make_btn_style(name: str, bg: str, hover_bg: str, fg: str = "#ffffff", font_spec=("Segoe UI", 9, "bold"), pad=(14, 7)):
            style.configure(
                name,
                font=font_spec,
                background=bg,
                foreground=fg,
                borderwidth=0,
                focusthickness=0,
                focuscolor="none",
                relief="flat",
                padding=pad
            )
            style.map(
                name,
                background=[("active", hover_bg), ("disabled", "#e2e8f0")],
                foreground=[("active", fg), ("disabled", Theme.TEXT_DISABLED)]
            )

        make_btn_style("TButton", Theme.SLATE_BTN, Theme.SLATE_BTN_HOVER)
        make_btn_style("Slate.TButton", Theme.SLATE_BTN, Theme.SLATE_BTN_HOVER)
        make_btn_style("Accent.TButton", Theme.CRIMSON, Theme.CRIMSON_HOVER, pad=(16, 7))
        make_btn_style("Danger.TButton", Theme.DANGER, Theme.DANGER_HOVER)
        make_btn_style("RDV.TButton", Theme.AMBER, Theme.AMBER_HOVER, fg="#0f172a")
        make_btn_style("Paid.TButton", Theme.EMERALD, Theme.EMERALD_HOVER)
        make_btn_style("Edit.TButton", Theme.BLUE, Theme.BLUE_HOVER)
        make_btn_style("Lock.TButton", Theme.SLATE_BTN, Theme.SLATE_BTN_HOVER)
        make_btn_style("Teams.TButton", Theme.VIOLET, Theme.VIOLET_HOVER)
        make_btn_style("Late.TButton", Theme.EMERALD, Theme.EMERALD_HOVER)
        make_btn_style("Spin.TButton", Theme.CRIMSON, Theme.CRIMSON_HOVER, font_spec=("Segoe UI", 12, "bold"), pad=(28, 10))
        make_btn_style("Standings.TButton", Theme.EMERALD, Theme.EMERALD_HOVER)
        make_btn_style("History.TButton", Theme.VIOLET, Theme.VIOLET_HOVER)
        make_btn_style("Demo.TButton", "#0d9488", "#0f766e")
        make_btn_style("Demo2.TButton", Theme.BLUE, Theme.BLUE_HOVER)
        make_btn_style("Demo2HG.TButton", Theme.VIOLET, Theme.VIOLET_HOVER)
        make_btn_style("Repod.TButton", Theme.AMBER, Theme.AMBER_HOVER, fg="#0f172a")
        make_btn_style("Pairings.TButton", Theme.BLUE, Theme.BLUE_HOVER)
        make_btn_style("Win.TButton", Theme.EMERALD, Theme.EMERALD_HOVER, font_spec=("Segoe UI", 9, "bold"), pad=(10, 4))
        make_btn_style("Draw.TButton", Theme.SLATE_BTN, Theme.SLATE_BTN_HOVER, font_spec=("Segoe UI", 9, "bold"), pad=(10, 6))
        make_btn_style("Small.TButton", Theme.SLATE_BTN, Theme.SLATE_BTN_HOVER, font_spec=("Segoe UI", 8, "bold"), pad=(6, 4))
        make_btn_style("SwapActive.TButton", Theme.BLUE, Theme.BLUE_HOVER, font_spec=("Segoe UI", 8, "bold"), pad=(6, 4))
        make_btn_style("Move.TButton", Theme.BLUE, Theme.BLUE_HOVER, font_spec=("Segoe UI", 8, "bold"), pad=(6, 4))

    def _build_ui(self):
        # --- Top Brand Header Bar ---
        header_bar = tk.Frame(self.root, bg=Theme.BG_DARKEST, padx=18, pady=12)
        header_bar.pack(fill=tk.X)

        brand_left = tk.Frame(header_bar, bg=Theme.BG_DARKEST)
        brand_left.pack(side=tk.LEFT)

        tk.Label(
            brand_left,
            text="🐉  RED DRAGON'S VAULT",
            font=("Segoe UI", 15, "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_DARKEST
        ).pack(side=tk.LEFT)

        tk.Label(
            brand_left,
            text="   |   COMMANDER CONTROL CENTRE",
            font=("Segoe UI", 11, "bold"),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_DARKEST
        ).pack(side=tk.LEFT, pady=(2, 0))

        # Phase Pill Badge on Right of Header
        self.round_label = tk.Label(
            header_bar,
            text="REGISTRATION PHASE",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_PRIMARY,
            bg="#e2e8f0",
            padx=14,
            pady=5
        )
        self.round_label.pack(side=tk.RIGHT)

        # --- Action Toolbar Bar ---
        toolbar_frame = tk.Frame(
            self.root,
            bg=Theme.BG_CARD_HEADER,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=16,
            pady=10
        )
        toolbar_frame.pack(fill=tk.X)

        self.add_label = tk.Label(
            toolbar_frame,
            text="REGISTER PLAYER(S):",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD_HEADER
        )
        self.add_label.pack(side=tk.LEFT, padx=(0, 8))

        self.player_entry = ttk.Entry(toolbar_frame, width=24, font=("Segoe UI", 10))
        self.player_entry.pack(side=tk.LEFT, padx=(0, 6))
        self.player_entry.bind("<Return>", lambda e: self.handle_add_players())

        self.add_btn = ttk.Button(toolbar_frame, text="+ Add", style="Paid.TButton", command=self.handle_add_players)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 14))

        self.demo_btn = ttk.Button(toolbar_frame, text="Demo 1", style="Demo.TButton", command=self.handle_demo_mode)
        self.demo_btn.pack(side=tk.LEFT, padx=3)

        self.demo2_btn = ttk.Button(toolbar_frame, text="Demo 2 (Post-Event)", style="Demo2.TButton", command=self.handle_demo_mode_2)
        self.demo2_btn.pack(side=tk.LEFT, padx=3)

        self.demo_2hg_btn = ttk.Button(
            toolbar_frame, text="Demo 3 (2HG Ready)", style="Demo2HG.TButton", command=self.handle_demo_mode_2hg
        )
        self.demo_2hg_btn.pack(side=tk.LEFT, padx=3)

        self.mode_2hg_btn = ttk.Button(
            toolbar_frame, text="👥  2HG Mode: OFF", style="Slate.TButton", command=self.handle_toggle_2hg_mode
        )
        self.mode_2hg_btn.pack(side=tk.LEFT, padx=12)

        self.next_round_btn = ttk.Button(
            toolbar_frame, text="▶  Start Round 1 (Random)", style="Accent.TButton", command=self.handle_next_round
        )
        self.next_round_btn.pack(side=tk.RIGHT)

        # --- Main Notebook Tabs ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 16))

        self.scoreboard_tab = ttk.Frame(self.notebook, padding=12)
        self.pods_tab = ttk.Frame(self.notebook, padding=12)
        self.prizing_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.scoreboard_tab, text="   🧑‍💼  Player Manager   ")
        self.notebook.add(self.pods_tab, text="   🫛  Active Pods   ")
        self.notebook.add(self.prizing_tab, text="   🏆  Prizing & Wheel   ")

        # --- Tab 1: Player Manager ---
        scoreboard_controls = tk.Frame(self.scoreboard_tab, bg=Theme.BG_MAIN, pady=6)
        scoreboard_controls.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            scoreboard_controls,
            text="💡 Shift+Click or Ctrl+Click to multi-select players. Double-click to toggle Paid, or right-click for actions.",
            font=("Segoe UI", 9, "italic"),
            fg=Theme.TEXT_MUTED,
            bg=Theme.BG_MAIN
        ).pack(side=tk.LEFT)

        btn_right_frame = tk.Frame(scoreboard_controls, bg=Theme.BG_MAIN)
        btn_right_frame.pack(side=tk.RIGHT)

        self.late_btn = ttk.Button(
            btn_right_frame,
            text="+ Late Player",
            style="Late.TButton",
            command=self.handle_add_late_player
        )
        self.late_btn.pack(side=tk.LEFT, padx=3)

        self.paid_btn = ttk.Button(
            btn_right_frame,
            text="✓ Mark Paid",
            style="Paid.TButton",
            command=self.handle_toggle_paid_button
        )
        self.paid_btn.pack(side=tk.LEFT, padx=3)

        self.edit_btn = ttk.Button(
            btn_right_frame,
            text="✎ Edit Name",
            style="Edit.TButton",
            command=self.handle_edit_player_name
        )
        self.edit_btn.pack(side=tk.LEFT, padx=3)

        self.lock_btn = ttk.Button(
            btn_right_frame,
            text="🔒 Lock Table",
            style="Lock.TButton",
            command=self.handle_set_table_lock
        )
        self.lock_btn.pack(side=tk.LEFT, padx=3)

        self.teams_btn = ttk.Button(
            btn_right_frame,
            text="👥 Manage Teams",
            style="Teams.TButton",
            command=self.handle_open_team_builder
        )

        self.rdv_btn = ttk.Button(
            btn_right_frame,
            text="★ RDV Tag",
            style="RDV.TButton",
            command=self.handle_toggle_rdv
        )
        self.rdv_btn.pack(side=tk.LEFT, padx=3)

        self.drop_btn = ttk.Button(
            btn_right_frame,
            text="✕ Drop Player",
            style="Danger.TButton",
            command=self.handle_drop_player
        )
        self.drop_btn.pack(side=tk.LEFT, padx=(3, 0))

        tree_frame = tk.Frame(
            self.scoreboard_tab,
            bg=Theme.BG_CARD,
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("paid", "name", "status", "pts", "opp_pts", "record")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")

        headers = {
            "paid": ("PAYMENT", 120, tk.CENTER),
            "name": ("PLAYER NAME", 280, tk.W),
            "status": ("STATUS", 110, tk.CENTER),
            "pts": ("POINTS", 95, tk.CENTER),
            "opp_pts": ("OPP PTS (TB)", 115, tk.CENTER),
            "record": ("W - L - D", 115, tk.CENTER),
        }
        for col, (text, width, anchor) in headers.items():
            self.tree.heading(col, text=text, command=lambda c=col: self.handle_column_sort(c))
            self.tree.column(col, width=width, anchor=anchor, stretch=False if col == "paid" else True)

        self.tree.tag_configure("evenrow", background=Theme.BG_CARD)
        self.tree.tag_configure("oddrow", background=Theme.BG_ROW_ALT)
        self.tree.tag_configure("dropped", foreground=Theme.DANGER, font=("Segoe UI", 10))
        self.tree.tag_configure("paid", foreground=Theme.EMERALD_TEXT, font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("unpaid", foreground=Theme.AMBER_TEXT, font=("Segoe UI", 10, "bold"))

        # Standard Desktop Click, Ctrl+Click, Shift+Click, Double-Click, and Ctrl+A bindings
        self.tree.bind("<Button-1>", self.handle_tree_click)
        self.tree.bind("<Control-Button-1>", self.handle_tree_ctrl_click)
        self.tree.bind("<Shift-Button-1>", self.handle_tree_shift_click)
        self.tree.bind("<Control-a>", self.handle_tree_select_all)
        self.tree.bind("<Control-A>", self.handle_tree_select_all)
        self.tree.bind("<Double-1>", self.handle_tree_double_click)

        # Context Menu Setup
        self.context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_PRIMARY,
            activebackground=Theme.BLUE,
            activeforeground="#ffffff",
            font=("Segoe UI", 9)
        )
        self.context_menu.add_command(label="✓  Mark Paid / Unpaid", command=self.handle_context_paid)
        self.context_menu.add_command(label="✎  Edit Player Name", command=self.handle_context_edit)
        self.context_menu.add_command(label="🔒  Set Table Lock...", command=self.handle_context_lock)
        self.context_menu.add_command(label="★  Toggle RDV Tag", command=self.handle_context_rdv)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✕  Drop Player(s)", command=self.handle_context_drop)

        def show_context_menu(event):
            if self.event.is_tournament_complete():
                return
            item = self.tree.identify_row(event.y)
            if item:
                if item not in self.tree.selection():
                    self.tree.selection_set(item)
                    self.tree_anchor = item
                self.tree.focus(item)
                self.context_menu.tk_popup(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", show_context_menu)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Tab 2: Active Pods ---
        pods_container = tk.Frame(self.pods_tab, bg=Theme.BG_MAIN)
        pods_container.pack(fill=tk.BOTH, expand=True)

        pods_top_bar = tk.Frame(pods_container, bg=Theme.BG_MAIN, pady=6)
        pods_top_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            pods_top_bar,
            text="ACTIVE ROUND TABLES & MATCHUPS",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.TEXT_MUTED,
            bg=Theme.BG_MAIN
        ).pack(side=tk.LEFT)

        self.show_pairings_btn = ttk.Button(
            pods_top_bar,
            text="📺  Show TV Pairings",
            style="Pairings.TButton",
            command=self.handle_show_pairings_window
        )
        self.show_pairings_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self.repod_btn = ttk.Button(
            pods_top_bar,
            text="↻  Re-Pod Round",
            style="Repod.TButton",
            command=self.handle_repod
        )
        self.repod_btn.pack(side=tk.RIGHT)

        pods_canvas_frame = tk.Frame(pods_container, bg=Theme.BG_MAIN)
        pods_canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(pods_canvas_frame, highlightthickness=0, bg=Theme.BG_MAIN)
        self.canvas._is_scrollable = True
        scrollbar = ttk.Scrollbar(pods_canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.pods_frame = tk.Frame(self.canvas, bg=Theme.BG_MAIN)

        self.pods_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.pods_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Tab 3: Prizing ---
        self._build_prizing_tab()

        self.refresh_pods()
        self.refresh_standings()
        self.draw_wheel(self.scroll_offset)
        self.refresh_prizing()

    def handle_tree_click(self, event):
        """Standard single click: select only the clicked row and set selection anchor."""
        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        row_id = self.tree.identify_row(event.y)
        self.tree.focus_set()
        if not row_id:
            self.tree.selection_remove(self.tree.selection())
            return "break"
        self.tree_anchor = row_id
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        return "break"

    def handle_tree_ctrl_click(self, event):
        """Ctrl+Click: toggle individual row selection without clearing existing selections."""
        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        row_id = self.tree.identify_row(event.y)
        self.tree.focus_set()
        if not row_id:
            return "break"
        if row_id in self.tree.selection():
            self.tree.selection_remove(row_id)
        else:
            self.tree.selection_add(row_id)
        self.tree_anchor = row_id
        self.tree.focus(row_id)
        return "break"

    def handle_tree_shift_click(self, event):
        """Shift+Click: select contiguous range of rows from anchor to clicked row."""
        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        row_id = self.tree.identify_row(event.y)
        self.tree.focus_set()
        if not row_id:
            return "break"
        all_rows = list(self.tree.get_children(""))
        if not self.tree_anchor or self.tree_anchor not in all_rows:
            focused = self.tree.focus()
            self.tree_anchor = focused if focused in all_rows else row_id

        idx1 = all_rows.index(self.tree_anchor)
        idx2 = all_rows.index(row_id)
        start, end = min(idx1, idx2), max(idx1, idx2)
        self.tree.selection_set(all_rows[start:end + 1])
        self.tree.focus(row_id)
        return "break"

    def handle_tree_select_all(self, event=None):
        """Ctrl+A: select all players in the Player Manager."""
        all_rows = self.tree.get_children("")
        if all_rows:
            self.tree.selection_set(all_rows)
        return "break"

    def handle_column_sort(self, col):
        if not hasattr(self, "tree_sort_directions"):
            self.tree_sort_directions = {}

        current_state = self.tree_sort_directions.get(col, "desc")
        if current_state == "desc":
            reverse = False
            self.tree_sort_directions = {col: "asc"}
        else:
            reverse = True
            self.tree_sort_directions = {col: "desc"}

        data = []
        for child in self.tree.get_children(""):
            val = self.tree.set(child, col)
            data.append((val, child))

        if col == "team":
            def team_sort_key(item):
                val_str = str(item[0]).strip()
                if val_str.startswith("Team "):
                    try:
                        return (0, int(val_str.replace("Team ", "")))
                    except ValueError:
                        pass
                return (1, 999999)
            data.sort(key=team_sort_key, reverse=reverse)
        else:
            try:
                data.sort(key=lambda x: float(x[0]), reverse=reverse)
            except ValueError:
                data.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)

        for index, (val, child) in enumerate(data):
            self.tree.move(child, "", index)
            stripe_tag = "evenrow" if index % 2 == 0 else "oddrow"
            current_tags = [t for t in self.tree.item(child, "tags") if t not in ("evenrow", "oddrow")]
            self.tree.item(child, tags=(stripe_tag, *current_tags))

    def handle_toggle_2hg_mode(self):
        if self.event.round_number > 0:
            messagebox.showwarning("Locked", "Cannot toggle 2HG mode after the tournament has started.")
            return

        self.event.is_2hg_mode = not self.event.is_2hg_mode
        self.event.global_swap_selection = None
        self.event.global_team_swap_selection = None
        self.event.save_state()

        if self.event.is_2hg_mode:
            self.mode_2hg_btn.config(text="👥  2HG Mode: ON", style="Accent.TButton")
            self.teams_btn.pack(side=tk.LEFT, padx=4)
        else:
            self.mode_2hg_btn.config(text="👥  2HG Mode: OFF", style="Slate.TButton")
            self.teams_btn.pack_forget()
            if self.team_builder_win and self.team_builder_win.winfo_exists():
                self.team_builder_win.destroy()

        self._refresh_all_views()

    def handle_open_team_builder(self):
        if not self.team_builder_win or not self.team_builder_win.winfo_exists():
            self.team_builder_win = TeamBuilderWindow(self.root, self)
        else:
            self.team_builder_win.populate_content()
            self.team_builder_win.lift()

    def _build_prizing_tab(self):
        prizing_top_controls = tk.Frame(self.prizing_tab, bg=Theme.BG_MAIN, pady=4)
        prizing_top_controls.pack(fill=tk.X, pady=(0, 8))

        self.final_standings_btn = ttk.Button(
            prizing_top_controls,
            text="🏆  View Full Final Standings",
            style="Standings.TButton",
            command=self.handle_show_final_standings,
            state=tk.DISABLED
        )
        self.final_standings_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self.match_history_btn = ttk.Button(
            prizing_top_controls,
            text="📋  Matchups & Winners",
            style="History.TButton",
            command=self.handle_show_match_history
        )
        self.match_history_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self.tv_wheel_btn = ttk.Button(
            prizing_top_controls,
            text="📺  TV Wheel",
            style="Pairings.TButton",
            command=self.handle_show_tv_wheel
        )
        self.tv_wheel_btn.pack(side=tk.RIGHT)

        # --- Modern Podium Cards ---
        podium_container = tk.Frame(self.prizing_tab, bg=Theme.BG_MAIN)
        podium_container.pack(fill=tk.X, pady=(0, 14))
        podium_container.columnconfigure(0, weight=1, uniform="podium")
        podium_container.columnconfigure(1, weight=1, uniform="podium")
        podium_container.columnconfigure(2, weight=1, uniform="podium")

        self.prize_labels = []
        podium_specs = [
            ("🥇  1ST PLACE", Theme.GOLD),
            ("🥈  2ND PLACE", Theme.SILVER),
            ("🥉  3RD PLACE", Theme.BRONZE),
        ]

        for idx, (medal_title, accent_color) in enumerate(podium_specs):
            card = tk.Frame(
                podium_container,
                bg=Theme.BG_CARD,
                highlightbackground=Theme.BORDER,
                highlightthickness=1
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 6, 0 if idx == 2 else 6))

            top_stripe = tk.Frame(card, bg=accent_color, height=4)
            top_stripe.pack(fill=tk.X)

            inner = tk.Frame(card, bg=Theme.BG_CARD, padx=16, pady=12)
            inner.pack(fill=tk.BOTH, expand=True)

            tk.Label(
                inner,
                text=medal_title,
                font=("Segoe UI", 9, "bold"),
                fg=accent_color,
                bg=Theme.BG_CARD
            ).pack(anchor="w")

            lbl = tk.Label(
                inner,
                text="TBD",
                font=("Segoe UI", 13, "bold"),
                fg=Theme.TEXT_PRIMARY,
                bg=Theme.BG_CARD,
                wraplength=360,
                justify=tk.LEFT
            )
            lbl.pack(anchor="w", pady=(4, 0))
            self.prize_labels.append(lbl)

        # --- Prize Wheel Card ---
        wheel_outer = tk.Frame(
            self.prizing_tab,
            bg=Theme.BG_CARD,
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        wheel_outer.pack(fill=tk.BOTH, expand=True)

        wheel_hdr = tk.Frame(wheel_outer, bg=Theme.BG_CARD_HEADER, padx=16, pady=8)
        wheel_hdr.pack(fill=tk.X)

        tk.Label(
            wheel_hdr,
            text="🎡  RANDOM DOOR PRIZE WHEEL",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD_HEADER
        ).pack(side=tk.LEFT)

        self.last_winner_lbl = tk.Label(
            wheel_hdr,
            text="Last Winner: None yet",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.EMERALD_TEXT,
            bg=Theme.BG_CARD_HEADER
        )
        self.last_winner_lbl.pack(side=tk.RIGHT)

        self.wheel_canvas = tk.Canvas(wheel_outer, bg="#f8fafc", highlightthickness=0, height=280)
        self.wheel_canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.wheel_canvas.bind("<Configure>", lambda e: self.draw_wheel(self.scroll_offset, self.active_winner_banner))

        wheel_footer = tk.Frame(wheel_outer, bg=Theme.BG_CARD, pady=10)
        wheel_footer.pack(fill=tk.X)

        self.spin_btn = ttk.Button(
            wheel_footer,
            text="🎰  SPIN PRIZE WHEEL",
            style="Spin.TButton",
            command=self.handle_spin_wheel,
            state=tk.DISABLED
        )
        self.spin_btn.pack()

    def handle_export_match_history_txt(self):
        """Export the night's matchups, winners, and standings to 'Commander FNM ddmmyyyy.txt'."""
        rounds_summary = self.event.get_all_rounds_summary()
        if not rounds_summary:
            messagebox.showinfo("No Data", "No rounds or matchups available to export yet.")
            return

        date_str = datetime.now().strftime("%d%m%Y")
        default_filename = f"Commander FNM {date_str}.txt"

        parent_win = (
            self.match_history_win
            if self.match_history_win and self.match_history_win.winfo_exists()
            else self.root
        )
        file_path = filedialog.asksaveasfilename(
            parent=parent_win,
            title="Export Matchups & Winners to Plain Text",
            initialdir=get_app_dir(),
            initialfile=default_filename,
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            report_text = self.event.format_match_history_text()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            messagebox.showinfo(
                "Export Complete",
                f"Successfully exported matchups and winners to:\n{file_path}",
                parent=parent_win
            )
        except Exception as e:
            messagebox.showerror(
                "Export Failed",
                f"Could not save the text file:\n{e}",
                parent=parent_win
            )

    def handle_show_match_history(self):
        """Open a dedicated window displaying all matchups and winners for every round of the night."""
        rounds_summary = self.event.get_all_rounds_summary()
        if not rounds_summary:
            messagebox.showinfo("No Matchups Yet", "No rounds have been generated yet.")
            return

        if self.match_history_win and self.match_history_win.winfo_exists():
            self._populate_match_history_window()
            self.match_history_win.lift()
            return

        self.match_history_win = tk.Toplevel(self.root)
        self.match_history_win.title("Red Dragon's Vault — Night's Matchups & Winners")
        self.match_history_win.geometry("1400x880")
        self.match_history_win.minsize(1000, 650)
        self.match_history_win.configure(bg=Theme.BG_MAIN)
        self._maximize_window(self.match_history_win)

        hdr_bar = tk.Frame(
            self.match_history_win,
            bg=Theme.BG_DARKEST,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=24,
            pady=14
        )
        hdr_bar.pack(fill=tk.X)

        tk.Label(
            hdr_bar,
            text="📋  ALL MATCHUPS & WINNERS FOR THE NIGHT",
            font=("Segoe UI", 16, "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_DARKEST
        ).pack(side=tk.LEFT)

        ttk.Button(
            hdr_bar,
            text="📄  Export to Text (.txt)",
            style="Paid.TButton",
            command=self.handle_export_match_history_txt
        ).pack(side=tk.RIGHT, padx=(12, 0))

        mode_badge = "2HG TEAM FORMAT" if self.event.is_2hg_mode else "COMMANDER POD FORMAT"
        tk.Label(
            hdr_bar,
            text=mode_badge,
            font=("Segoe UI", 9, "bold"),
            fg=Theme.TEXT_PRIMARY,
            bg="#e2e8f0",
            padx=12,
            pady=5
        ).pack(side=tk.RIGHT)

        canvas_container = tk.Frame(self.match_history_win, bg=Theme.BG_MAIN)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        self.match_history_canvas = tk.Canvas(canvas_container, bg=Theme.BG_MAIN, highlightthickness=0)
        self.match_history_canvas._is_scrollable = True
        v_scroll = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.match_history_canvas.yview)
        self.match_history_content_frame = tk.Frame(self.match_history_canvas, bg=Theme.BG_MAIN)

        self.match_history_content_frame.bind(
            "<Configure>",
            lambda e: self.match_history_canvas.configure(scrollregion=self.match_history_canvas.bbox("all"))
        )
        canvas_win = self.match_history_canvas.create_window(
            (0, 0), window=self.match_history_content_frame, anchor="nw"
        )
        self.match_history_canvas.bind(
            "<Configure>",
            lambda e: self.match_history_canvas.itemconfig(canvas_win, width=e.width)
        )
        self.match_history_canvas.configure(yscrollcommand=v_scroll.set)

        self.match_history_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._populate_match_history_window()

    def _populate_match_history_window(self):
        if not self.match_history_win or not self.match_history_win.winfo_exists():
            return

        for widget in self.match_history_content_frame.winfo_children():
            widget.destroy()

        rounds_summary = self.event.get_all_rounds_summary()
        if not rounds_summary:
            return

        num_cols = max(1, len(rounds_summary))
        for c in range(3):
            self.match_history_content_frame.columnconfigure(c, weight=0, uniform="")
        for c in range(num_cols):
            self.match_history_content_frame.columnconfigure(c, weight=1, uniform="round_col")

        for col_idx, r_data in enumerate(rounds_summary):
            r_num = r_data.get("round", col_idx + 1)
            matches = r_data.get("matches", [])

            col_frame = tk.Frame(
                self.match_history_content_frame,
                bg=Theme.BG_MAIN,
                padx=8
            )
            col_frame.grid(row=0, column=col_idx, sticky="nsew")

            # Round Column Banner
            round_banner = tk.Frame(
                col_frame,
                bg=Theme.CRIMSON,
                padx=16,
                pady=10
            )
            round_banner.pack(fill=tk.X, pady=(0, 12))

            tk.Label(
                round_banner,
                text=f"ROUND {r_num}",
                font=("Segoe UI", 13, "bold"),
                fg="#ffffff",
                bg=Theme.CRIMSON
            ).pack(side=tk.LEFT)

            completed_count = sum(1 for m in matches if m.get("outcome_type") != "IN_PROGRESS")
            tk.Label(
                round_banner,
                text=f"{completed_count}/{len(matches)} Complete",
                font=("Segoe UI", 9, "bold"),
                fg="#ffe4e6",
                bg=Theme.CRIMSON
            ).pack(side=tk.RIGHT)

            # Table Cards inside Round Column
            for m in matches:
                t_num = m.get("table", 1)
                is_bye = m.get("is_bye", False)
                outcome_type = m.get("outcome_type", "IN_PROGRESS")
                winner_name = m.get("winner_name")
                participants = m.get("participants", [])

                border_col = (
                    Theme.VIOLET if is_bye
                    else (Theme.EMERALD if outcome_type == "WIN" else (Theme.BLUE if outcome_type == "DRAW" else Theme.BORDER))
                )

                t_card = tk.Frame(
                    col_frame,
                    bg=Theme.BG_CARD,
                    highlightbackground=border_col,
                    highlightthickness=1
                )
                t_card.pack(fill=tk.X, pady=(0, 10))

                # Table Card Header
                t_hdr = tk.Frame(t_card, bg=Theme.BG_CARD_HEADER, padx=14, pady=8)
                t_hdr.pack(fill=tk.X)

                table_title = "★  BYE POD" if is_bye else f"TABLE {t_num}"
                tk.Label(
                    t_hdr,
                    text=table_title,
                    font=("Segoe UI", 10, "bold"),
                    fg=Theme.TEXT_PRIMARY,
                    bg=Theme.BG_CARD_HEADER
                ).pack(side=tk.LEFT)

                if outcome_type == "BYE":
                    res_badge = f"★ Bye: {winner_name} (+3 pts)"
                    res_fg = Theme.VIOLET
                elif outcome_type == "WIN":
                    res_badge = f"🏆 Winner: {winner_name}"
                    res_fg = Theme.EMERALD_TEXT
                elif outcome_type == "DRAW":
                    res_badge = "🤝 Draw (+1 pt each)"
                    res_fg = Theme.BLUE
                else:
                    res_badge = "⏳ In Progress"
                    res_fg = Theme.AMBER_TEXT

                tk.Label(
                    t_hdr,
                    text=res_badge,
                    font=("Segoe UI", 9, "bold"),
                    fg=res_fg,
                    bg=Theme.BG_CARD_HEADER
                ).pack(side=tk.RIGHT)

                # Participants List
                t_body = tk.Frame(t_card, bg=Theme.BG_CARD, padx=14, pady=10)
                t_body.pack(fill=tk.X)

                for part_name in participants:
                    is_winner = (outcome_type in ("WIN", "BYE") and part_name == winner_name)
                    row_bg = "#ecfdf5" if is_winner else Theme.BG_ROW_ALT
                    row_fg = Theme.EMERALD_TEXT if is_winner else (Theme.BLUE if outcome_type == "DRAW" else Theme.TEXT_PRIMARY)
                    prefix = "🏆  " if is_winner else ("🤝  " if outcome_type == "DRAW" else "•  ")

                    p_row = tk.Frame(
                        t_body,
                        bg=row_bg,
                        highlightbackground="#d1fae5" if is_winner else "#e2e8f0",
                        highlightthickness=1,
                        padx=10,
                        pady=5
                    )
                    p_row.pack(fill=tk.X, pady=2)

                    tk.Label(
                        p_row,
                        text=f"{prefix}{part_name}",
                        font=("Segoe UI", 10, "bold" if is_winner else "normal"),
                        fg=row_fg,
                        bg=row_bg,
                        anchor="w"
                    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

                    if is_winner:
                        tk.Label(
                            p_row,
                            text="WON (+3)",
                            font=("Segoe UI", 8, "bold"),
                            fg=Theme.EMERALD_TEXT,
                            bg=row_bg
                        ).pack(side=tk.RIGHT)
                    elif outcome_type == "DRAW":
                        tk.Label(
                            p_row,
                            text="DRAW (+1)",
                            font=("Segoe UI", 8, "bold"),
                            fg=Theme.BLUE,
                            bg=row_bg
                        ).pack(side=tk.RIGHT)

        self.match_history_content_frame.update_idletasks()
        if self.match_history_canvas and self.match_history_canvas.winfo_exists():
            self.match_history_canvas.configure(scrollregion=self.match_history_canvas.bbox("all"))

    def handle_show_tv_wheel(self):
        """Launch a 1080p-scaled, view-only replica of the Top 3 Podium and Prize Wheel."""
        if self.tv_wheel_win and self.tv_wheel_win.winfo_exists():
            self.tv_wheel_win.lift()
            self.refresh_prizing()
            return

        self.tv_wheel_win = tk.Toplevel(self.root)
        self.tv_wheel_win.title("Red Dragon's Vault — TV Wheel")
        self.tv_wheel_win.geometry("1920x1080")
        self.tv_wheel_win.minsize(1280, 720)
        self.tv_wheel_win.configure(bg=Theme.BG_MAIN)
        self._maximize_window(self.tv_wheel_win)

        body = tk.Frame(self.tv_wheel_win, bg=Theme.BG_MAIN, padx=28, pady=24)
        body.pack(fill=tk.BOTH, expand=True)

        # 1080p Top 3 Podium Cards
        podium_container = tk.Frame(body, bg=Theme.BG_MAIN)
        podium_container.pack(fill=tk.X, pady=(0, 24))
        podium_container.columnconfigure(0, weight=1, uniform="tv_podium")
        podium_container.columnconfigure(1, weight=1, uniform="tv_podium")
        podium_container.columnconfigure(2, weight=1, uniform="tv_podium")

        self.tv_prize_labels = []
        podium_specs = [
            ("🥇  1ST PLACE", Theme.GOLD),
            ("🥈  2ND PLACE", Theme.SILVER),
            ("🥉  3RD PLACE", Theme.BRONZE),
        ]

        for idx, (medal_title, accent_color) in enumerate(podium_specs):
            card = tk.Frame(
                podium_container,
                bg=Theme.BG_CARD,
                highlightbackground=Theme.BORDER,
                highlightthickness=1
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 10, 0 if idx == 2 else 10))

            top_stripe = tk.Frame(card, bg=accent_color, height=6)
            top_stripe.pack(fill=tk.X)

            inner = tk.Frame(card, bg=Theme.BG_CARD, padx=24, pady=18)
            inner.pack(fill=tk.BOTH, expand=True)

            tk.Label(
                inner,
                text=medal_title,
                font=("Segoe UI", 14, "bold"),
                fg=accent_color,
                bg=Theme.BG_CARD
            ).pack(anchor="w")

            lbl = tk.Label(
                inner,
                text="TBD",
                font=("Segoe UI", 22, "bold"),
                fg=Theme.TEXT_PRIMARY,
                bg=Theme.BG_CARD,
                wraplength=540,
                justify=tk.LEFT
            )
            lbl.pack(anchor="w", pady=(8, 0))
            self.tv_prize_labels.append(lbl)

        # 1080p View-Only Prize Wheel Card
        wheel_outer = tk.Frame(
            body,
            bg=Theme.BG_CARD,
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        wheel_outer.pack(fill=tk.BOTH, expand=True)

        self.tv_wheel_canvas = tk.Canvas(wheel_outer, bg="#f8fafc", highlightthickness=0)
        self.tv_wheel_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.tv_wheel_canvas.bind(
            "<Configure>",
            lambda e: self._render_wheel_canvas(self.tv_wheel_canvas, self.scroll_offset, self.active_winner_banner, is_tv=True)
        )

        self.refresh_prizing()

    def _render_wheel_canvas(self, canvas: tk.Canvas, offset: float = 0.0, winner_text: str | None = None, is_tv: bool = False):
        if not canvas or not canvas.winfo_exists():
            return

        canvas.delete("all")

        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        if canvas_width < 50:
            canvas_width = 1600 if is_tv else 800
        if canvas_height < 50:
            canvas_height = 650 if is_tv else 280

        cx = canvas_width / 2.0
        cy = canvas_height / 2.0

        if winner_text:
            canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#fffbeb", outline="")
            banner_font_size = 96 if is_tv else 72
            y_shift = int(canvas_height * 0.22)
            canvas.create_text(
                cx, cy - y_shift,
                text="🎉  WINNER  🎉",
                fill=Theme.AMBER_TEXT,
                font=("Segoe UI", banner_font_size, "bold")
            )

            name_font_size = 180 if is_tv else 140
            name_id = canvas.create_text(
                cx, cy + int(y_shift * 0.8),
                text=winner_text,
                fill=Theme.EMERALD_TEXT,
                font=("Segoe UI", name_font_size, "bold")
            )
            bbox = canvas.bbox(name_id)
            while bbox and (bbox[2] - bbox[0]) > (canvas_width - 80) and name_font_size > 36:
                name_font_size -= 6
                canvas.itemconfig(name_id, font=("Segoe UI", name_font_size, "bold"))
                bbox = canvas.bbox(name_id)
            return

        pool = self.event.get_wheel_pool()
        if not pool:
            canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#f1f5f9", outline="")
            empty_font_size = 24 if is_tv else 13
            canvas.create_text(
                cx, cy,
                text="No Eligible Entries Remaining on Wheel",
                fill=Theme.TEXT_MUTED,
                font=("Segoe UI", empty_font_size, "bold")
            )
            return

        if is_tv:
            panel_width = max(720.0, min(1280.0, canvas_width * 0.65))
            panel_height = max(76.0, min(116.0, canvas_height / 6.5))
            slot_font_size = max(20, int(panel_height * 0.30))
        else:
            panel_width = float(self.WHEEL_PANEL_WIDTH)
            panel_height = float(self.WHEEL_PANEL_HEIGHT)
            slot_font_size = 16

        # Scale offset proportionally so TV Wheel and Main Wheel always align on the exact same slot
        scaled_offset = offset * (panel_height / self.WHEEL_PANEL_HEIGHT)

        x1 = cx - panel_width / 2.0
        x2 = cx + panel_width / 2.0

        n = len(pool)
        total_span = n * panel_height
        norm_offset = scaled_offset % total_span

        palette = [
            "#e11d48", "#2563eb", "#059669", "#7c3aed",
            "#d97706", "#0891b2", "#4f46e5", "#be185d"
        ]

        visible_slots = int(canvas_height // panel_height) + 4
        start_i = -(visible_slots // 2)
        end_i = (visible_slots // 2) + 1

        for i in range(start_i, end_i):
            slot_idx = int((norm_offset // panel_height) + i)
            item_name = pool[slot_idx % n]
            color = palette[slot_idx % len(palette)]

            slot_y = cy + (i * panel_height) - (norm_offset % panel_height)

            canvas.create_rectangle(
                x1, slot_y - panel_height / 2.0,
                x2, slot_y + panel_height / 2.0,
                fill=color, outline="#ffffff", width=3
            )

            canvas.create_text(
                cx, slot_y,
                text=item_name,
                fill="#ffffff",
                font=("Segoe UI", slot_font_size, "bold")
            )

        # Side rails
        rail_w = 12 if is_tv else 8
        canvas.create_rectangle(
            x1 - rail_w, 0, x1, canvas_height, fill=Theme.BORDER, outline=""
        )
        canvas.create_rectangle(
            x2, 0, x2 + rail_w, canvas_height, fill=Theme.BORDER, outline=""
        )

        # Center pointers
        pointer_y = cy
        ptr_w = 64 if is_tv else 44
        ptr_h = 42 if is_tv else 30
        canvas.create_polygon(
            x1 + 4, pointer_y,
            x1 - ptr_w, pointer_y - ptr_h,
            x1 - ptr_w, pointer_y + ptr_h,
            fill=Theme.CRIMSON, outline="#ffffff", width=3 if is_tv else 2
        )
        canvas.create_polygon(
            x2 - 4, pointer_y,
            x2 + ptr_w, pointer_y - ptr_h,
            x2 + ptr_w, pointer_y + ptr_h,
            fill=Theme.CRIMSON, outline="#ffffff", width=3 if is_tv else 2
        )

    def draw_wheel(self, offset: float = 0.0, winner_text: str | None = None):
        self.active_winner_banner = winner_text
        self._render_wheel_canvas(self.wheel_canvas, offset, winner_text, is_tv=False)
        if self.tv_wheel_win and self.tv_wheel_win.winfo_exists():
            self._render_wheel_canvas(self.tv_wheel_canvas, offset, winner_text, is_tv=True)

    def handle_spin_wheel(self):
        if self.is_spinning:
            return

        pool = self.event.get_wheel_pool()
        if not pool:
            messagebox.showinfo("No Eligible Entries", "No eligible participants remaining on the wheel!")
            return

        self.is_spinning = True
        self.spin_btn.config(state=tk.DISABLED)

        winner = random.choice(pool)
        winner_idx = pool.index(winner)

        panel_height = self.WHEEL_PANEL_HEIGHT
        n = len(pool)

        current_base = self.scroll_offset % (n * panel_height)
        target_base = winner_idx * panel_height
        diff = (target_base - current_base) % (n * panel_height)
        if diff < panel_height:
            diff += n * panel_height

        extra_spins = random.randint(8, 12) * (n * panel_height)
        final_target_offset = self.scroll_offset + extra_spins + diff

        spin_duration = 7.0
        start_time = time.perf_counter()
        start_offset = self.scroll_offset

        def step_animation():
            if not self.root.winfo_exists():
                return
            elapsed = time.perf_counter() - start_time
            if elapsed < spin_duration:
                t = elapsed / spin_duration
                ease_t = 1.0 - (1.0 - t) ** 3
                self.scroll_offset = start_offset + (final_target_offset - start_offset) * ease_t
                self.draw_wheel(self.scroll_offset)
                self.root.after(16, step_animation)
            else:
                self.scroll_offset = final_target_offset
                self.draw_wheel(self.scroll_offset)
                self.event.random_winners.append(winner)
                self.event.save_state()
                self.refresh_prizing()

                def after_stop_pause():
                    if not self.root.winfo_exists():
                        return
                    self.draw_wheel(self.scroll_offset, winner_text=winner)

                    def finish_wait():
                        if not self.root.winfo_exists():
                            return
                        self.is_spinning = False
                        if self.event.is_tournament_complete():
                            self.spin_btn.config(text="🎰  SPIN AGAIN", state=tk.NORMAL)
                        self.draw_wheel(self.scroll_offset)

                    self.root.after(5000, finish_wait)

                self.root.after(2000, after_stop_pause)

        step_animation()

    def handle_show_final_standings(self):
        if not self.event.is_tournament_complete():
            messagebox.showinfo("Incomplete", "The tournament is not complete yet.")
            return

        if self.standings_win and self.standings_win.winfo_exists():
            self.standings_win.destroy()

        self.standings_win = tk.Toplevel(self.root)
        self.standings_win.title("Tournament Final Standings")
        self.standings_win.geometry("1200x900")
        self.standings_win.minsize(950, 650)
        self.standings_win.configure(bg=Theme.BG_MAIN)
        self._maximize_window(self.standings_win)

        if self.event.is_2hg_mode:
            sorted_items = self.event.get_sorted_teams_standings()
        else:
            sorted_items = self.event.get_sorted_standings()

        total_items = max(1, len(sorted_items))
        screen_height = self.standings_win.winfo_screenheight() or 1080
        available_height = screen_height - 150

        calculated_row_height = max(24, min(available_height // total_items, 42))
        calculated_font_size = max(10, min(int(calculated_row_height * 0.45), 18))

        style = ttk.Style(self.standings_win)
        style.configure(
            "DenseFinal.Treeview.Heading",
            font=("Segoe UI", calculated_font_size + 1, "bold"),
            background="#f1f5f9",
            foreground=Theme.TEXT_SECONDARY,
            relief="flat",
            padding=(8, 8)
        )
        style.configure(
            "DenseFinal.Treeview",
            font=("Segoe UI", calculated_font_size, "bold"),
            rowheight=calculated_row_height,
            background=Theme.BG_CARD,
            fieldbackground=Theme.BG_CARD,
            foreground=Theme.TEXT_PRIMARY,
            borderwidth=0
        )

        hdr_bar = tk.Frame(
            self.standings_win,
            bg=Theme.BG_DARKEST,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            pady=12
        )
        hdr_bar.pack(fill=tk.X)
        tk.Label(
            hdr_bar,
            text="🏆  TOURNAMENT FINAL STANDINGS",
            font=("Segoe UI", max(16, calculated_font_size + 4), "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_DARKEST
        ).pack()

        tree_frame = tk.Frame(
            self.standings_win,
            bg=Theme.BG_CARD,
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        columns = ("rank", "name", "pts", "opp_pts", "record")
        final_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="none",
            style="DenseFinal.Treeview"
        )
        final_tree.tag_configure("evenrow", background=Theme.BG_CARD)
        final_tree.tag_configure("oddrow", background=Theme.BG_ROW_ALT)
        final_tree.tag_configure("top1", background="#fef3c7", foreground=Theme.AMBER_TEXT)

        name_header_text = "TEAM" if self.event.is_2hg_mode else "PLAYER"
        headers = {
            "rank": ("RANK", 110, tk.CENTER, False),
            "name": (name_header_text, 460, tk.W, True),
            "pts": ("POINTS", 130, tk.CENTER, False),
            "opp_pts": ("OPP PTS (TB)", 160, tk.CENTER, False),
            "record": ("W - L - D", 160, tk.CENTER, False),
        }
        for col, (text, width, anchor, stretch) in headers.items():
            final_tree.heading(col, text=text)
            final_tree.column(col, width=width, anchor=anchor, stretch=stretch)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=final_tree.yview)
        final_tree.configure(yscrollcommand=tree_scroll.set)

        final_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for idx, item in enumerate(sorted_items, start=1):
            if self.event.is_2hg_mode:
                opp_pts = self.event.get_team_opponent_points(item)
                record = f"{item.wins} - {item.losses} - {item.draws}"
                p1 = self.event.players.get(item.player1)
                p2 = self.event.players.get(item.player2)
                has_rdv = (p1 and p1.is_rdv) or (p2 and p2.is_rdv)
                display_name = f"{item.name} [RDV]" if has_rdv else item.name
                pts = item.points
            else:
                opp_pts = self.event.get_opponent_points(item)
                record = f"{item.wins} - {item.losses} - {item.draws}"
                display_name = f"{item.name} [RDV]" if item.is_rdv else item.name
                pts = item.points

            row_tag = "top1" if idx == 1 else ("evenrow" if idx % 2 == 0 else "oddrow")
            final_tree.insert(
                "",
                tk.END,
                values=(f"#{idx}", display_name, pts, opp_pts, record),
                tags=(row_tag,)
            )

    def refresh_prizing(self):
        if self.event.is_2hg_mode:
            top3 = self.event.get_top_3_eligible_teams()
            for i in range(3):
                text_val = f"{top3[i].name}  ({top3[i].points} pts)" if i < len(top3) else "TBD"
                self.prize_labels[i].config(text=text_val)
                if self.tv_wheel_win and self.tv_wheel_win.winfo_exists() and i < len(self.tv_prize_labels):
                    self.tv_prize_labels[i].config(text=text_val)
        else:
            top3 = self.event.get_top_3_eligible()
            for i in range(3):
                text_val = f"{top3[i].name}  ({top3[i].points} pts)" if i < len(top3) else "TBD"
                self.prize_labels[i].config(text=text_val)
                if self.tv_wheel_win and self.tv_wheel_win.winfo_exists() and i < len(self.tv_prize_labels):
                    self.tv_prize_labels[i].config(text=text_val)

        if self.event.random_winners:
            winner_str = f"🎉  Last Winner: {self.event.random_winners[-1]}"
        else:
            winner_str = "Last Winner: None yet"

        self.last_winner_lbl.config(text=winner_str)

        if self.event.is_tournament_complete():
            if not self.is_spinning:
                btn_text = "🎰  SPIN AGAIN" if self.event.random_winners else "🎰  SPIN PRIZE WHEEL"
                self.spin_btn.config(text=btn_text, state=tk.NORMAL)
            self.final_standings_btn.config(state=tk.NORMAL)
        else:
            self.spin_btn.config(state=tk.DISABLED)
            self.final_standings_btn.config(state=tk.DISABLED)

        if not self.is_spinning:
            self.draw_wheel(self.scroll_offset)

    def disable_demo_buttons(self):
        self.demo_btn.config(state=tk.DISABLED)
        self.demo2_btn.config(state=tk.DISABLED)
        self.demo_2hg_btn.config(state=tk.DISABLED)

    def _update_registration_locks(self):
        state = tk.DISABLED if self.event.is_tournament_complete() else tk.NORMAL
        self.late_btn.config(state=state)
        self.paid_btn.config(state=state)
        self.edit_btn.config(state=state)
        self.lock_btn.config(state=state)
        self.rdv_btn.config(state=state)
        self.drop_btn.config(state=state)
        self.teams_btn.config(state=state)
        self.mode_2hg_btn.config(state=tk.DISABLED if self.event.round_number > 0 else tk.NORMAL)

    def handle_demo_mode(self):
        if self.event.round_number > 0:
            messagebox.showwarning("Locked", "Cannot load demo mode after the tournament has started.")
            return

        self.disable_demo_buttons()

        added_count = 0
        rdv_count = 0
        for name in self.DEMO_PLAYERS:
            success, _ = self.event.add_player(name)
            if success:
                added_count += 1
                if "(RDV)" in name:
                    rdv_count += 1

        if self.event.is_2hg_mode:
            active_players = self.event.get_active_players()
            self.event.teams_2hg = []
            for i in range(0, len(active_players) - 1, 2):
                self.event.teams_2hg.append(Team2HG(active_players[i].name, active_players[i + 1].name))
            self.event.save_state()

        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()
        messagebox.showinfo("Demo Mode Active", f"Successfully loaded {added_count} demo players (including {rdv_count} RDV tagged players).")

    def handle_demo_mode_2(self):
        if self.event.round_number > 0:
            messagebox.showwarning("Locked", "Cannot load demo mode after the tournament has started.")
            return

        self.disable_demo_buttons()

        for name in self.DEMO_PLAYERS:
            self.event.add_player(name)

        if self.event.is_2hg_mode:
            active_players = self.event.get_active_players()
            self.event.teams_2hg = []
            for i in range(0, len(active_players) - 1, 2):
                self.event.teams_2hg.append(Team2HG(active_players[i].name, active_players[i + 1].name))

        for _ in range(3):
            self.event.create_next_round()
            for pod_idx in range(len(self.event.current_pods)):
                if self.event.pod_outcomes[pod_idx] is not None:
                    continue
                pod = self.event.current_pods[pod_idx]
                if self.event.is_2hg_mode:
                    pod_teams = self.event.get_pod_teams_2hg(pod)
                    winner_team = random.choice(pod_teams)
                    self.event.record_result(pod_idx, winner_team=winner_team, is_draw=False)
                else:
                    winner = random.choice(pod)
                    self.event.record_result(pod_idx, winner=winner, is_draw=False)

        self.round_label.config(text="★  TOURNAMENT FINALIZED")
        self.next_round_btn.config(text="✓  Tournament Finalized", state=tk.DISABLED)
        self.player_entry.config(state=tk.DISABLED)
        self.add_btn.config(state=tk.DISABLED)
        self._update_registration_locks()
        self.event.save_state()

        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()
        self.notebook.select(self.prizing_tab)
        messagebox.showinfo("Demo 2 Active", "Loaded post-tournament state! All 3 rounds simulated. Check the Prizing tab.")

    def handle_demo_mode_2hg(self):
        if self.event.round_number > 0:
            messagebox.showwarning("Locked", "Cannot load demo mode after the tournament has started.")
            return

        self.disable_demo_buttons()

        self.event.is_2hg_mode = True
        self.event.global_swap_selection = None
        self.event.global_team_swap_selection = None

        added_count = 0
        for name in self.DEMO_PLAYERS:
            success, _ = self.event.add_player(name)
            if success:
                added_count += 1

        active_players = self.event.get_active_players()
        self.event.teams_2hg = []
        for i in range(0, len(active_players) - 1, 2):
            self.event.teams_2hg.append(Team2HG(active_players[i].name, active_players[i + 1].name))

        self.event.save_state()
        self._refresh_all_views()
        if self.team_builder_win and self.team_builder_win.winfo_exists():
            self.team_builder_win.populate_content()

        messagebox.showinfo(
            "2HG Demo Mode Active",
            f"2HG Mode enabled! Loaded {added_count} demo players and automatically paired them into {len(self.event.teams_2hg)} teams.\n\nReady for Round 1 to begin!"
        )

    def handle_add_players(self):
        raw_text = self.player_entry.get()
        if not raw_text.strip():
            return

        self.disable_demo_buttons()

        names = [n.strip() for n in raw_text.split(",") if n.strip()]
        errors = []
        for name in names:
            success, msg = self.event.add_player(name)
            if not success:
                errors.append(msg)

        self.player_entry.delete(0, tk.END)
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()
        if self.team_builder_win and self.team_builder_win.winfo_exists():
            self.team_builder_win.populate_content()

        if errors:
            messagebox.showwarning("Registration Notice", "\n".join(errors))

    def handle_add_late_player(self):
        if self.event.is_tournament_complete():
            messagebox.showwarning("Tournament Complete", "Cannot add late players after the tournament is finalized.")
            return

        name_input = simpledialog.askstring("Add Late Player", "Enter late player name (use * or RDV suffix for RDV tag):", parent=self.root)
        if name_input:
            self.disable_demo_buttons()
            success, msg = self.event.add_player(name_input)
            if success:
                self.refresh_pods()
                self.refresh_standings()
                self.refresh_prizing()
                if self.team_builder_win and self.team_builder_win.winfo_exists():
                    self.team_builder_win.populate_content()
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showwarning("Error", msg)

    def handle_edit_player_name(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select a Player", "Please select a player on the Player Manager first.")
            return
        if len(selected) > 1:
            messagebox.showinfo("Single Player Only", "Please select only a single player to edit their name.")
            return

        old_name = selected[0]
        new_name_input = simpledialog.askstring(
            "Edit Player Name",
            f"Enter new name for '{old_name}' (use * or RDV suffix to add RDV tag):",
            initialvalue=old_name,
            parent=self.root
        )
        if new_name_input is not None:
            success, msg = self.event.edit_player_name(old_name, new_name_input)
            if success:
                new_clean_name, _ = CommanderEvent._parse_raw_name(new_name_input)
                self.refresh_pods()
                self.refresh_standings(select_names=[new_clean_name])
                self.refresh_prizing()
                if self.team_builder_win and self.team_builder_win.winfo_exists():
                    self.team_builder_win.populate_content()
            else:
                messagebox.showwarning("Error", msg)

    def handle_set_table_lock(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Player(s)", "Please select one or more players on the Player Manager first.")
            return

        first_player = self.event.players.get(selected[0])
        if not first_player:
            return

        current_val = str(first_player.locked_table + 1) if len(selected) == 1 and first_player.locked_table is not None else ""
        target_label = f"'{first_player.name}'" if len(selected) == 1 else f"{len(selected)} selected players"

        res = simpledialog.askstring(
            "Table Lock",
            f"Enter table number for {target_label} (1, 2, 3...)\nLeave blank or enter 0 to clear lock:",
            initialvalue=current_val,
            parent=self.root
        )
        if res is not None:
            res = res.strip()
            if not res or res == "0":
                target_table = None
            else:
                try:
                    table_num = int(res)
                    target_table = None if table_num < 1 else table_num - 1
                except ValueError:
                    messagebox.showwarning("Invalid Input", "Please enter a valid integer table number.")
                    return

            for clean_name in selected:
                player = self.event.players.get(clean_name)
                if not player:
                    continue
                player.locked_table = target_table
                team = self.event.get_player_team(player.name)
                if team:
                    team.locked_table = target_table
                    p1_obj = self.event.players.get(team.player1)
                    p2_obj = self.event.players.get(team.player2)
                    if p1_obj:
                        p1_obj.locked_table = target_table
                    if p2_obj:
                        p2_obj.locked_table = target_table

            self.event.save_state()
            self.refresh_pods()
            self.refresh_standings(select_names=selected)
            self.refresh_prizing()
            if self.team_builder_win and self.team_builder_win.winfo_exists():
                self.team_builder_win.populate_content()

    def handle_toggle_paid_button(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Player(s)", "Please select one or more players on the Player Manager first.")
            return

        if len(selected) == 1:
            clean_name = selected[0]
            player = self.event.players.get(clean_name)
            if player and player.is_rdv:
                messagebox.showinfo("RDV Notice", "Players with an RDV tag must always maintain paid status.")
                return
            success, msg = self.event.toggle_paid(clean_name)
            if not success:
                messagebox.showwarning("Paid Status Error", msg)
                return
        else:
            non_rdv_players = [
                self.event.players[name]
                for name in selected
                if name in self.event.players and not self.event.players[name].is_rdv
            ]
            if not non_rdv_players:
                messagebox.showinfo("RDV Notice", "All selected players have an RDV tag and must maintain paid status.")
                return
            target_paid_state = any(not p.paid for p in non_rdv_players)
            for p in non_rdv_players:
                p.paid = target_paid_state
            self.event.save_state()

        self.refresh_pods()
        self.refresh_standings(select_names=selected)
        self.refresh_prizing()

    def handle_tree_double_click(self, event):
        if self.event.is_tournament_complete():
            return
        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        player = self.event.players.get(row_id)
        if player and player.is_rdv:
            messagebox.showinfo("RDV Notice", "Players with an RDV tag must always maintain paid status.")
            return

        success, msg = self.event.toggle_paid(row_id)
        if success:
            self.refresh_pods()
            self.refresh_standings(select_names=self.tree.selection())
            self.refresh_prizing()
        else:
            messagebox.showwarning("Paid Status Error", msg)

    def handle_toggle_rdv(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Player(s)", "Please select one or more players on the Player Manager first.")
            return

        if len(selected) == 1:
            self.event.toggle_rdv(selected[0])
        else:
            players_list = [self.event.players[name] for name in selected if name in self.event.players]
            target_rdv = any(not p.is_rdv for p in players_list)
            for p in players_list:
                p.is_rdv = target_rdv
                if p.is_rdv:
                    p.paid = True
            self.event.save_state()

        self.refresh_pods()
        self.refresh_standings(select_names=selected)
        self.refresh_prizing()
        if self.team_builder_win and self.team_builder_win.winfo_exists():
            self.team_builder_win.populate_content()

    def handle_drop_player(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Player(s)", "Please select one or more players on the Player Manager first.")
            return

        active_selected = [
            self.event.players[name]
            for name in selected
            if name in self.event.players and not self.event.players[name].dropped
        ]
        if not active_selected:
            messagebox.showinfo("Already Dropped", "The selected player(s) have already been dropped from the tournament.")
            return

        names_str = f"'{active_selected[0].name}'" if len(active_selected) == 1 else f"{len(active_selected)} selected players"
        team_notice = ""
        if self.event.is_2hg_mode:
            if self.event.round_number == 0:
                team_notice = "\n\nNote: Any 2HG teams containing these players will be disbanded and their table locks cleared."
            else:
                team_notice = "\n\nNote: Because 2HG is active, their entire 2HG team(s) will be dropped from future rounds."

        msg_text = (
            f"Are you sure you want to drop {names_str} from the tournament?{team_notice}\n\n"
            f"Logged scores will remain valid on the Player Manager and count toward opponents' tiebreakers, "
            f"but they will not be placed into pods in future rounds."
        )
        if messagebox.askyesno("Confirm Player Drop", msg_text):
            for p in active_selected:
                if not p.dropped:
                    self.event.drop_player(p.name)
            self.refresh_pods()
            self.refresh_standings(select_names=selected)
            self.refresh_prizing()
            if self.team_builder_win and self.team_builder_win.winfo_exists():
                self.team_builder_win.populate_content()

    # --- Context Menu Action Handlers ---
    def handle_context_paid(self):
        self.handle_toggle_paid_button()

    def handle_context_edit(self):
        self.handle_edit_player_name()

    def handle_context_lock(self):
        self.handle_set_table_lock()

    def handle_context_rdv(self):
        self.handle_toggle_rdv()

    def handle_context_drop(self):
        self.handle_drop_player()

    def handle_swap_player(self, pod_idx: int, player: Player):
        if self.event.global_swap_selection is None:
            self.event.global_swap_selection = (pod_idx, player)
            self.refresh_pods()
        else:
            p1_pod_idx, p1_player = self.event.global_swap_selection
            p2_pod_idx, p2_player = pod_idx, player

            if p1_pod_idx == p2_pod_idx:
                self.event.global_swap_selection = None
                self.refresh_pods()
                return

            pod1 = self.event.current_pods[p1_pod_idx]
            pod2 = self.event.current_pods[p2_pod_idx]

            if p1_player in pod1 and p2_player in pod2:
                idx1 = pod1.index(p1_player)
                idx2 = pod2.index(p2_player)
                pod1[idx1], pod2[idx2] = pod2[idx2], pod1[idx1]
                self.event.recalculate_warnings()

            self.event.global_swap_selection = None
            self.event.save_state()
            self.refresh_pods()

    def handle_move_player_dialog(self, current_pod_idx: int, player: Player):
        total_pods = len(self.event.current_pods)
        if total_pods < 2:
            messagebox.showinfo("Single Pod", "There is only one active pod available.")
            return

        pod_choices = [
            f"Table {i + 1}"
            for i in range(total_pods)
            if i != current_pod_idx and self.event.pod_outcomes[i] is None
        ]
        if not pod_choices:
            messagebox.showinfo("No Eligible Tables", "All other tables have already completed their matches.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Move {player.name}")
        dialog.geometry("320x180")
        dialog.resizable(False, False)
        dialog.configure(bg=Theme.BG_CARD)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text=f"Move '{player.name}' to which table?",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.TEXT_PRIMARY,
            bg=Theme.BG_CARD
        ).pack(pady=(20, 10))

        selected_choice = tk.StringVar(value=pod_choices[0])
        dropdown = ttk.Combobox(dialog, textvariable=selected_choice, values=pod_choices, state="readonly", width=18)
        dropdown.pack(pady=4)

        def confirm_move():
            choice_str = selected_choice.get()
            target_pod_num = int(choice_str.replace("Table ", ""))
            target_pod_idx = target_pod_num - 1

            if player in self.event.current_pods[current_pod_idx]:
                self.event.current_pods[current_pod_idx].remove(player)
                self.event.current_pods[target_pod_idx].append(player)

                if len(self.event.current_pods[current_pod_idx]) == 0:
                    del self.event.current_pods[current_pod_idx]
                    del self.event.pod_outcomes[current_pod_idx]

                self.event.global_swap_selection = None
                self.event.recalculate_warnings()
                self.event.save_state()

            dialog.destroy()
            self.refresh_pods()

        ttk.Button(dialog, text="Confirm Move", style="Edit.TButton", command=confirm_move).pack(pady=(16, 0))

    def handle_swap_team_2hg(self, pod_idx: int, team: Team2HG):
        if self.event.global_team_swap_selection is None:
            self.event.global_team_swap_selection = (pod_idx, team)
            self.refresh_pods()
        else:
            t1_pod_idx, t1_team = self.event.global_team_swap_selection
            t2_pod_idx, t2_team = pod_idx, team

            if t1_pod_idx == t2_pod_idx:
                self.event.global_team_swap_selection = None
                self.refresh_pods()
                return

            pod1 = self.event.current_pods[t1_pod_idx]
            pod2 = self.event.current_pods[t2_pod_idx]

            idx1 = next(
                (k for k in range(0, len(pod1) - 1, 2)
                 if pod1[k].name == t1_team.player1 and pod1[k + 1].name == t1_team.player2),
                None
            )
            idx2 = next(
                (k for k in range(0, len(pod2) - 1, 2)
                 if pod2[k].name == t2_team.player1 and pod2[k + 1].name == t2_team.player2),
                None
            )

            if idx1 is not None and idx2 is not None:
                o1 = self.event.pod_outcomes[t1_pod_idx]
                o2 = self.event.pod_outcomes[t2_pod_idx]
                pod1_is_bye = (o1 is not None and o1.get("type") == "BYE")
                pod2_is_bye = (o2 is not None and o2.get("type") == "BYE")

                if pod1_is_bye:
                    self.event._revert_bye_2hg(t1_pod_idx)
                if pod2_is_bye:
                    self.event._revert_bye_2hg(t2_pod_idx)

                pod1[idx1], pod1[idx1 + 1], pod2[idx2], pod2[idx2 + 1] = (
                    pod2[idx2], pod2[idx2 + 1], pod1[idx1], pod1[idx1 + 1]
                )

                if pod1_is_bye:
                    self.event._apply_bye_2hg(t1_pod_idx, t2_team)
                if pod2_is_bye:
                    self.event._apply_bye_2hg(t2_pod_idx, t1_team)

                self.event.recalculate_warnings()

            self.event.global_team_swap_selection = None
            self.event.save_state()
            self.refresh_pods()
            self.refresh_standings()
            self.refresh_prizing()

    def handle_move_team_dialog_2hg(self, current_pod_idx: int, team: Team2HG):
        total_pods = len(self.event.current_pods)
        pod_choices = [
            f"Table {i + 1}"
            for i in range(total_pods)
            if i != current_pod_idx and self.event.pod_outcomes[i] is None
        ]
        if len(self.event.current_pods[current_pod_idx]) > 2:
            pod_choices.append("New Table")

        if not pod_choices:
            messagebox.showinfo("No Eligible Tables", "No other incomplete tables are available to move this team to.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Move {team.name}")
        dialog.geometry("360x185")
        dialog.resizable(False, False)
        dialog.configure(bg=Theme.BG_CARD)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text=f"Move '{team.name}' to which table?",
            font=("Segoe UI", 10, "bold"),
            fg=Theme.TEXT_PRIMARY,
            bg=Theme.BG_CARD,
            wraplength=320
        ).pack(pady=(20, 10))

        selected_choice = tk.StringVar(value=pod_choices[0])
        dropdown = ttk.Combobox(dialog, textvariable=selected_choice, values=pod_choices, state="readonly", width=18)
        dropdown.pack(pady=4)

        def confirm_move():
            choice_str = selected_choice.get()
            p1_obj = self.event.players.get(team.player1)
            p2_obj = self.event.players.get(team.player2)
            current_pod = self.event.current_pods[current_pod_idx]

            if p1_obj in current_pod and p2_obj in current_pod:
                current_pod.remove(p1_obj)
                current_pod.remove(p2_obj)

                if choice_str == "New Table":
                    bye_idx = next(
                        (idx for idx, o in enumerate(self.event.pod_outcomes)
                         if o is not None and o.get("type") == "BYE"),
                        None
                    )
                    if bye_idx is not None:
                        self.event.current_pods.insert(bye_idx, [p1_obj, p2_obj])
                        self.event.pod_outcomes.insert(bye_idx, None)
                    else:
                        self.event.current_pods.append([p1_obj, p2_obj])
                        self.event.pod_outcomes.append(None)
                else:
                    target_pod_num = int(choice_str.replace("Table ", ""))
                    target_pod_idx = target_pod_num - 1
                    self.event.current_pods[target_pod_idx].extend([p1_obj, p2_obj])

                if len(self.event.current_pods[current_pod_idx]) == 0:
                    del self.event.current_pods[current_pod_idx]
                    del self.event.pod_outcomes[current_pod_idx]

                self.event.global_team_swap_selection = None
                self.event.recalculate_warnings()
                self.event.save_state()

            dialog.destroy()
            self.refresh_pods()

        ttk.Button(dialog, text="Confirm Move", style="Edit.TButton", command=confirm_move).pack(pady=(16, 0))

    def handle_show_pairings_window(self):
        if not self.event.current_pods:
            messagebox.showinfo("No Pairings", "No active round or pairings generated yet.")
            return

        if self.pairings_win and self.pairings_win.winfo_exists():
            self._populate_pairings_window()
            self.pairings_win.lift()
            return

        self.pairings_win = tk.Toplevel(self.root)
        self.pairings_win.title(f"Round {self.event.round_number} - Table Pairings")
        self.pairings_win.geometry("1280x860")
        self.pairings_win.configure(bg=Theme.BG_MAIN)
        self._maximize_window(self.pairings_win)

        hdr_bar = tk.Frame(
            self.pairings_win,
            bg=Theme.BG_DARKEST,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            pady=10
        )
        hdr_bar.pack(fill=tk.X)

        self.pairings_header_lbl = tk.Label(
            hdr_bar,
            text=f"⚔  ROUND {self.event.round_number} — TABLE PAIRINGS",
            font=("Segoe UI", 18, "bold"),
            fg=Theme.CRIMSON,
            bg=Theme.BG_DARKEST
        )
        self.pairings_header_lbl.pack()

        self.pairings_content_frame = tk.Frame(self.pairings_win, bg=Theme.BG_MAIN, padx=10, pady=10)
        self.pairings_content_frame.pack(fill=tk.BOTH, expand=True)

        self._populate_pairings_window()

    def handle_repod(self):
        success, msg = self.event.regenerate_current_round_pods()
        if success:
            self.refresh_pods()
            self.refresh_standings()
            self.refresh_prizing()
            messagebox.showinfo("Re-Pod Success", msg)
        else:
            messagebox.showwarning("Cannot Re-Pod", msg)

    def handle_next_round(self):
        if self.event.round_number >= self.event.max_rounds:
            messagebox.showinfo("Tournament Ended", "The tournament has reached its 3-round limit. Final standings are locked.")
            return

        success, msg = self.event.create_next_round()
        if not success:
            messagebox.showwarning("Cannot Advance Round", msg)
            return

        self.disable_demo_buttons()

        if self.event.round_number == self.event.max_rounds:
            self.round_label.config(text=f"ROUND {self.event.round_number} OF 3  •  FINAL ROUND")
            self.next_round_btn.config(text="✓  Tournament Finalized", state=tk.DISABLED)
            self.player_entry.config(state=tk.DISABLED)
            self.add_btn.config(state=tk.DISABLED)
        else:
            mode = "RANDOM PAIRINGS" if self.event.round_number == 1 else "SWISS STANDINGS"
            self.round_label.config(text=f"ROUND {self.event.round_number} OF 3  •  {mode}")
            self.next_round_btn.config(text=f"▶  Start Round {self.event.round_number + 1}")

        if not self.event.is_2hg_mode and len(self.event.get_active_players()) == 5 and self.event.round_number == 1:
            messagebox.showinfo("5-Player Notice", "5 active players cannot be split into pods of 3 and 4. Created one pod of 5.")

        self._update_registration_locks()
        if self.team_builder_win and self.team_builder_win.winfo_exists():
            self.team_builder_win.populate_content()
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()
        self.notebook.select(self.pods_tab)

    def handle_record_win_2hg(self, pod_idx: int, winning_team: Team2HG):
        self.event.record_result(pod_idx, winner_team=winning_team, is_draw=False)
        self._update_registration_locks()
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()

        if self.event.is_tournament_complete():
            self.round_label.config(text="★  TOURNAMENT FINALIZED")
            messagebox.showinfo("Tournament Complete", "All 3 rounds have been completed! Final standings and prizing are locked.")

    def handle_record_win(self, pod_idx: int, winner: Player):
        self.event.record_result(pod_idx, winner=winner, is_draw=False)
        self._update_registration_locks()
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()

        if self.event.is_tournament_complete():
            self.round_label.config(text="★  TOURNAMENT FINALIZED")
            messagebox.showinfo("Tournament Complete", "All 3 rounds have been completed! Final standings and prizing are locked.")

    def handle_record_draw(self, pod_idx: int):
        self.event.record_result(pod_idx, is_draw=True)
        self._update_registration_locks()
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()

        if self.event.is_tournament_complete():
            self.round_label.config(text="★  TOURNAMENT FINALIZED")
            messagebox.showinfo("Tournament Complete", "All 3 rounds have been completed! Final standings and prizing are locked.")

    def handle_undo(self, pod_idx: int):
        self.event.undo_result(pod_idx)
        self._update_registration_locks()
        if self.event.round_number == self.event.max_rounds:
            self.round_label.config(text="ROUND 3 OF 3  •  FINAL ROUND")
            self.next_round_btn.config(text="✓  Tournament Finalized", state=tk.DISABLED)
        self.refresh_pods()
        self.refresh_standings()
        self.refresh_prizing()

    def _populate_pairings_window(self):
        if not self.pairings_win or not self.pairings_win.winfo_exists():
            return

        self.pairings_header_lbl.config(text=f"⚔  ROUND {self.event.round_number} — TABLE PAIRINGS")
        for widget in self.pairings_content_frame.winfo_children():
            widget.destroy()

        for col in range(4):
            self.pairings_content_frame.columnconfigure(col, weight=0, uniform="")
        for row in range(10):
            self.pairings_content_frame.rowconfigure(row, weight=0)

        total_tables = len(self.event.current_pods)
        if total_tables == 0:
            return

        num_cols = 3 if total_tables >= 7 else (2 if total_tables >= 3 else 1)
        num_rows = (total_tables + num_cols - 1) // num_cols

        for c in range(num_cols):
            self.pairings_content_frame.columnconfigure(c, weight=1, uniform="pairings_col")
        for r in range(num_rows):
            self.pairings_content_frame.rowconfigure(r, weight=1)

        if num_rows <= 3:
            num_font_size = 64
            name_font_size = 32
        else:
            scale = 3.0 / num_rows
            num_font_size = max(36, int(64 * scale))
            name_font_size = max(18, int(32 * scale))

        for i, pod in enumerate(self.event.current_pods):
            outcome = self.event.pod_outcomes[i] if i < len(self.event.pod_outcomes) else None
            is_bye = (outcome is not None and outcome.get("type") == "BYE")
            row_idx = i // num_cols
            col_idx = i % num_cols

            table_container = tk.Frame(
                self.pairings_content_frame,
                bg=Theme.BG_CARD,
                highlightbackground=Theme.BORDER,
                highlightthickness=1
            )
            table_container.grid(row=row_idx, column=col_idx, sticky="nsew", padx=6, pady=6)

            box_text = "BYE" if is_bye else str(i + 1)
            box_font_size = max(26, int(num_font_size * 0.55)) if is_bye else num_font_size
            box_bg = Theme.VIOLET if is_bye else Theme.CRIMSON

            num_box = tk.Label(
                table_container,
                text=box_text,
                font=("Segoe UI", box_font_size, "bold"),
                fg="#ffffff",
                bg=box_bg,
                padx=14,
                anchor=tk.CENTER
            )
            num_box.pack(side=tk.LEFT, fill=tk.Y)

            card = tk.Frame(table_container, bg=Theme.BG_CARD, padx=12, pady=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            if self.event.is_2hg_mode:
                pod_teams = self.event.get_pod_teams_2hg(pod)
                winner_team = outcome.get("winner_team") if outcome else None

                for tm in pod_teams:
                    tm_fg = Theme.TEXT_PRIMARY
                    if outcome is not None:
                        if outcome["type"] == "DRAW":
                            tm_fg = Theme.BLUE
                        elif outcome["type"] in ("WIN", "BYE") and winner_team == tm:
                            tm_fg = Theme.EMERALD_TEXT

                    for p_text in (f"{tm.player1} &", tm.player2):
                        row = tk.Frame(card, bg=Theme.BG_CARD)
                        row.pack(fill=tk.X, pady=0)
                        tk.Label(
                            row,
                            text=p_text,
                            font=("Segoe UI", name_font_size, "bold"),
                            fg=tm_fg,
                            bg=Theme.BG_CARD,
                            anchor="w"
                        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            else:
                for player in pod:
                    row = tk.Frame(card, bg=Theme.BG_CARD)
                    row.pack(fill=tk.X, pady=0)

                    name_fg = Theme.TEXT_PRIMARY
                    if outcome is not None:
                        if outcome["type"] == "DRAW":
                            name_fg = Theme.BLUE
                        elif outcome["type"] == "WIN" and outcome["winner"] == player:
                            name_fg = Theme.EMERALD_TEXT

                    tk.Label(
                        row,
                        text=player.name,
                        font=("Segoe UI", name_font_size, "bold"),
                        fg=name_fg,
                        bg=Theme.BG_CARD,
                        anchor="w"
                    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def refresh_pods(self):
        for widget in self.pods_frame.winfo_children():
            widget.destroy()

        if self.event.is_2hg_mode:
            active_teams = [t for t in self.event.teams_2hg if not t.dropped]
            if not active_teams:
                empty_lbl = tk.Label(
                    self.pods_frame,
                    text="No 2HG teams created yet.\nClick '👥 Manage Teams' on the Player Manager tab to pair players into teams.",
                    font=("Segoe UI", 11),
                    fg=Theme.TEXT_MUTED,
                    bg=Theme.BG_MAIN,
                    justify=tk.CENTER
                )
                empty_lbl.pack(pady=60)
                return
            if not self.event.current_pods:
                empty_lbl = tk.Label(
                    self.pods_frame,
                    text=f"Teams Ready ({len(active_teams)} active teams).\nClick '▶ Start Round 1' on the top bar when ready.",
                    font=("Segoe UI", 11),
                    fg=Theme.TEXT_MUTED,
                    bg=Theme.BG_MAIN,
                    justify=tk.CENTER
                )
                empty_lbl.pack(pady=60)
                return
        else:
            if not self.event.current_pods:
                active_count = len(self.event.get_active_players())
                empty_lbl = tk.Label(
                    self.pods_frame,
                    text=f"No active pods yet ({active_count} active players registered).\nAdd at least 3 players and click '▶ Start Round 1'.",
                    font=("Segoe UI", 11),
                    fg=Theme.TEXT_MUTED,
                    bg=Theme.BG_MAIN,
                    justify=tk.CENTER
                )
                empty_lbl.pack(pady=60)
                return

        self.pods_frame.columnconfigure(0, weight=1)
        self.pods_frame.columnconfigure(1, weight=1)

        for i, pod in enumerate(self.event.current_pods):
            outcome = self.event.pod_outcomes[i]
            is_bye = (outcome is not None and outcome.get("type") == "BYE")

            row_idx = i // 2
            col_idx = i % 2

            # Modern Pod Card Container
            border_color = Theme.VIOLET if is_bye else (Theme.EMERALD if outcome else Theme.BORDER)
            card_outer = tk.Frame(
                self.pods_frame,
                bg=Theme.BG_CARD,
                highlightbackground=border_color,
                highlightthickness=1
            )
            card_outer.grid(row=row_idx, column=col_idx, sticky="nsew", padx=8, pady=8)

            # Card Header Bar
            card_hdr = tk.Frame(card_outer, bg=Theme.BG_CARD_HEADER, padx=14, pady=8)
            card_hdr.pack(fill=tk.X)

            title_text = "★  BYE POD" if is_bye else f"TABLE {i + 1}"
            tk.Label(
                card_hdr,
                text=title_text,
                font=("Segoe UI", 11, "bold"),
                fg=Theme.TEXT_PRIMARY,
                bg=Theme.BG_CARD_HEADER
            ).pack(side=tk.LEFT)

            if is_bye:
                badge_text, badge_fg = "★ AUTOMATIC BYE (+3 PTS)", Theme.VIOLET
            elif outcome:
                badge_text, badge_fg = "✓ COMPLETE", Theme.EMERALD_TEXT
            else:
                badge_text, badge_fg = "● IN PROGRESS", Theme.AMBER_TEXT

            tk.Label(
                card_hdr,
                text=badge_text,
                font=("Segoe UI", 9, "bold"),
                fg=badge_fg,
                bg=Theme.BG_CARD_HEADER
            ).pack(side=tk.RIGHT)

            # Card Body
            card = tk.Frame(card_outer, bg=Theme.BG_CARD, padx=14, pady=12)
            card.pack(fill=tk.BOTH, expand=True)

            if is_bye and self.event.is_2hg_mode:
                pod_teams = self.event.get_pod_teams_2hg(pod)
                for team in pod_teams:
                    t_frame = tk.Frame(
                        card,
                        bg=Theme.BG_ROW_ALT,
                        highlightbackground="#e2e8f0",
                        highlightthickness=1,
                        padx=10,
                        pady=8
                    )
                    t_frame.pack(fill=tk.X, pady=4)

                    lock_tag = f"  🔒 [T{team.locked_table + 1}]" if team.locked_table is not None else ""
                    is_selected = (
                        self.event.global_team_swap_selection is not None
                        and self.event.global_team_swap_selection[0] == i
                        and self.event.global_team_swap_selection[1] == team
                    )
                    lbl_fg = Theme.BLUE if is_selected else Theme.TEXT_PRIMARY

                    tk.Label(
                        t_frame,
                        text=f"{team.name}{lock_tag}   •   {team.points} pts",
                        font=("Segoe UI", 10, "bold"),
                        fg=lbl_fg,
                        bg=Theme.BG_ROW_ALT
                    ).pack(side=tk.LEFT)

                    swap_text = "✓ ↔" if is_selected else "↔"
                    swap_style = "SwapActive.TButton" if is_selected else "Small.TButton"
                    ttk.Button(
                        t_frame,
                        text=swap_text,
                        style=swap_style,
                        width=4,
                        command=lambda idx=i, tm=team: self.handle_swap_team_2hg(idx, tm)
                    ).pack(side=tk.RIGHT, padx=2)

                tk.Label(
                    card,
                    text="✓  Automatic Bye Awarded (+3 pts)",
                    fg=Theme.EMERALD_TEXT,
                    bg=Theme.BG_CARD,
                    font=("Segoe UI", 9, "bold")
                ).pack(anchor="w", pady=(8, 0))

            elif outcome is None:
                if self.event.is_2hg_mode:
                    pod_teams = self.event.get_pod_teams_2hg(pod)

                    for team in pod_teams:
                        t_frame = tk.Frame(
                            card,
                            bg=Theme.BG_ROW_ALT,
                            highlightbackground="#e2e8f0",
                            highlightthickness=1,
                            padx=10,
                            pady=7
                        )
                        t_frame.pack(fill=tk.X, pady=3)

                        lock_tag = f"  🔒 [T{team.locked_table + 1}]" if team.locked_table is not None else ""
                        is_selected = (
                            self.event.global_team_swap_selection is not None
                            and self.event.global_team_swap_selection[0] == i
                            and self.event.global_team_swap_selection[1] == team
                        )
                        lbl_fg = Theme.BLUE if is_selected else Theme.TEXT_PRIMARY

                        tk.Label(
                            t_frame,
                            text=f"{team.name}{lock_tag}   •   {team.points} pts",
                            font=("Segoe UI", 10, "bold"),
                            fg=lbl_fg,
                            bg=Theme.BG_ROW_ALT
                        ).pack(side=tk.LEFT)

                        ttk.Button(
                            t_frame,
                            text="Won (+3)",
                            style="Win.TButton",
                            command=lambda idx=i, tm=team: self.handle_record_win_2hg(idx, tm)
                        ).pack(side=tk.RIGHT, padx=(4, 0))

                        swap_text = "✓ ↔" if is_selected else "↔"
                        swap_style = "SwapActive.TButton" if is_selected else "Small.TButton"
                        ttk.Button(
                            t_frame,
                            text=swap_text,
                            style=swap_style,
                            width=4,
                            command=lambda idx=i, tm=team: self.handle_swap_team_2hg(idx, tm)
                        ).pack(side=tk.RIGHT, padx=2)

                        ttk.Button(
                            t_frame,
                            text="M",
                            style="Move.TButton",
                            width=3,
                            command=lambda idx=i, tm=team: self.handle_move_team_dialog_2hg(idx, tm)
                        ).pack(side=tk.RIGHT, padx=2)

                    ttk.Button(
                        card,
                        text="🤝  Record Match Draw (+1 pt each)",
                        style="Draw.TButton",
                        command=lambda idx=i: self.handle_record_draw(idx)
                    ).pack(fill=tk.X, pady=(8, 0))
                else:
                    for player in pod:
                        row = tk.Frame(
                            card,
                            bg=Theme.BG_ROW_ALT,
                            highlightbackground="#e2e8f0",
                            highlightthickness=1,
                            padx=10,
                            pady=6
                        )
                        row.pack(fill=tk.X, pady=3)
                        rdv_tag = " [RDV]" if player.is_rdv else ""
                        status_tag = " [DROPPED]" if player.dropped else ""
                        lock_tag = f" 🔒[T{player.locked_table + 1}]" if player.locked_table is not None else ""

                        is_selected = (
                            self.event.global_swap_selection is not None
                            and self.event.global_swap_selection[1] == player
                        )
                        lbl_fg = Theme.BLUE if is_selected else Theme.TEXT_PRIMARY

                        tk.Label(
                            row,
                            text=f"{player.name}{rdv_tag}{status_tag}{lock_tag}   •   {player.points} pts",
                            font=("Segoe UI", 9, "bold"),
                            fg=lbl_fg,
                            bg=Theme.BG_ROW_ALT
                        ).pack(side=tk.LEFT)

                        ttk.Button(
                            row,
                            text="Won (+3)",
                            style="Win.TButton",
                            command=lambda idx=i, p=player: self.handle_record_win(idx, p)
                        ).pack(side=tk.RIGHT, padx=(4, 0))

                        swap_text = "✓ ↔" if is_selected else "↔"
                        swap_style = "SwapActive.TButton" if is_selected else "Small.TButton"
                        ttk.Button(
                            row,
                            text=swap_text,
                            style=swap_style,
                            width=4,
                            command=lambda idx=i, p=player: self.handle_swap_player(idx, p)
                        ).pack(side=tk.RIGHT, padx=2)

                        ttk.Button(
                            row,
                            text="M",
                            style="Move.TButton",
                            width=3,
                            command=lambda idx=i, p=player: self.handle_move_player_dialog(idx, p)
                        ).pack(side=tk.RIGHT, padx=2)

                    ttk.Button(
                        card,
                        text="🤝  Record Pod Draw (+1 pt to all)",
                        style="Draw.TButton",
                        command=lambda idx=i: self.handle_record_draw(idx)
                    ).pack(fill=tk.X, pady=(8, 0))

            else:
                if self.event.is_2hg_mode:
                    winner_team = outcome.get("winner_team")
                    pod_teams = self.event.get_pod_teams_2hg(pod)
                    teams_str_list = []
                    for tm in pod_teams:
                        t_lock = f" 🔒[T{tm.locked_table + 1}]" if tm.locked_table is not None else ""
                        teams_str_list.append(f"{tm.name}{t_lock} ({tm.points} pts)")
                    teams_str = "   vs   ".join(teams_str_list)

                    tk.Label(
                        card,
                        text=teams_str,
                        font=("Segoe UI", 9),
                        fg=Theme.TEXT_SECONDARY,
                        bg=Theme.BG_CARD,
                        wraplength=460,
                        justify=tk.LEFT
                    ).pack(anchor="w")

                    res_row = tk.Frame(card, bg=Theme.BG_CARD)
                    res_row.pack(fill=tk.X, pady=(10, 0))

                    if outcome["type"] == "DRAW":
                        res_text = "🤝  Match Draw (+1 pt each)"
                        res_color = Theme.BLUE
                    else:
                        res_text = f"🏆  {winner_team.name if winner_team else 'Unknown'} Won (+3 pts)"
                        res_color = Theme.EMERALD_TEXT

                    tk.Label(
                        res_row,
                        text=res_text,
                        fg=res_color,
                        bg=Theme.BG_CARD,
                        font=("Segoe UI", 10, "bold")
                    ).pack(side=tk.LEFT)
                    ttk.Button(
                        res_row,
                        text="↺ Undo",
                        style="Small.TButton",
                        command=lambda idx=i: self.handle_undo(idx)
                    ).pack(side=tk.RIGHT)
                else:
                    players_list = []
                    for p in pod:
                        lock_tag = f" 🔒[T{p.locked_table + 1}]" if p.locked_table is not None else ""
                        rdv_str = " [RDV]" if p.is_rdv else ""
                        players_list.append(f"{p.name}{rdv_str}{lock_tag} ({p.points} pts)")
                    players_str = "  •  ".join(players_list)

                    tk.Label(
                        card,
                        text=players_str,
                        font=("Segoe UI", 9),
                        fg=Theme.TEXT_SECONDARY,
                        bg=Theme.BG_CARD,
                        wraplength=460,
                        justify=tk.LEFT
                    ).pack(anchor="w")

                    res_row = tk.Frame(card, bg=Theme.BG_CARD)
                    res_row.pack(fill=tk.X, pady=(10, 0))

                    if outcome["type"] == "DRAW":
                        res_text = "🤝  Pod Draw (+1 pt each)"
                        res_color = Theme.BLUE
                    else:
                        res_text = f"🏆  {outcome['winner'].name} Won (+3 pts)"
                        res_color = Theme.EMERALD_TEXT

                    tk.Label(
                        res_row,
                        text=res_text,
                        fg=res_color,
                        bg=Theme.BG_CARD,
                        font=("Segoe UI", 10, "bold")
                    ).pack(side=tk.LEFT)
                    ttk.Button(
                        res_row,
                        text="↺ Undo",
                        style="Small.TButton",
                        command=lambda idx=i: self.handle_undo(idx)
                    ).pack(side=tk.RIGHT)

        self.pods_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._populate_pairings_window()
        self._populate_match_history_window()

    def refresh_standings(self, select_names: list[str] | tuple[str, ...] | str | None = None):
        if select_names is None:
            select_names = self.tree.selection()
        elif isinstance(select_names, str):
            select_names = (select_names,)

        yview_pos = self.tree.yview()

        for item in self.tree.get_children():
            self.tree.delete(item)

        sorted_players = self.event.get_sorted_standings()
        for idx, p in enumerate(sorted_players):
            paid_status = "✓ Paid" if p.paid else "⏳ Unpaid"
            opp_pts = self.event.get_opponent_points(p)
            record = f"{p.wins} - {p.losses} - {p.draws}"
            status = "Dropped" if p.dropped else "Active"

            rdv_str = "  [RDV]" if p.is_rdv else ""
            lock_str = f"  🔒 [Table {p.locked_table + 1}]" if p.locked_table is not None else ""
            display_name = f"{p.name}{rdv_str}{lock_str}"

            if self.event.is_2hg_mode:
                team_idx = self.event.get_player_team_index(p.name)
                team_str = f"Team {team_idx}" if team_idx is not None else "-"
                values = (paid_status, display_name, team_str, status, p.points, opp_pts, record)
            else:
                values = (paid_status, display_name, status, p.points, opp_pts, record)

            stripe_tag = "evenrow" if idx % 2 == 0 else "oddrow"
            if p.dropped:
                status_tag = "dropped"
            elif p.paid:
                status_tag = "paid"
            else:
                status_tag = "unpaid"

            self.tree.insert(
                "",
                tk.END,
                iid=p.name,
                values=values,
                tags=(stripe_tag, status_tag)
            )

        valid_selections = [name for name in select_names if self.tree.exists(name)]
        if valid_selections:
            self.tree.selection_set(valid_selections)
            self.tree.focus(valid_selections[-1])

        if yview_pos:
            self.tree.yview_moveto(yview_pos[0])


if __name__ == "__main__":
    root = tk.Tk()
    app = CommanderGUI(root)
    root.mainloop()