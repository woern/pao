"""The tournament data model.

A tournament is a plain dictionary so that files written by older versions
of the program keep loading. Every function here takes that dictionary as
its first argument and edits it in place.

    {
        "name": "amelia2025",
        "created_at": datetime, "modified_at": datetime,
        "court_map": {"a": (1, 90), "b": (0, 0)},
        "teams": {
            12: {"name": "Smith/Jones", "group": "FL",
                 "games": [40, 7, ...],      # opponent per round; None = sat out
                 "courts": [3, 61, ...],     # court per round; None = sat out
                 "played_b": 0,             # times on the annex
                 "bye": False},
            ...
        },
        "scores": {round_index: {team_number: points_scored}},
        "tiebreaks": {team_number: {"key": [wins, diff, ratio], "pos": n}},
    }
"""

import datetime
from collections import namedtuple

# A court section set to this range means "this section is not in use".
UNUSED_SECTION = (0, 0)

# Section "a" is the main field; section "b" is the annex/overflow field.
# Teams that have played the annex get first claim on section "a" next round.
DEFAULT_COURT_MAP = {"a": (1, 10), "b": UNUSED_SECTION}

# Group assigned to the filler team added when the team count is odd. No real
# team should use this group, or those teams can never draw the bye.
BYE_GROUP = "EU"
BYE_PREFIX = "BYE-"

# A petanque game is played to 13. A bye, and a no-show, is scored 13-7.
MAX_SCORE = 13
WALKOVER_SCORE = (13, 7)

# One game in a round: the court and the two team numbers.
Game = namedtuple("Game", "court tid oid")


class ModelError(ValueError):
    """Raised for invalid edits; the message is meant for the user."""


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


##################################
#######  tournament         ######
##################################

def new_tournament(name=""):
    now = utcnow()
    return {
        "name": name,
        "teams": {},
        "created_at": now,
        "modified_at": now,
        "court_map": dict(DEFAULT_COURT_MAP),
        "scores": {},
        "tiebreaks": {},
    }


def migrate(tournament):
    """Fill in fields missing from tournament files saved by older versions."""
    tournament.setdefault("name", "")
    tournament.setdefault("teams", {})
    tournament.setdefault("created_at", utcnow())
    tournament.setdefault("modified_at", utcnow())
    tournament.setdefault("scores", {})
    tournament.setdefault("tiebreaks", {})
    if not tournament.get("court_map"):
        tournament["court_map"] = dict(DEFAULT_COURT_MAP)

    for team in tournament["teams"].values():
        team.setdefault("name", "Anonymous")
        team.setdefault("group", "-")
        team.setdefault("games", [])
        team.setdefault("courts", [])
        team.setdefault("played_b", 0)
        team.setdefault("bye", team["group"] == BYE_GROUP and team["name"].startswith(BYE_PREFIX))
    return tournament


##################################
#######  teams              ######
##################################

def is_bye(team):
    return bool(team.get("bye"))


def add_team(tournament, num, group, name, bye=False):
    """Insert or update a team, keeping any schedule it already has.

    Returns (created, previous) where previous is the old (group, name)
    when an existing team was updated, else None.
    """
    teams = tournament["teams"]
    existing = teams.get(num)

    if existing and is_bye(existing) and not bye:
        raise ModelError("Number %d is the BYE filler; give the team another number." % num)

    if existing:
        previous = (existing["group"], existing["name"])
        existing["group"] = group
        existing["name"] = name
        return False, previous

    teams[num] = dict(name=name, group=group, games=[], courts=[], played_b=0, bye=bye)
    return True, None


def remove_team(tournament, num):
    """Delete a team. Returns how many scheduled games still reference it."""
    teams = tournament["teams"]
    if num not in teams:
        raise ModelError("Team %d not found." % num)

    orphaned = sum(other["games"].count(num) for other in teams.values())
    del teams[num]
    for per_round in tournament["scores"].values():
        per_round.pop(num, None)
    tournament["tiebreaks"].pop(num, None)
    return orphaned


def team_name(tournament, tid):
    team = tournament["teams"].get(tid)
    return team["name"] if team else "(removed team)"


def next_team_number(tournament):
    return max(tournament["teams"], default=0) + 1


def add_bye_team(tournament):
    """Add a filler team so the team count is even. Returns its number."""
    num = next_team_number(tournament)
    add_team(tournament, num, BYE_GROUP, "%s%d" % (BYE_PREFIX, num), bye=True)
    return num


def real_teams(tournament):
    """(tid, team) for every team that is not the BYE filler, sorted."""
    return [(tid, team) for tid, team in sorted(tournament["teams"].items()) if not is_bye(team)]


##################################
#######  courts             ######
##################################

def section_bounds(tournament, section):
    bounds = tournament["court_map"].get(section)
    if not bounds or tuple(bounds) == UNUSED_SECTION:
        return None
    return tuple(bounds)


