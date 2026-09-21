"""Every page of the web app: routes plus the HTML that renders them."""

import urllib.parse
from html import escape as esc

from paolib import model, scheduler, standings, store, teamsio
from .server import html, json_response, redirect

ROUTES = []


def route(method, pattern):
    def register(fn):
        ROUTES.append((method, pattern, fn))
        return fn
    return register


def register(app):
    for method, pattern, fn in ROUTES:
        app.route(method, pattern)(fn)


##################################
#######  layout helpers     ######
##################################

NAV = [
    ("/", "Home"),
    ("/setup", "Courts"),
    ("/teams", "Teams"),
    ("/rounds", "Rounds"),
    ("/standings", "Standings"),
]


def layout(app, req, title, body, active=None):
    links = "".join(
        '<a href="%s"%s>%s</a>' % (href, ' class="active"' if href == active else "", label)
        for href, label in NAV
    )
    flash = ""
    if req.get("msg"):
        flash += '<div class="flash ok">%s</div>' % esc(req.get("msg"))
    if req.get("err"):
        flash += '<div class="flash err">%s</div>' % esc(req.get("err"))

    name = app.name or "PAO"
    switch = '<a class="switch" href="/open">Switch tournament</a>' if app.name else ""
    return html("""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s - %s</title>
<link rel="stylesheet" href="/static/app.css">
</head><body>
<nav class="no-print"><span class="brand">%s</span>%s%s</nav>
<main>%s<h1>%s</h1>%s</main>
<script src="/static/app.js"></script>
</body></html>""" % (esc(title), esc(name), esc(name), links if app.name else "", switch, flash, esc(title), body))


def print_layout(app, title, body, subtitle=""):
    return html("""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>%s</title>
<link rel="stylesheet" href="/static/app.css"></head>
<body class="print">
<div class="no-print toolbar"><a href="javascript:history.back()">&larr; Back</a>
<button onclick="window.print()">Print / Save as PDF</button> <span class="muted">%s</span></div>
%s
</body></html>""" % (esc(title), esc(subtitle), body))


def table(headers, rows, cls="", row_attrs=None):
    head = "".join("<th>%s</th>" % h for h in headers)
    body = []
    for index, row in enumerate(rows):
        attrs = row_attrs(index) if row_attrs else ""
        body.append("<tr%s>%s</tr>" % (attrs, "".join("<td>%s</td>" % c for c in row)))
    return '<table class="%s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (cls, head, "".join(body))


def button_form(action, label, cls="", hidden=None, confirm=None):
    fields = "".join('<input type="hidden" name="%s" value="%s">' % (esc(k), esc(str(v))) for k, v in (hidden or {}).items())
    onsubmit = ' onsubmit="return confirm(%s)"' % esc(repr(confirm)) if confirm else ""
    # `label` is trusted HTML written in this file, not user input.
    return '<form method="post" action="%s" class="inline"%s>%s<button class="%s">%s</button></form>' % (
        esc(action), onsubmit, fields, cls, label)


def courts_text(t):
    parts = []
    for section, label in (("a", "Main field"), ("b", "Annex")):
        bounds = model.section_bounds(t, section)
        parts.append("%s: %s" % (label, "%d-%d" % bounds if bounds else "not used"))
    return ", ".join(parts)


def round_index(req_round, t):
    """1-based round from the URL to a 0-based index, or raise."""
    rnd = req_round - 1
    if not 0 <= rnd < model.rounds_played(t):
        raise model.ModelError("Round %d has not been drawn." % req_round)
    return rnd


def name_of(t, tid):
    return esc(model.team_name(t, tid))


def round_switcher(t, current, suffix=""):
    """Links to the same page for every drawn round. Scores stay editable
    for every round, whatever has been drawn since."""
    links = ['<a href="/rounds">All rounds</a>']
    for rnd in range(model.rounds_played(t)):
        n = rnd + 1
        label = "Round %d" % n
        if rnd == current:
            links.append("<strong>%s</strong>" % label)
        else:
            links.append('<a href="/rounds/%d%s">%s</a>' % (n, suffix, label))
    return '<p class="switcher no-print">%s</p>' % " &middot; ".join(links)


##################################
#######  choose a tournament ####
##################################

