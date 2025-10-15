from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz, process


POINT_A_SYNONYMS = [
	"point to team a",
	"point team a",
	"point a",
	"score team a",
	"team a point",
	"team alpha",
	"team one",
	"team 1",
	"left team",
]
POINT_B_SYNONYMS = [
	"point to team b",
	"point team b",
	"point b",
	"score team b",
	"team b point",
	"team bravo",
	"team bee",
	"team be",
	"team two",
	"team 2",
	"right team",
]
UNDO_SYNONYMS = ["undo last point", "undo", "reverse point", "take back point"]
WHATS_SCORE_SYNONYMS = ["what's the score", "what is the score", "score now", "current score"]
NEXT_SET_SYNONYMS = ["next set", "start next set", "new set"]
RESET_MATCH_SYNONYMS = ["reset match", "restart match", "clear match"]


def best_match_score(text: str, phrases: list[str]) -> int:
	text = text.lower()
	best = 0
	for p in phrases:
		best = max(best, fuzz.partial_ratio(text, p))
	return best


@dataclass
class Command:
	type: str
	team: Optional[str] = None  # 'A' or 'B'


def parse_command(transcript: str, team_a_name: Optional[str] = None, team_b_name: Optional[str] = None) -> Optional[Command]:
	t = (transcript or "").lower().strip()
	if not t:
		return None
	# PRIORITIZE UNDO with stricter rules to avoid false positives (e.g. "rvce" ~= "reverse")
	if 'undo' in t:
		return Command(type="undo")
	# Only accept fuzzy UNDO if very confident and not clearly a point command
	if best_match_score(t, UNDO_SYNONYMS) >= 85 and 'point' not in t:
		return Command(type="undo")
	# Handle score query BEFORE point matching so "what's the score" never increments
	if 'what' in t and 'score' in t:
		return Command(type="whats_score")
	if best_match_score(t, WHATS_SCORE_SYNONYMS) >= 70:
		return Command(type="whats_score")
	# Fast path: extract "point to team <name>" or "point <name>"
	m = re.search(r"point\s+(?:to\s+)?(?:team\s+)?([a-z0-9][a-z0-9\s'-]{1,40})$", t)
	if m and (team_a_name or team_b_name):
		target = m.group(1).strip()
		cand_a = team_a_name.lower() if team_a_name else ""
		cand_b = team_b_name.lower() if team_b_name else ""
		s_a = fuzz.partial_ratio(target, cand_a) if cand_a else 0
		s_b = fuzz.partial_ratio(target, cand_b) if cand_b else 0
		if max(s_a, s_b) >= 60:
			return Command(type="point", team="A" if s_a >= s_b else "B")
    # Dynamic phrases using provided team names
	dyn_a: list[str] = []
	dyn_b: list[str] = []
	if team_a_name:
		name = team_a_name.lower()
		dyn_a.extend([
			f"point to {name}",
			f"point {name}",
			f"score {name}",
			f"{name} point",
			f"point to team {name}",
			f"team {name} point",
			f"point {name} team",
		])
	if team_b_name:
		name = team_b_name.lower()
		dyn_b.extend([
			f"point to {name}",
			f"point {name}",
			f"score {name}",
			f"{name} point",
			f"point to team {name}",
			f"team {name} point",
			f"point {name} team",
		])
	# Score both teams; pick the higher if above threshold
	syn_a = best_match_score(t, POINT_A_SYNONYMS)
	syn_b = best_match_score(t, POINT_B_SYNONYMS)
	name_a = best_match_score(t, dyn_a)
	name_b = best_match_score(t, dyn_b)
	# Prefer explicit team-name matches if reasonably strong
	if max(name_a, name_b) >= 65:
		return Command(type="point", team="A" if name_a >= name_b else "B")
	# Fall back to generic synonyms
	s_a = max(syn_a, name_a)
	s_b = max(syn_b, name_b)
	if max(s_a, s_b) >= 60:
		return Command(type="point", team="A" if s_a >= s_b else "B")
	if best_match_score(t, NEXT_SET_SYNONYMS) >= 70:
		return Command(type="next_set")
	if best_match_score(t, RESET_MATCH_SYNONYMS) >= 70:
		return Command(type="reset_match")
	return None