def in_section(tournament, section, num):
    bounds = section_bounds(tournament, section)
    return bool(bounds) and bounds[0] <= num <= bounds[1]


def is_court_a(tournament, num):
    return in_section(tournament, "a", num)


def is_court_b(tournament, num):
    return in_section(tournament, "b", num)


def court_map(tournament):
    """Return (all courts, section-a courts) as sorted lists."""
    courts = set()
    courts_a = set()
    for section in tournament["court_map"]:
        bounds = section_bounds(tournament, section)
        if not bounds:
            continue
        nums = range(bounds[0], bounds[1] + 1)
        courts.update(nums)
        if section == "a":
            courts_a.update(nums)
    return sorted(courts), sorted(courts_a)


def set_section(tournament, section, low, high):
    """Define a court section. `0 0` marks it unused."""
    if section not in ("a", "b"):
        raise ModelError("Section must be a or b.")
    if (low, high) != UNUSED_SECTION and low < 1:
        raise ModelError("Court numbers start at 1. Use 0 0 to mark section %s unused." % section)
    if low > high:
        raise ModelError("`from` must not be greater than `to`.")
    tournament["court_map"][section] = (low, high)


##################################
#######  rounds and games   ######
##################################

def rounds_played(tournament):
    teams = tournament["teams"].values()
    return max((len(t["games"]) for t in teams), default=0)


def teams_in_round(tournament, rnd):
    """Yield (tid, team) for every team with a game scheduled in `rnd`."""
    for tid, team in sorted(tournament["teams"].items()):
        if len(team["games"]) > rnd and team["games"][rnd] is not None:
            yield tid, team


def teams_absent_from_round(tournament, rnd):
    """(tid, team) for teams that exist but have no game in `rnd`."""
    playing = {tid for tid, _ in teams_in_round(tournament, rnd)}
    return [(tid, team) for tid, team in sorted(tournament["teams"].items()) if tid not in playing]


def team_game(tournament, tid, rnd):
    """(opponent, court) for a team in a round; (None, None) if it sat out."""
    team = tournament["teams"][tid]
    oid = team["games"][rnd] if len(team["games"]) > rnd else None
    court = team["courts"][rnd] if len(team["courts"]) > rnd else None
    return oid, court


def repeated_courts(tournament, rnd):
    """[(tid, court)] for teams whose court in `rnd` is one they played before."""
    repeats = []
    for tid, team in teams_in_round(tournament, rnd):
        court = team["courts"][rnd] if len(team["courts"]) > rnd else None
        if court is not None and court in team["courts"][:rnd]:
            repeats.append((tid, court))
    return repeats


def pad_absent_teams(tournament):
    """Give every team an entry for every round, so round N is always index N.

    A team that sat a round out (the BYE when the count is even, or a team
    that arrived late) gets None for that round.
    """
    total = rounds_played(tournament)
    for team in tournament["teams"].values():
        while len(team["games"]) < total:
            team["games"].append(None)
        while len(team["courts"]) < len(team["games"]):
            team["courts"].append(None)


def games_in_round(tournament, rnd):
    """One Game per pairing in a round, sorted by court.

    A game recorded for only one team (a hand fix, or a removed opponent)
    still appears once, from that team's side.
    """
    games = []
    seen = set()
    for tid, team in teams_in_round(tournament, rnd):
        if tid in seen:
            continue
        oid, court = team_game(tournament, tid, rnd)
        seen.update((tid, oid))
        games.append(Game(court, tid, oid))

    games.sort(key=lambda g: (g.court is None, g.court if g.court is not None else 0, g.tid))
    return games


def _bump_annex(tournament, tid, court, delta):
    if court is not None and is_court_b(tournament, court):
        team = tournament["teams"][tid]
        team["played_b"] = max(0, team["played_b"] + delta)


def add_game(tournament, tid, oid, court, both=True):
    """Append a game to a team's schedule (and the opponent's unless both=False)."""
    teams = tournament["teams"]
    missing = [str(n) for n in (tid, oid) if n not in teams]
    if missing:
        raise ModelError("Team(s) not found: " + ", ".join(missing))

    teams[tid]["games"].append(oid)
    teams[tid]["courts"].append(court)
    _bump_annex(tournament, tid, court, +1)

    if both:
        teams[oid]["games"].append(tid)
        teams[oid]["courts"].append(court)
        _bump_annex(tournament, oid, court, +1)