@route("GET", "/open")
def open_page(app, req):
    rows = []
    for name, teams, rounds, modified in store.list_tournaments():
        when = modified.astimezone().strftime("%Y-%m-%d %H:%M") if modified else ""
        current = " <span class='tag ok'>open</span>" if name == app.name else ""
        rows.append([
            "<b>%s</b>%s" % (esc(name), current), teams, rounds, when,
            button_form("/open", "Open", "small", {"name": name}),
        ])
    body = """
<form method="post" action="/open" class="row">
  <label>New tournament <input name="name" placeholder="amelia2026" required autofocus></label>
  <button class="primary">Create and open</button>
  <span class="muted">Each tournament is one file, &lt;name&gt;.p, in the app's folder.</span>
</form>
<h2>Existing tournaments</h2>
%s
""" % (table(["Tournament", "Teams", "Rounds", "Last change", ""], rows)
       if rows else "<p class='muted'>None yet in this folder.</p>")
    return layout(app, req, "Choose a tournament", body, None)


@route("POST", "/open")
def open_tournament(app, req):
    try:
        name = store.clean_name(req.get("name"))
        created = app.open(name)
    except store.StoreError as exc:
        return redirect("/open", err=str(exc))
    return redirect("/", msg=("Created %s" if created else "Opened %s") % name)


##################################
#######  home               ######
##################################

