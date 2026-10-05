"""Day 2: groups and single-elimination brackets.

The final Day 1 standings are cut into groups by rank (A is the best
teams). Each group plays a knockout bracket seeded the classic way, 1 v 32,
16 v 17 and so on, and the losers of the first round drop into a
consolation bracket (the "AA" sheets) that pairs the losers of adjacent
first-round games.

Stored state is small: the groups, and for each match its court and the
result as entered. Who plays whom in later rounds is derived from earlier
results every time, so correcting an early result automatically voids
anything downstream that depended on it.

    tournament["day2"] = {
        "groups": [{"name": "A", "teams": [174, 33, ...], "consolation": True}, ...],
        "matches": {"A-main-1-3": {"a": 174, "b": 77, "sa": 13, "sb": 0, "court": 9}, ...},
    }
"""

import math
import random

from . import model, standings

MAIN = "main"
CONS = "cons"
KINDS = (MAIN, CONS)

# Sizes that make a clean bracket; the form nudges the director toward them.
GOOD_SIZES = (8, 16, 32, 64)
DEFAULT_GROUP_SIZE = 32
GROUP_NAMES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


##################################
#######  bracket shape      ######
##################################

def bracket_size(count):
    """Smallest power of two that holds `count` teams (at least 2)."""
    size = 2
    while size < count:
        size *= 2
    return size


def seed_order(size):
    """Seeds in bracket order: [1, 32, 16, 17, 8, 25, ...] for 32.

    Adjacent pairs are first-round games; adjacent games feed one
    second-round game, so seed 1 cannot meet seed 2 before the final.
    """
    order = [1]
    while len(order) < size:
        order = [s for seed in order for s in (seed, 2 * len(order) + 1 - seed)]
    return order


def round_count(size):
    return int(math.log2(size))


def round_name(matches):
    """'1/16 Finals' ... '1/2 Finals', 'Final'."""
    if matches == 1:
        return "Final"
    return "1/%d Finals" % matches


def match_id(group, kind, rnd, index):
    return "%s-%s-%d-%d" % (group, kind, rnd, index)


##################################
#######  groups             ######
##################################

def day2(tournament):
    return tournament.setdefault("day2", {"groups": [], "matches": {}})


def has_groups(tournament):
    return bool(tournament.get("day2", {}).get("groups"))


def ranked_team_ids(tournament):
    return [row["tid"] for row in standings.standings(tournament)]


def day1_complete(tournament):
    """(complete, reason) - groups can only be made from final standings."""
    total = model.rounds_played(tournament)
    if total == 0:
        return False, "No rounds have been drawn."
    for rnd in range(total):
        summary = model.round_score_summary(tournament, rnd)
        if summary["ok"] != summary["games"]:
            return False, "Round %d has %d game(s) without a valid score." % (rnd + 1, summary["games"] - summary["ok"])
    ties = standings.unresolved_ties(tournament)
    if ties:
        return False, "%d tie(s) in the standings still need a coin flip." % len(ties)
    return True, ""


