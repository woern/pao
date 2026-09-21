"""Day 1 rankings.

Mirrors the Google Sheets Results workbook: for every team, points for and
against per round, then wins, point differential, points for, points
against and the ratio of for to against. Teams rank by wins, then
differential, then ratio, then Buchholz (the sum of their opponents' wins,
a last-resort measure of who they had to beat). Teams equal on all four
are tied and need a coin flip, which the tournament director records as a
tiebreak.
"""

from . import model


def team_rounds(tournament, tid):
    """Per-round detail for one team: opponent, court, points for/against."""
    team = tournament["teams"][tid]
    rows = []
    for rnd in range(len(team["games"])):
        oid, court = model.team_game(tournament, tid, rnd)
        if oid is None:
            rows.append({"round": rnd, "oid": None, "opponent": "", "court": None,
                         "pf": None, "pa": None, "status": "absent", "won": False})
            continue
        pf = model.get_score(tournament, rnd, tid)
        pa = model.get_score(tournament, rnd, oid)
        rows.append({
            "round": rnd,
            "oid": oid,
            "opponent": model.team_name(tournament, oid),
            "court": court,
            "pf": pf,
            "pa": pa,
            "status": model.game_status(pf, pa),
            "won": pf is not None and pa is not None and pf > pa,
        })
    return rows


def ratio(pf, pa):
    """Points for over points against; just points for when nothing was conceded."""
    return pf / pa if pa else float(pf)


def team_totals(tournament, tid):
    rounds = team_rounds(tournament, tid)
    scored = [r for r in rounds if r["status"] in ("ok", "tied")]
    pf = sum(r["pf"] for r in scored)
    pa = sum(r["pa"] for r in scored)
    wins = sum(1 for r in scored if r["won"])
    return {
        "tid": tid,
        "name": tournament["teams"][tid]["name"],
        "group": tournament["teams"][tid]["group"],
        "rounds": rounds,
        "played": len(scored),
        "wins": wins,
        "pf": pf,
        "pa": pa,
        "diff": pf - pa,
        "ratio": ratio(pf, pa),
    }


def _tiebreak_pos(tournament, row):
    entry = tournament["tiebreaks"].get(row["tid"])
    if entry and list(entry.get("key", [])) == list(row["key"]):
        return entry["pos"]
    return 0


def buchholz(tournament, tid, wins_by_team):
    """Sum of the wins of every opponent this team has faced."""
    team = tournament["teams"][tid]
    return sum(wins_by_team.get(oid, 0) for oid in team["games"] if oid is not None)


def standings(tournament):
    """Ranked rows for every real team.

    Each row carries `rank` (equal rows share a rank), `tie` (an id shared
    by rows still tied after tiebreaks, else None) and `key`.
    """
    rows = [team_totals(tournament, tid) for tid, _ in model.real_teams(tournament)]
    # The BYE team is an opponent too; it never wins, so it counts as 0.
    wins_by_team = {row["tid"]: row["wins"] for row in rows}
    for row in rows:
        row["buchholz"] = buchholz(tournament, row["tid"], wins_by_team)
        row["key"] = (row["wins"], row["diff"], row["ratio"], row["buchholz"])
        row["tiebreak"] = _tiebreak_pos(tournament, row)
        # Tiebreak position 1 beats 2; teams with no tiebreak sort after none.
        row["sort_key"] = (-row["wins"], -row["diff"], -row["ratio"], -row["buchholz"],
                           row["tiebreak"] or float("inf"), row["tid"])

    rows.sort(key=lambda r: r["sort_key"])

    rank = 0
    previous = None
    tie_id = 0
    for index, row in enumerate(rows, start=1):
        full_key = row["sort_key"][:5]
        if full_key != previous:
            rank = index
            previous = full_key
        row["rank"] = rank

    # Mark rows that share a rank: those still need a coin flip.
    by_rank = {}
    for row in rows:
        by_rank.setdefault(row["rank"], []).append(row)
    for group in by_rank.values():
        if len(group) > 1:
            tie_id += 1
            for row in group:
                row["tie"] = tie_id
        else:
            group[0]["tie"] = None

    return rows


def unresolved_ties(tournament, rows=None):
    """Lists of tied rows, in rank order."""
    rows = rows if rows is not None else standings(tournament)
    ties = {}
    for row in rows:
        if row["tie"]:
            ties.setdefault(row["tie"], []).append(row)
    return [ties[k] for k in sorted(ties)]


def set_tiebreak(tournament, order):
    """Record a coin-flip result: `order` lists tied team numbers, best first.

    The teams must currently share wins, differential, ratio and Buchholz;
    otherwise the flip is meaningless and a ModelError is raised.
    """
    rows = {row["tid"]: row for row in standings(tournament)}
    missing = [str(tid) for tid in order if tid not in rows]
    if missing:
        raise model.ModelError("Team(s) not in the standings: " + ", ".join(missing))
    if len(order) < 2:
        raise model.ModelError("A tiebreak needs at least two teams.")

    keys = {rows[tid]["key"] for tid in order}
    if len(keys) != 1:
        raise model.ModelError("Those teams are not tied, so no coin flip is needed.")
    key = list(keys.pop())

    for pos, tid in enumerate(order, start=1):
        tournament["tiebreaks"][tid] = {"key": key, "pos": pos}


def clear_tiebreak(tournament, tid):
    tournament["tiebreaks"].pop(tid, None)