def set_game(tournament, rnd, tid, oid, court):
    """Replace (or add) the game both teams play in round `rnd`.

    Any score either team had for the round is cleared, because the
    pairing it belonged to no longer exists.
    """
    teams = tournament["teams"]
    missing = [str(n) for n in (tid, oid) if n not in teams]
    if missing:
        raise ModelError("Team(s) not found: " + ", ".join(missing))
    if tid == oid:
        raise ModelError("A team cannot play itself.")
    if court < 1:
        raise ModelError("Court numbers start at 1.")

    for me, other in ((tid, oid), (oid, tid)):
        team = teams[me]
        if len(team["games"]) < rnd:
            raise ModelError("Team %d has no game in round %d yet, so it cannot be fixed in round %d."
                             % (me, len(team["games"]) + 1, rnd + 1))

        if len(team["games"]) == rnd:
            team["games"].append(other)
            team["courts"].append(court)
        else:
            old_court = team["courts"][rnd] if len(team["courts"]) > rnd else None
            _bump_annex(tournament, me, old_court, -1)
            team["games"][rnd] = other
            while len(team["courts"]) <= rnd:
                team["courts"].append(None)
            team["courts"][rnd] = court
        _bump_annex(tournament, me, court, +1)

        tournament["scores"].get(rnd, {}).pop(me, None)


def remove_round(tournament, rnd):
    """Delete round `rnd` (0-based) from every team. -1 removes the last.

    Returns how many teams were affected.
    """
    removed = 0
    total = rounds_played(tournament)
    if rnd == -1:
        rnd = total - 1
    if rnd < 0:
        return 0

    for tid, team in tournament["teams"].items():
        games = team["games"]
        courts = team["courts"]
        if len(games) <= rnd:
            continue

        court = courts[rnd] if rnd < len(courts) else None
        del games[rnd]
        if rnd < len(courts):
            del courts[rnd]
        _bump_annex(tournament, tid, court, -1)
        removed += 1

    # Scores for later rounds shift down with the rounds they belong to.
    scores = tournament["scores"]
    scores.pop(rnd, None)
    for later in sorted(k for k in scores if k > rnd):
        scores[later - 1] = scores.pop(later)
    return removed


def clear_rounds(tournament):
    """Delete every round, keeping the teams. Returns how many rounds went."""
    total = rounds_played(tournament)
    for team in tournament["teams"].values():
        team["games"] = []
        team["courts"] = []
        team["played_b"] = 0
    tournament["scores"] = {}
    tournament["tiebreaks"] = {}
    return total


##################################
#######  scores             ######
##################################

def parse_score(value):
    """Turn a form/CLI value into a score or None. Raises ModelError if bad."""
    if value is None:
        return None
    if isinstance(value, int):
        score = value
    else:
        text = str(value).strip()
        if text == "":
            return None
        if not text.isdigit():
            raise ModelError("Scores must be whole numbers, not %r." % text)
        score = int(text)
    if not 0 <= score <= MAX_SCORE:
        raise ModelError("Scores must be between 0 and %d." % MAX_SCORE)
    return score


def get_score(tournament, rnd, tid):
    return tournament["scores"].get(rnd, {}).get(tid)


def set_score(tournament, rnd, tid, points):
    per_round = tournament["scores"].setdefault(rnd, {})
    if points is None:
        per_round.pop(tid, None)
        if not per_round:
            tournament["scores"].pop(rnd, None)
    else:
        per_round[tid] = points


def set_game_score(tournament, rnd, tid, oid, points_tid, points_oid):
    """Record both sides of one game. Values may be None to clear a side."""
    if rnd >= rounds_played(tournament):
        raise ModelError("Round %d has not been drawn." % (rnd + 1))
    for num in (tid, oid):
        if num not in tournament["teams"]:
            raise ModelError("Team %d not found." % num)
    set_score(tournament, rnd, tid, parse_score(points_tid))
    set_score(tournament, rnd, oid, parse_score(points_oid))


def game_scores(tournament, rnd, game):
    return get_score(tournament, rnd, game.tid), get_score(tournament, rnd, game.oid)


def game_status(points_a, points_b):
    """'missing', 'partial', 'tied' or 'ok'."""
    if points_a is None and points_b is None:
        return "missing"
    if points_a is None or points_b is None:
        return "partial"
    if points_a == points_b:
        return "tied"
    return "ok"


def record_walkover(tournament, rnd, winner, loser):
    """Score a game 13-7 to the winner: byes and no-shows."""
    win, lose = WALKOVER_SCORE
    set_game_score(tournament, rnd, winner, loser, win, lose)


def record_bye_scores(tournament, rnd):
    """Give every team drawn against the BYE filler its 13-7 win."""
    teams = tournament["teams"]
    for game in games_in_round(tournament, rnd):
        a, b = teams.get(game.tid), teams.get(game.oid)
        if a and b and is_bye(b) and not is_bye(a):
            record_walkover(tournament, rnd, game.tid, game.oid)
        elif a and b and is_bye(a) and not is_bye(b):
            record_walkover(tournament, rnd, game.oid, game.tid)


def round_score_summary(tournament, rnd):
    """Counts of games by status for a round."""
    summary = {"games": 0, "missing": 0, "partial": 0, "tied": 0, "ok": 0}
    for game in games_in_round(tournament, rnd):
        summary["games"] += 1
        summary[game_status(*game_scores(tournament, rnd, game))] += 1
    return summary
