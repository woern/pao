"""The round draw.

For each round:

1. Only real teams play. If there is an odd number of them, one BYE filler
   team plays too (added the first time it is needed, reused after that);
   with an even number the BYE sits the round out.
2. Teams that have played the annex are drawn first, against teams that
   have not, onto section-a courts, so nobody plays the annex twice running.
3. Everyone else is drawn in random order.
4. Opponents are picked from teams not yet scheduled this round, never met
   before, and not in the same group.
5. Courts are picked from free courts neither team has played on, section a
   first.
6. If any team cannot be paired or seated the round is discarded and retried.
"""

import random

from . import model

# How many times to retry building a round before giving up and suggesting -f.
# Each attempt is a few milliseconds even for 180 teams, and a small field
# with little court headroom often needs a dozen tries in the later rounds.
MAX_ROUND_ATTEMPTS = 50


class DrawError(Exception):
    """The round could not be drawn; the message says why."""


class DrawFailed(DrawError):
    """Every attempt produced a dead end; forcing may get past it."""


def build_groups(tournament):
    groups = {}
    for tid, team in tournament["teams"].items():
        groups.setdefault(team["group"], set()).add(tid)
    return groups


def pick_opponent(tournament, tid, groups, scheduled, exclude=frozenset(), pool=None):
    """Choose an opponent this team has not met and is not grouped with."""
    teams = tournament["teams"]
    team = teams[tid]

    pool = set(teams) if pool is None else set(pool)
    candidates = pool - scheduled - set(team["games"]) - groups[team["group"]] - exclude - {tid}
    if not candidates:
        return None

    # sorted() keeps the candidate order stable so the shuffle is the only
    # source of randomness; random.choice needs a sequence, not a set.
    oid = random.choice(sorted(candidates))
    scheduled.update((tid, oid))
    return oid


def pick_court(tournament, tid, oid, pool, force=False):
    """Choose a court from `pool` that neither team has played on."""
    if not pool:
        return None

    options = list(pool)
    if not force:
        teams = tournament["teams"]
        played = set(teams[tid]["courts"]) | set(teams[oid]["courts"])
        options = [c for c in options if c not in played]

    return random.choice(options) if options else None


def create_round(tournament, force=False, log=None):
    """Return a list of (team, opponent, court) tuples, or [] on a bad draw.

    Raises DrawError when no draw could ever succeed (too few teams or
    courts). `log` receives progress messages when given.
    """
    log = log or (lambda msg: None)
    teams = tournament["teams"]

    participants = {tid for tid, team in model.real_teams(tournament)}
    if len(participants) < 2:
        raise DrawError("Need at least 2 teams to schedule a round.")

    if len(participants) % 2 == 1:
        byes = sorted(tid for tid, team in teams.items() if model.is_bye(team))
        if byes:
            bye = byes[0]
        else:
            bye = model.add_bye_team(tournament)
            log("[INFO] Odd number of teams, added %s%d." % (model.BYE_PREFIX, bye))
        participants.add(bye)

    courts, courts_a = model.court_map(tournament)
    needed = len(participants) // 2
    if len(courts) < needed:
        raise DrawError("%d games need %d courts, but only %d are defined. Use `cset`."
                        % (needed, needed, len(courts)))

    groups = build_groups(tournament)
    played_annex = set()
    rest = set()
    for tid in participants:
        (played_annex if teams[tid]["played_b"] > 0 else rest).add(tid)

    if force:
        rest |= played_annex
        played_annex = set()

    games = []
    scheduled = set()

    # Teams that already played the annex get first claim on section a.
    for tid in sorted(played_annex):
        if tid in scheduled:
            continue

        oid = pick_opponent(tournament, tid, groups, scheduled, exclude=played_annex, pool=participants)
        log("[DEBUG] annex %s vs %s" % (tid, oid))
        if oid is None:
            return []

        court = pick_court(tournament, tid, oid, courts_a, force=force)
        if court is None:
            return []

        courts.remove(court)
        courts_a.remove(court)
        games.append((tid, oid, court))

    # Everyone else, in random order.
    remaining = sorted(rest)
    random.shuffle(remaining)

    for tid in remaining:
        if tid in scheduled:
            continue

        oid = pick_opponent(tournament, tid, groups, scheduled, pool=participants)
        log("[DEBUG] main  %s vs %s" % (tid, oid))
        if oid is None:
            return []

        court = pick_court(tournament, tid, oid, courts_a or courts, force=force)
        if court is None:
            return []

        courts.remove(court)
        if court in courts_a:
            courts_a.remove(court)
        games.append((tid, oid, court))

    return games


def update_teams(tournament, games):
    """Append a drawn round to every team's schedule."""
    for tid, oid, court in games:
        model.add_game(tournament, tid, oid, court)


def draw_round(tournament, force=False, log=None, attempts=MAX_ROUND_ATTEMPTS):
    """Draw and record the next round. Returns its 0-based index.

    Raises DrawError if the draw fails every attempt.
    """
    log = log or (lambda msg: None)
    games = []
    for attempt in range(1, attempts + 1):
        games = create_round(tournament, force=force, log=log)
        if games:
            break
        log("[DEBUG] attempt %d produced no round" % attempt)

    if not games:
        raise DrawFailed("Could not create a round after %d attempts." % attempts)

    # Pad first so a late arrival's new game lands at this round's index,
    # then again so whoever sat this round out gets its placeholder.
    model.pad_absent_teams(tournament)
    update_teams(tournament, games)
    model.pad_absent_teams(tournament)
    rnd = model.rounds_played(tournament) - 1
    model.record_bye_scores(tournament, rnd)
    return rnd