def suggest_sizes(count, size=DEFAULT_GROUP_SIZE):
    """[32, 32, ..., remainder] for `count` teams."""
    if count <= 0:
        return []
    sizes = [size] * (count // size)
    if count % size:
        sizes.append(count % size)
    return sizes


def plan_groups(tournament, sizes):
    """[(name, [tids])] the given sizes would produce; validates the sizes."""
    ranked = ranked_team_ids(tournament)
    if not sizes:
        raise model.ModelError("Choose at least one group.")
    if len(sizes) > len(GROUP_NAMES):
        raise model.ModelError("At most %d groups." % len(GROUP_NAMES))
    if any(s < 2 for s in sizes):
        raise model.ModelError("Every group needs at least 2 teams.")
    if sum(sizes) != len(ranked):
        raise model.ModelError("Group sizes add up to %d but there are %d teams." % (sum(sizes), len(ranked)))

    plan = []
    start = 0
    for name, size in zip(GROUP_NAMES, sizes):
        plan.append((name, ranked[start:start + size]))
        start += size
    return plan


def make_groups(tournament, sizes, consolation=None):
    """Cut the final standings into groups and start empty brackets."""
    complete, reason = day1_complete(tournament)
    if not complete:
        raise model.ModelError("Day 1 is not finished: " + reason)
    plan = plan_groups(tournament, sizes)
    consolation = consolation or {}
    tournament["day2"] = {
        "groups": [{"name": name, "teams": tids, "consolation": bool(consolation.get(name, True))}
                   for name, tids in plan],
        "matches": {},
    }
    assign_all_courts(tournament)
    return tournament["day2"]["groups"]


def clear_groups(tournament):
    tournament["day2"] = {"groups": [], "matches": {}}


def get_group(tournament, name):
    for group in day2(tournament)["groups"]:
        if group["name"] == name:
            return group
    raise model.ModelError("There is no group %s." % name)


def groups_out_of_date(tournament):
    """True when Day 1 standings no longer match the groups that were made."""
    if not has_groups(tournament):
        return False
    grouped = [tid for group in day2(tournament)["groups"] for tid in group["teams"]]
    return grouped != ranked_team_ids(tournament)


##################################
#######  the bracket        ######
##################################

def _slot(tid=None, bye=False, seed=None):
    return {"tid": tid, "bye": bye, "seed": seed}


TBD = _slot()
BYE = _slot(bye=True)


def _stored(tournament, mid, a, b):
    """The stored record for a match, only if it was entered for these teams."""
    record = day2(tournament)["matches"].get(mid)
    if record and record.get("a") == a and record.get("b") == b:
        return record
    return None


def _build_match(tournament, group, kind, rnd, index, slot_a, slot_b):
    mid = match_id(group["name"], kind, rnd, index)
    match = {"id": mid, "group": group["name"], "kind": kind, "round": rnd, "index": index,
             "a": slot_a, "b": slot_b, "sa": None, "sb": None, "court": None,
             "status": "pending", "winner": TBD, "loser": TBD}

    a, b = slot_a["tid"], slot_b["tid"]
    if slot_a["bye"] and slot_b["bye"]:
        match["status"] = "void"
        match["winner"] = match["loser"] = BYE
    elif slot_a["bye"] and b is not None:
        match["status"] = "walkover"
        match["winner"], match["loser"] = slot_b, BYE
    elif slot_b["bye"] and a is not None:
        match["status"] = "walkover"
        match["winner"], match["loser"] = slot_a, BYE
    elif a is not None and b is not None:
        record = _stored(tournament, mid, a, b)
        if record:
            match["court"] = record.get("court")
            match["sa"], match["sb"] = record.get("sa"), record.get("sb")
        if match["sa"] is not None and match["sb"] is not None:
            match["status"] = "done"
            if match["sa"] > match["sb"]:
                match["winner"], match["loser"] = slot_a, slot_b
            else:
                match["winner"], match["loser"] = slot_b, slot_a
        else:
            match["status"] = "ready"
    return match


def main_bracket(tournament, group):
    """Rounds of matches for a group's main bracket."""
    teams = group["teams"]
    size = bracket_size(len(teams))
    order = seed_order(size)
    slots = [_slot(teams[s - 1], seed=s) if s <= len(teams) else BYE for s in order]

    rounds = []
    rnd = 0
    while len(slots) > 1:
        matches = [_build_match(tournament, group, MAIN, rnd, i, slots[2 * i], slots[2 * i + 1])
                   for i in range(len(slots) // 2)]
        rounds.append(matches)
        slots = [m["winner"] for m in matches]
        rnd += 1
    return rounds


def consolation_bracket(tournament, group, main_rounds=None):
    """Rounds for the losers of the main bracket's first round; [] if none."""
    if not group.get("consolation"):
        return []
    main_rounds = main_rounds if main_rounds is not None else main_bracket(tournament, group)
    slots = [m["loser"] for m in main_rounds[0]]
    if len(slots) < 2:
        return []

    rounds = []
    rnd = 0
    while len(slots) > 1:
        matches = [_build_match(tournament, group, CONS, rnd, i, slots[2 * i], slots[2 * i + 1])
                   for i in range(len(slots) // 2)]
        rounds.append(matches)
        slots = [m["winner"] for m in matches]
        rnd += 1
    return rounds


def brackets(tournament, group):
    main = main_bracket(tournament, group)
    return {MAIN: main, CONS: consolation_bracket(tournament, group, main)}


def all_matches(tournament):
    """Every match of every group, derived fresh."""
    for group in day2(tournament)["groups"]:
        for kind, rounds in brackets(tournament, group).items():
            for matches in rounds:
                for match in matches:
                    yield match


def find_match(tournament, mid):
    for match in all_matches(tournament):
        if match["id"] == mid:
            return match
    raise model.ModelError("Unknown match %s." % mid)


def group_summary(tournament, group):
    b = brackets(tournament, group)
    summary = {"name": group["name"], "teams": len(group["teams"]), "consolation": bool(b[CONS])}
    for kind in KINDS:
        playable = [m for r in b[kind] for m in r if m["status"] in ("ready", "done")]
        summary[kind + "_done"] = sum(1 for m in playable if m["status"] == "done")
        summary[kind + "_total"] = len(playable)
        final = b[kind][-1][0] if b[kind] else None
        summary[kind + "_champion"] = final["winner"]["tid"] if final and final["status"] in ("done", "walkover") else None
    return summary


##################################
#######  results            ######
##################################

def record_result(tournament, mid, sa, sb):
    """Store a match result. Scores may be None to clear it."""
    match = find_match(tournament, mid)
    if match["status"] not in ("ready", "done"):
        raise model.ModelError("Match %s is not ready to be scored." % mid)
    sa, sb = model.parse_score(sa), model.parse_score(sb)
    if (sa is None) != (sb is None):
        raise model.ModelError("Enter both scores, or neither.")
    if sa is not None and sa == sb:
        raise model.ModelError("A knockout game cannot be tied.")

    matches = day2(tournament)["matches"]
    record = matches.setdefault(mid, {})
    record.update({"a": match["a"]["tid"], "b": match["b"]["tid"], "sa": sa, "sb": sb})
    record.setdefault("court", match["court"])
    prune_stale(tournament)
    assign_all_courts(tournament)
    return find_match(tournament, mid)


def record_walkover(tournament, mid, winner):
    match = find_match(tournament, mid)
    win, lose = model.WALKOVER_SCORE
    if winner == match["a"]["tid"]:
        return record_result(tournament, mid, win, lose)
    if winner == match["b"]["tid"]:
        return record_result(tournament, mid, lose, win)
    raise model.ModelError("Team %s is not in match %s." % (winner, mid))


def prune_stale(tournament):
    """Drop stored records whose teams no longer meet in that match."""
    live = {m["id"]: (m["a"]["tid"], m["b"]["tid"]) for m in all_matches(tournament)
            if m["a"]["tid"] is not None and m["b"]["tid"] is not None}
    matches = day2(tournament)["matches"]
    for mid in list(matches):
        record = matches[mid]
        if live.get(mid) != (record.get("a"), record.get("b")):
            del matches[mid]


##################################
#######  courts             ######
##################################

def team_court_history(tournament, tid):
    """Every court a team has played, Day 1 and Day 2."""
    courts = {c for c in tournament["teams"][tid]["courts"] if c is not None}
    for match in all_matches(tournament):
        if match["court"] is not None and tid in (match["a"]["tid"], match["b"]["tid"]):
            courts.add(match["court"])
    return courts


def busy_courts(tournament):
    """Courts held by matches that have teams and a court but no result."""
    return {m["court"] for m in all_matches(tournament) if m["status"] == "ready" and m["court"] is not None}


def _set_court(tournament, match, court):
    record = day2(tournament)["matches"].setdefault(match["id"], {})
    record.update({"a": match["a"]["tid"], "b": match["b"]["tid"], "court": court})
    record.setdefault("sa", None)
    record.setdefault("sb", None)


def assign_courts(tournament, matches, reassign=False):
    """Give each ready match without a court a random free one.

    Prefers courts neither team has played on; falls back to any free
    court; leaves the match without a court if none is free. With
    `reassign`, the given matches give up their courts first.
    """
    courts, _ = model.court_map(tournament)
    ready = [m for m in matches if m["status"] == "ready"]
    if reassign:
        for match in ready:
            if match["court"] is not None:
                _set_court(tournament, match, None)
                match["court"] = None

    busy = busy_courts(tournament)
    for match in ready:
        if match["court"] is not None:
            continue
        free = [c for c in courts if c not in busy]
        if not free:
            continue
        a, b = match["a"]["tid"], match["b"]["tid"]
        played = team_court_history(tournament, a) | team_court_history(tournament, b)
        fresh = [c for c in free if c not in played]
        court = random.choice(fresh or free)
        _set_court(tournament, match, court)
        match["court"] = court
        busy.add(court)


def assign_all_courts(tournament):
    """Fill in courts for every ready match, earliest rounds first."""
    for group in day2(tournament)["groups"]:
        b = brackets(tournament, group)
        for kind in KINDS:
            for matches in b[kind]:
                assign_courts(tournament, matches)


def shuffle_round(tournament, group_name, kind, rnd):
    """Redraw the courts of one bracket round's unplayed matches."""
    group = get_group(tournament, group_name)
    rounds = brackets(tournament, group).get(kind, [])
    if not 0 <= rnd < len(rounds):
        raise model.ModelError("No such round.")
    assign_courts(tournament, rounds[rnd], reassign=True)