@route("GET", "/")
def home(app, req):
    t = app.tournament
    real = model.real_teams(t)
    byes = [tid for tid, team in t["teams"].items() if model.is_bye(team)]
    courts, courts_a = model.court_map(t)
    total_rounds = model.rounds_played(t)

    rounds_rows = []
    for rnd in range(total_rounds):
        s = model.round_score_summary(t, rnd)
        state = "complete" if s["ok"] == s["games"] else "%d of %d games scored" % (s["ok"], s["games"])
        if s["tied"]:
            state += ", %d tied" % s["tied"]
        rounds_rows.append([
            rnd + 1, s["games"], state,
            '<a href="/rounds/%d">matchups</a> &middot; <a href="/rounds/%d/scores">scores</a>' % (rnd + 1, rnd + 1),
        ])

    steps = []
    if not real:
        steps.append('<a href="/teams">Import the team list</a>')
    if len(courts) < max(1, len(t["teams"]) // 2):
        steps.append('<a href="/setup">Set the courts</a> (%d games need %d courts, %d defined)'
                     % (len(t["teams"]) // 2, len(t["teams"]) // 2, len(courts)))
    if real and not total_rounds:
        steps.append('<a href="/rounds">Draw round 1</a>')
    next_steps = "<h2>Next</h2><ol>%s</ol>" % "".join("<li>%s</li>" % s for s in steps) if steps else ""

    body = """
<div class="cards">
  <div class="card"><div class="big">%d</div>teams%s <a href="/teams">manage</a></div>
  <div class="card"><div class="big">%d</div>courts<br><span class="muted">%s</span> <a href="/setup">change</a></div>
  <div class="card"><div class="big">%d</div>rounds drawn <a href="/rounds">manage</a></div>
</div>
%s
<h2>Rounds</h2>
%s
<p class="muted">Tournament file: <code>%s</code>. Copy that file to back up the whole tournament.</p>
%s
""" % (
        len(real), " (+1 BYE)" if byes else "",
        len(courts), esc(courts_text(t)),
        total_rounds,
        next_steps,
        table(["Round", "Games", "Scores", ""], rounds_rows) if rounds_rows else "<p class='muted'>No rounds drawn yet.</p>",
        esc(app.path),
        ("<p class='muted'>Other devices on the same network can open <code>%s</code>.</p>" % esc(app.lan_url))
        if getattr(app, "lan_url", "") else "",
    )
    return layout(app, req, "Tournament", body, "/")


##################################
#######  courts             ######
##################################

@route("GET", "/setup")
def setup(app, req):
    t = app.tournament
    a = model.section_bounds(t, "a") or (0, 0)
    b = model.section_bounds(t, "b") or (0, 0)
    courts, courts_a = model.court_map(t)
    games = len(t["teams"]) // 2
    body = """
<form method="post" action="/setup" class="stack">
  <fieldset><legend>Main field (section a)</legend>
    courts <input type="number" name="a_from" value="%d" min="0"> to <input type="number" name="a_to" value="%d" min="0">
  </fieldset>
  <fieldset><legend>Annex (section b)</legend>
    courts <input type="number" name="b_from" value="%d" min="0"> to <input type="number" name="b_to" value="%d" min="0">
    <div class="muted">Enter 0 and 0 if there is no annex. Keep the annex to at most half the size of the main field.</div>
  </fieldset>
  <button class="primary">Save courts</button>
</form>
<p>%d courts defined (%d main, %d annex). %d teams need %d courts per round.</p>
""" % (a[0], a[1], b[0], b[1], len(courts), len(courts_a), len(courts) - len(courts_a), len(t["teams"]), games)
    return layout(app, req, "Courts", body, "/setup")


@route("POST", "/setup")
def setup_save(app, req):
    t = app.tournament
    for section in ("a", "b"):
        low = req.get(section + "_from", "0").strip() or "0"
        high = req.get(section + "_to", "0").strip() or "0"
        if not (low.isdigit() and high.isdigit()):
            raise model.ModelError("Court numbers must be whole numbers.")
        model.set_section(t, section, int(low), int(high))
    app.save()
    return redirect("/setup", msg="Courts saved: " + courts_text(t))


##################################
#######  teams              ######
##################################

@route("GET", "/teams")
def teams(app, req):
    t = app.tournament
    rows = []
    for tid, team in sorted(t["teams"].items()):
        rows.append([
            tid, esc(team["group"]), esc(team["name"]) + (" <span class='tag'>BYE</span>" if model.is_bye(team) else ""),
            len(team["games"]), team["played_b"],
            button_form("/teams/%d/remove" % tid, "remove", "small danger",
                        confirm="Remove team %d %s?" % (tid, team["name"])),
        ])
    drawn = model.rounds_played(t)
    warning = ("<div class='flash warn'>Rounds are already drawn. Editing a name or group is safe; "
               "removing a team leaves its opponents with a missing game to fix by hand.</div>" if drawn else "")

    body = """
%s
<details %s><summary>Import team list</summary>
<form method="post" action="/teams/import" class="stack">
  <p>Paste from the ForCSV sheet (or any CSV/tab-separated text) with columns <b>number, group, name</b>.
  Extra columns are ignored. A header row and empty rows are skipped automatically.
  Or pick the file: <input type="file" id="teamfile" accept=".csv,.txt,.tsv"></p>
  <textarea name="text" id="teamtext" rows="8" placeholder="1,FL,Smith/Jones&#10;2,GA,Lee/Chen"></textarea>
  <div><button class="primary">Import</button> <span class="muted">Re-importing updates names and groups and keeps schedules.</span></div>
</form>
</details>
<details><summary>Add or edit one team</summary>
<form method="post" action="/teams" class="row">
  <label>Number <input type="number" name="number" value="%d" min="1" required></label>
  <label>Group <input name="group" placeholder="FL" size="6" required></label>
  <label>Name <input name="name" placeholder="Smith/Jones" required></label>
  <button>Save team</button>
</form>
</details>
<h2>%d teams%s</h2>
%s
""" % (
        warning,
        "open" if not t["teams"] else "",
        model.next_team_number(t),
        len(model.real_teams(t)),
        " <span class='muted'>plus a BYE filler, used only when the count is odd</span>" if len(model.real_teams(t)) != len(t["teams"]) else "",
        table(["#", "Group", "Name", "Games", "Annex", ""], rows) if rows else "<p class='muted'>No teams yet.</p>",
    )
    return layout(app, req, "Teams", body, "/teams")


@route("POST", "/teams/import")
def teams_import(app, req):
    text = req.get("text", "")
    if not text.strip():
        raise model.ModelError("Nothing to import: paste the team list first.")
    rows, skipped = teamsio.parse_teams(text)
    added, updated, rejected = teamsio.import_teams(app.tournament, rows)
    app.save()
    msg = "Imported %d teams (%d new, %d updated)." % (added + updated, added, updated)
    problems = [teamsio.format_skipped(skipped)] if skipped else []
    problems += ["Team %d not imported: %s" % (number, reason) for number, reason in rejected]
    return redirect("/teams", msg=msg, err=" ".join(problems) or None)


@route("POST", "/teams")
def team_save(app, req):
    number = req.get("number").strip()
    name = req.get("name").strip()
    group = req.get("group").strip()
    if not number.isdigit() or int(number) < 1:
        raise model.ModelError("Team number must be a whole number.")
    if teamsio.is_blank(name) or teamsio.is_blank(group):
        raise model.ModelError("Both a group and a name are required.")
    created, previous = model.add_team(app.tournament, int(number), group, name)
    app.save()
    return redirect("/teams", msg=("Added" if created else "Updated") + " team %s %s" % (number, name))


@route("POST", r"/teams/(\d+)/remove")
def team_remove(app, req):
    tid = req.args[0]
    name = model.team_name(app.tournament, tid)
    orphaned = model.remove_team(app.tournament, tid)
    app.save()
    err = ("%d scheduled game(s) still reference this team; fix them on the round pages." % orphaned) if orphaned else None
    return redirect("/teams", msg="Removed team %d %s" % (tid, name), err=err)


##################################
#######  rounds             ######
##################################

@route("GET", "/rounds")
def rounds(app, req):
    t = app.tournament
    total = model.rounds_played(t)
    courts, _ = model.court_map(t)
    rows = []
    for rnd in range(total):
        s = model.round_score_summary(t, rnd)
        status = []
        if s["ok"] == s["games"]:
            status.append("<span class='tag ok'>all scored</span>")
        else:
            status.append("%d / %d scored" % (s["ok"], s["games"]))
        if s["tied"]:
            status.append("<span class='tag bad'>%d tied</span>" % s["tied"])
        if s["partial"]:
            status.append("<span class='tag warn'>%d half-entered</span>" % s["partial"])
        n = rnd + 1
        rows.append([
            n, s["games"], " ".join(status),
            '<a href="/rounds/%d">matchups</a> &middot; <a href="/rounds/%d/scores">enter scores</a>' % (n, n),
            '<a href="/print/rounds/%d/cards" target="_blank">court cards</a> &middot; '
            '<a href="/print/rounds/%d/list" target="_blank">list with names</a> &middot; '
            '<a href="/print/rounds/%d/slips" target="_blank">score slips</a>' % (n, n, n),
            button_form("/rounds/%d/delete" % n, "delete", "small danger",
                        confirm="Delete round %d? Later rounds shift down and its scores are lost." % n),
        ])

    real = len(model.real_teams(t))
    body = """
<form method="post" action="/rounds/draw" class="row">
  <button class="primary" %s>Draw round %d</button>
  <span class="muted">%d teams%s, %d games, %d courts. If the courts are too tight for a clean draw,
  the round is drawn anyway and you are told which teams repeat a court.</span>
</form>
%s
%s
""" % (
        "disabled" if real < 2 else "",
        total + 1, real, " + BYE" if real % 2 else "", (real + 1) // 2, len(courts),
        table(["Round", "Games", "Scores", "Manage", "Print", ""], rows) if rows else "<p class='muted'>No rounds drawn yet.</p>",
        button_form("/rounds/clear", "Delete all rounds, keep teams", "danger",
                    confirm="Delete every round and every score?") if total else "",
    )
    return layout(app, req, "Rounds", body, "/rounds")


@route("POST", "/rounds/draw")
def rounds_draw(app, req):
    t = app.tournament
    messages = []
    log = lambda m: messages.append(m) if m.startswith("[INFO]") else None  # noqa: E731
    forced = False
    try:
        try:
            rnd = scheduler.draw_round(t, log=log)
        except scheduler.DrawFailed:
            # Too little court headroom for a clean draw. Draw it anyway,
            # ignoring court history, and say who is affected.
            forced = True
            rnd = scheduler.draw_round(t, force=True, log=log)
    except scheduler.DrawError as exc:
        app.save()  # a BYE team may have been added
        return redirect("/rounds", err=str(exc))
    app.save()

    msg = "Drew round %d." % (rnd + 1)
    if messages:
        msg += " " + " ".join(m.replace("[INFO] ", "") for m in messages)
    err = None
    if forced:
        repeats = model.repeated_courts(t, rnd)
        who = ", ".join("%d (court %d)" % (tid, court) for tid, court in repeats)
        err = ("Not enough spare courts for a clean draw, so court history was ignored for this round. "
               "%d team(s) play a court they have used before: %s. Adding courts avoids this."
               % (len(repeats), who or "none, as it turned out"))
    return redirect("/rounds/%d" % (rnd + 1), msg=msg, err=err)


@route("POST", r"/rounds/(\d+)/delete")
def round_delete(app, req):
    rnd = round_index(req.args[0], app.tournament)
    model.remove_round(app.tournament, rnd)
    app.save()
    return redirect("/rounds", msg="Deleted round %d." % (rnd + 1))


@route("POST", "/rounds/clear")
def rounds_clear(app, req):
    total = model.clear_rounds(app.tournament)
    app.save()
    return redirect("/rounds", msg="Cleared %d round(s)." % total)


@route("GET", r"/rounds/(\d+)")
def round_view(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    n = rnd + 1
    games = model.games_in_round(t, rnd)
    rows = []
    for g in games:
        a, b = model.game_scores(t, rnd, g)
        status = model.game_status(a, b)
        score = "" if status == "missing" else "%s - %s" % ("" if a is None else a, "" if b is None else b)
        rows.append([
            g.court if g.court is not None else "?",
            g.tid, name_of(t, g.tid), "vs", g.oid, name_of(t, g.oid),
            score, "<span class='tag %s'>%s</span>" % (status, status) if status != "ok" else "",
        ])

    courts, _ = model.court_map(t)
    used = {g.court for g in games}
    unused = sorted(set(courts) - used)
    orphans = [g for g in games if g.oid not in t["teams"] or g.tid not in t["teams"]]
    absent = ", ".join("%d %s" % (tid, esc(team["name"])) for tid, team in model.teams_absent_from_round(t, rnd))

    body = round_switcher(t, rnd) + """
<p class="row">
  <a class="button" href="/rounds/%d/scores">Enter scores</a>
  <a class="button" href="/print/rounds/%d/cards" target="_blank">Print court cards</a>
  <a class="button" href="/print/rounds/%d/list" target="_blank">Print list with names</a>
  <a class="button" href="/print/rounds/%d/slips" target="_blank">Print score slips</a>
</p>
%s
%s
<p class="muted">Unused courts: %s</p>
%s
<details><summary>Fix one game by hand</summary>
<form method="post" action="/rounds/%d/game" class="row">
  <label>Team <input type="number" name="tid" min="1" required></label>
  <label>Opponent <input type="number" name="oid" min="1" required></label>
  <label>Court <input type="number" name="court" min="1" required></label>
  <button>Replace game</button>
  <span class="muted">Replaces both teams' game in this round and clears their scores for it.</span>
</form>
</details>
""" % (
        n, n, n, n,
        "<div class='flash warn'>%d game(s) reference a removed team. Use the fix form below.</div>" % len(orphans) if orphans else "",
        table(["Court", "#", "Team", "", "#", "Opponent", "Score", ""], rows),
        ", ".join(str(c) for c in unused) or "none",
        "<p class='muted'>Not playing this round: %s</p>" % absent if absent else "",
        n,
    )
    return layout(app, req, "Round %d" % n, body, "/rounds")


@route("POST", r"/rounds/(\d+)/game")
def round_fix_game(app, req):
    rnd = round_index(req.args[0], app.tournament)
    values = [req.get(k).strip() for k in ("tid", "oid", "court")]
    if not all(v.isdigit() for v in values):
        raise model.ModelError("Team, opponent and court must be whole numbers.")
    tid, oid, court = (int(v) for v in values)
    model.set_game(app.tournament, rnd, tid, oid, court)
    app.save()
    return redirect("/rounds/%d" % (rnd + 1), msg="Round %d: %d vs %d on court %d." % (rnd + 1, tid, oid, court))


##################################
#######  scores             ######
##################################

def score_input(rnd, tid, value, tabindex):
    return ('<input class="score" type="text" inputmode="numeric" pattern="([0-9]|1[0-3])" maxlength="2" '
            'title="0 to %d" name="s_%d" value="%s" data-round="%d" data-tid="%d" tabindex="%d">'
            % (model.MAX_SCORE, tid, "" if value is None else value, rnd + 1, tid, tabindex))


@route("GET", r"/rounds/(\d+)/scores")
def scores(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    n = rnd + 1
    rows = []
    attrs = []
    tab = 1
    for g in model.games_in_round(t, rnd):
        a, b = model.game_scores(t, rnd, g)
        status = model.game_status(a, b)
        bye = model.is_bye(t["teams"].get(g.tid, {})) or model.is_bye(t["teams"].get(g.oid, {}))
        walk = "" if bye else (
            button_form("/rounds/%d/walkover" % n, "13-7 &larr;", "small", {"winner": g.tid, "loser": g.oid})
            + " " + button_form("/rounds/%d/walkover" % n, "&rarr; 13-7", "small", {"winner": g.oid, "loser": g.tid}))
        rows.append([
            g.court if g.court is not None else "?",
            "<b>%d</b> %s" % (g.tid, name_of(t, g.tid)),
            score_input(rnd, g.tid, a, tab), score_input(rnd, g.oid, b, tab + 1),
            "<b>%d</b> %s" % (g.oid, name_of(t, g.oid)),
            "<span class='status'>%s</span>" % status,
            walk,
        ])
        attrs.append(' class="game %s" data-tid="%d" data-oid="%d"' % (status, g.tid, g.oid))
        tab += 2

    s = model.round_score_summary(t, rnd)
    body = round_switcher(t, rnd, "/scores") + """
<p class="row">
  <span id="summary" class="muted">%d of %d games scored, %d tied</span>
  <a class="button" href="/print/rounds/%d/slips" target="_blank">Print score slips</a>
</p>
<form method="post" action="/rounds/%d/scores" id="scores">
%s
<p><button class="primary">Save all</button> <span class="muted">Scores also save on their own as you type, and can be changed at any time, for any round. No-show: use the 13-7 button pointing at the team that showed up.</span></p>
</form>
""" % (s["ok"], s["games"], s["tied"], n, n,
       table(["Court", "Team", "Score", "Score", "Opponent", "Status", "No-show"], rows, "scores",
             row_attrs=lambda i: attrs[i]))
    return layout(app, req, "Round %d scores" % n, body, "/rounds")


def apply_scores(t, rnd, getter):
    """Store every game's two scores from a callable name -> value."""
    for g in model.games_in_round(t, rnd):
        model.set_game_score(t, rnd, g.tid, g.oid, getter("s_%d" % g.tid), getter("s_%d" % g.oid))


@route("POST", r"/rounds/(\d+)/scores")
def scores_save(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    apply_scores(t, rnd, lambda name: req.get(name, None))
    app.save()
    s = model.round_score_summary(t, rnd)
    return redirect("/rounds/%d/scores" % (rnd + 1), msg="Saved. %d of %d games scored." % (s["ok"], s["games"]))


@route("POST", r"/rounds/(\d+)/walkover")
def scores_walkover(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    winner, loser = req.get("winner"), req.get("loser")
    if not (winner.isdigit() and loser.isdigit()):
        raise model.ModelError("Bad team numbers.")
    model.record_walkover(t, rnd, int(winner), int(loser))
    app.save()
    return redirect("/rounds/%d/scores" % (rnd + 1), msg="Recorded 13-7 for team %s." % winner)


@route("POST", "/api/score")
def api_score(app, req):
    """Autosave one game: {"round": n, "tid": .., "oid": .., "a": .., "b": ..}."""
    t = app.tournament
    data = req.json or {}
    rnd = round_index(int(data.get("round", 0)), t)
    tid, oid = int(data["tid"]), int(data["oid"])
    model.set_game_score(t, rnd, tid, oid, data.get("a"), data.get("b"))
    app.save()
    a, b = model.get_score(t, rnd, tid), model.get_score(t, rnd, oid)
    summary = model.round_score_summary(t, rnd)
    return json_response({"status": model.game_status(a, b), "summary": summary})


##################################
#######  standings          ######
##################################

def fmt_ratio(value):
    return "%.3f" % value


@route("GET", "/standings")
def standings_page(app, req):
    t = app.tournament
    rows = standings.standings(t)
    total = model.rounds_played(t)
    unscored = sum(1 for rnd in range(total) for g in model.games_in_round(t, rnd)
                   if model.game_status(*model.game_scores(t, rnd, g)) != "ok")

    headers = ["Rank", "#", "Team"]
    for rnd in range(total):
        headers += ["R%d F" % (rnd + 1), "A", "Opp"]
    headers += ["W", "Diff", "Pts F", "Pts A", "Ratio", "Opp W"]

    table_rows = []
    attrs = []
    for row in rows:
        cells = [row["rank"], row["tid"], esc(row["name"])]
        for rnd in range(total):
            if rnd < len(row["rounds"]) and row["rounds"][rnd]["oid"] is not None:
                r = row["rounds"][rnd]
                cells += ["" if r["pf"] is None else r["pf"], "" if r["pa"] is None else r["pa"], r["oid"]]
            else:
                cells += ["", "", ""]
        cells += [row["wins"], row["diff"], row["pf"], row["pa"], fmt_ratio(row["ratio"]), row["buchholz"]]
        table_rows.append(cells)
        attrs.append(' class="tied"' if row["tie"] and not unscored else "")

    # Coin flips only make sense once every game has a score.
    ties = standings.unresolved_ties(t, rows) if total and not unscored else []
    tie_forms = []
    for group in ties:
        inputs = "".join(
            '<label>%d %s <input type="number" name="pos_%d" min="1" max="%d" required size="2"></label>'
            % (r["tid"], esc(r["name"]), r["tid"], len(group)) for r in group)
        tie_forms.append(
            '<form method="post" action="/standings/tiebreak" class="row tie">'
            '<span>Rank %d, %d teams tied on %d wins, %+d diff, %s ratio, %d opponents\' wins. '
            'Coin flip order (1 = best):</span> %s '
            '<input type="hidden" name="tids" value="%s"><button>Record</button></form>'
            % (group[0]["rank"], len(group), group[0]["wins"], group[0]["diff"], fmt_ratio(group[0]["ratio"]),
               group[0]["buchholz"], inputs, ",".join(str(r["tid"]) for r in group)))

    resolved = [(tid, e) for tid, e in t["tiebreaks"].items() if tid in t["teams"]]
    resolved_html = ""
    if resolved:
        resolved_html = "<details><summary>%d recorded coin flips</summary><ul>%s</ul></details>" % (
            len(resolved), "".join(
                "<li>%d %s: position %d %s</li>" % (
                    tid, name_of(t, tid), e["pos"],
                    button_form("/standings/tiebreak/clear", "undo", "small", {"tid": tid}))
                for tid, e in sorted(resolved)))

    body = """
<p class="row"><a class="button" href="/print/standings" target="_blank">Print rankings</a>
<span class="muted">Ranked by wins, then point differential, then points for / points against, then opponents' wins (Buchholz). The BYE team is not listed.</span></p>
%s
%s
%s
%s
""" % (
        "<div class='flash warn'>%d game(s) are not fully scored yet. Ties are checked once every game is in.</div>" % unscored if unscored else "",
        ("<div class='flash err'>%d tie(s) need a coin flip.</div>%s" % (len(ties), "".join(tie_forms))) if ties else "",
        resolved_html,
        table(headers, table_rows, "standings", row_attrs=lambda i: attrs[i]) if rows else "<p class='muted'>No teams.</p>",
    )
    return layout(app, req, "Standings", body, "/standings")


@route("POST", "/standings/tiebreak")
def tiebreak(app, req):
    tids = [int(x) for x in req.get("tids").split(",") if x.strip().isdigit()]
    positions = {}
    for tid in tids:
        value = req.get("pos_%d" % tid).strip()
        if not value.isdigit():
            raise model.ModelError("Give every tied team a position.")
        positions[tid] = int(value)
    if sorted(positions.values()) != list(range(1, len(tids) + 1)):
        raise model.ModelError("Positions must be 1 to %d, each used once." % len(tids))
    order = sorted(tids, key=lambda tid: positions[tid])
    standings.set_tiebreak(app.tournament, order)
    app.save()
    return redirect("/standings", msg="Coin flip recorded: " + ", ".join(str(x) for x in order))


@route("POST", "/standings/tiebreak/clear")
def tiebreak_clear(app, req):
    tid = req.get("tid")
    if tid.isdigit():
        standings.clear_tiebreak(app.tournament, int(tid))
        app.save()
    return redirect("/standings", msg="Coin flip for team %s removed." % tid)


##################################
#######  print views        ######
##################################

PER_PAGE_CARDS = 20
PER_PAGE_SLIPS = 5


@route("GET", r"/print/rounds/(\d+)/cards")
def print_cards(app, req):
    """One card per team, 20 per page, so players find their own number."""
    t = app.tournament
    rnd = round_index(req.args[0], t)
    entries = []
    for tid, team in model.teams_in_round(t, rnd):
        oid, court = model.team_game(t, tid, rnd)
        entries.append((tid, court if court is not None else "?", oid))

    pages = []
    for start in range(0, len(entries), PER_PAGE_CARDS):
        chunk = entries[start:start + PER_PAGE_CARDS]
        half = (len(chunk) + 1) // 2
        cols = [chunk[:half], chunk[half:]]
        col_html = ""
        for col in cols:
            col_html += '<div class="col"><div class="cardhead"><span>Team #</span><span>COURT</span><span>Team #</span></div>' + "".join(
                '<div class="gamecard"><span class="team">%s</span><span class="court">%s</span><span class="team">%s</span></div>'
                % (tid, court, oid) for tid, court, oid in col) + "</div>"
        pages.append('<section class="page cards"><h1>GAME %d <span class="range">%d-%d</span></h1><div class="cols">%s</div></section>'
                     % (rnd + 1, chunk[0][0], chunk[-1][0], col_html))
    return print_layout(app, "Round %d court cards" % (rnd + 1), "".join(pages),
                        "%d teams, %d pages" % (len(entries), len(pages)))


@route("GET", r"/print/rounds/(\d+)/list")
def print_list(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    rows = []
    for tid, team in model.teams_in_round(t, rnd):
        oid, court = model.team_game(t, tid, rnd)
        rows.append([tid, esc(team["name"]), "vs", oid, name_of(t, oid), court if court is not None else "?"])
    body = '<section class="page"><h1>%s - Round %d</h1>%s</section>' % (
        esc(app.name), rnd + 1, table(["#", "Team", "", "#", "Opponent", "Court"], rows, "list"))
    return print_layout(app, "Round %d list" % (rnd + 1), body)


@route("GET", r"/print/rounds/(\d+)/slips")
def print_slips(app, req):
    t = app.tournament
    rnd = round_index(req.args[0], t)
    games = [g for g in model.games_in_round(t, rnd)
             if not (model.is_bye(t["teams"].get(g.tid, {})) or model.is_bye(t["teams"].get(g.oid, {})))]
    pages = []
    for start in range(0, len(games), PER_PAGE_SLIPS):
        slips = "".join("""
<div class="slip">
  <div class="round"><div class="circle">%d</div><div class="lbl">ROUND</div></div>
  <div class="courtbox"><div class="box">%s</div><div class="lbl">COURT #</div></div>
  <div class="side"><div class="lbl">Team #</div><div class="lbl">Score</div><div class="teamno">%d</div><div class="box score"></div><div class="sig">Signature</div></div>
  <div class="side"><div class="lbl">Score</div><div class="lbl">Team #</div><div class="box score"></div><div class="teamno">%d</div><div class="sig">Signature</div></div>
</div>""" % (rnd + 1, g.court if g.court is not None else "", g.tid, g.oid) for g in games[start:start + PER_PAGE_SLIPS])
        pages.append('<section class="page slips">%s</section>' % slips)
    return print_layout(app, "Round %d score slips" % (rnd + 1), "".join(pages),
                        "%d slips, %d pages" % (len(games), len(pages)))


@route("GET", "/print/standings")
def print_standings(app, req):
    t = app.tournament
    rows = standings.standings(t)
    body = '<section class="page"><h1>%s - Qualifying Rankings</h1>%s</section>' % (
        esc(app.name),
        table(["Rank", "Team", "Team #", "W", "Diff", "Ratio", "Opp W"],
              [[r["rank"], esc(r["name"]), r["tid"], r["wins"], r["diff"], fmt_ratio(r["ratio"]), r["buchholz"]]
               for r in rows],
              "list"))
    return print_layout(app, "Rankings", body)
