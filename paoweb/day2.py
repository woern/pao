"""Day 2 pages: groups, brackets, score entry, courts and print views."""

from html import escape as esc

from paolib import brackets, model, standings
from .pages import button_form, layout, print_layout, route, table


def team_label(t, tid):
    team = t["teams"].get(tid)
    return "<b>%d</b> %s" % (tid, esc(team["name"])) if team else "(removed team)"


##################################
#######  groups             ######
##################################

@route("GET", "/day2")
def day2_page(app, req):
    t = app.tournament
    if brackets.has_groups(t):
        return overview(app, req)
    return setup(app, req)


def parse_sizes(req):
    sizes = []
    for value in req.getlist("size"):
        value = value.strip()
        if value == "":
            continue
        if not value.isdigit():
            raise model.ModelError("Group sizes must be whole numbers.")
        sizes.append(int(value))
    return sizes


def setup(app, req):
    t = app.tournament
    complete, reason = brackets.day1_complete(t)
    ranked = brackets.ranked_team_ids(t)
    count = len(ranked)

    sizes = parse_sizes(req) if req.getlist("size") else brackets.suggest_sizes(count)
    wanted = req.get("groups", "").strip()
    if wanted.isdigit() and int(wanted) >= 1:
        n = int(wanted)
        sizes = (sizes + [brackets.DEFAULT_GROUP_SIZE] * n)[:n]
        # The last group takes whatever is left.
        head = sizes[:-1]
        sizes = head + [max(0, count - sum(head))]

    rows = []
    preview = ""
    try:
        plan = brackets.plan_groups(t, sizes) if sizes else []
        ranks = {tid: i + 1 for i, tid in enumerate(ranked)}
        for name, tids in plan:
            rows.append([name, len(tids), "%d - %d" % (ranks[tids[0]], ranks[tids[-1]]),
                         "" if len(tids) in brackets.GOOD_SIZES else "<span class='tag warn'>not 8/16/32/64: top seeds get byes</span>"])
        preview = table(["Group", "Teams", "Ranks", ""], rows)
    except model.ModelError as exc:
        preview = "<div class='flash err'>%s</div>" % esc(str(exc))

    size_inputs = "".join(
        '<label>Group %s <input type="number" name="size" value="%d" min="2"></label> '
        '<label class="muted"><input type="checkbox" name="cons_%s" checked> consolation</label><br>'
        % (brackets.GROUP_NAMES[i], size, brackets.GROUP_NAMES[i]) for i, size in enumerate(sizes))

    body = """
%s
<form method="get" action="/day2" class="row">
  <label>Number of groups <input type="number" name="groups" value="%d" min="1" max="26"></label>
  <button>Update</button>
  <span class="muted">%d teams ranked. Groups are cut from the top of the standings: A is the best %s teams.</span>
</form>
<form method="post" action="/day2/groups" class="stack">
  <fieldset><legend>Group sizes</legend>%s
  <div class="muted">Sizes of 8, 16, 32 or 64 make a clean bracket. Untick consolation for a group whose first-round losers do not play on.</div>
  </fieldset>
  <button formaction="/day2" formmethod="get">Preview</button>
  <button class="primary" %s>Create groups and brackets</button>
</form>
<h2>Preview</h2>
%s
""" % (
        "" if complete else "<div class='flash warn'>Day 1 is not finished: %s Groups can be previewed but not created yet.</div>" % esc(reason),
        len(sizes), count, sizes[0] if sizes else 0,
        size_inputs,
        "" if complete else "disabled",
        preview,
    )
    return layout(app, req, "Day 2: make the groups", body, "/day2")


@route("POST", "/day2/groups")
def groups_create(app, req):
    t = app.tournament
    sizes = parse_sizes(req)
    consolation = {brackets.GROUP_NAMES[i]: bool(req.get("cons_%s" % brackets.GROUP_NAMES[i])) for i in range(len(sizes))}
    groups = brackets.make_groups(t, sizes, consolation)
    app.save()
    return redirect_day2("Created %d groups: %s." % (len(groups), ", ".join(g["name"] for g in groups)))


def redirect_day2(msg=None, err=None):
    from .server import redirect
    return redirect("/day2", msg=msg, err=err)


@route("POST", "/day2/groups/delete")
def groups_delete(app, req):
    brackets.clear_groups(app.tournament)
    app.save()
    return redirect_day2("Groups and brackets deleted. Day 1 results are untouched.")


def overview(app, req):
    t = app.tournament
    rows = []
    for group in brackets.day2(t)["groups"]:
        s = brackets.group_summary(t, group)
        champion = team_label(t, s["main_champion"]) if s["main_champion"] else ""
        cons = "%d / %d" % (s["cons_done"], s["cons_total"]) if s["consolation"] else "none"
        rows.append([
            '<a href="/day2/%s"><b>Group %s</b></a>' % (s["name"], s["name"]), s["teams"],
            "%d / %d" % (s["main_done"], s["main_total"]), cons, champion,
            '<a href="/print/day2/%s" target="_blank">print brackets</a>' % s["name"],
        ])
    body = """
%s
<p class="row">
  <a class="button" href="/print/day2/groups" target="_blank">Print team lists by group</a>
  <a class="button" href="/print/standings" target="_blank">Print rankings</a>
</p>
%s
<p>%s</p>
""" % (
        "<div class='flash warn'>Day 1 scores changed after these groups were made, so the standings no longer match them. "
        "Delete the groups and create them again if that was intended.</div>" if brackets.groups_out_of_date(t) else "",
        table(["Group", "Teams", "Main bracket", "Consolation", "Champion", ""], rows),
        button_form("/day2/groups/delete", "Delete groups and all Day 2 results", "danger",
                    confirm="Delete every group, bracket and Day 2 score?"),
    )
    return layout(app, req, "Day 2", body, "/day2")


##################################
#######  brackets           ######
##################################

def side_html(t, slot, name, value, winner, editable):
    if slot["bye"]:
        return '<div class="side bye"><span class="seed"></span><span class="name muted">bye</span></div>'
    if slot["tid"] is None:
        return '<div class="side tbd"><span class="seed"></span><span class="name muted">&mdash;</span></div>'
    team = t["teams"].get(slot["tid"])
    label = esc(team["name"]) if team else "(removed team)"
    seed = slot["seed"] if slot["seed"] is not None else ""
    score = ('<input class="bscore" type="text" inputmode="numeric" pattern="([0-9]|1[0-3])" maxlength="2" name="%s" value="%s">'
             % (name, "" if value is None else value)) if editable \
        else '<span class="bscore">%s</span>' % ("" if value is None else value)
    return '<div class="side%s"><span class="seed">%s</span><span class="num">%d</span><span class="name">%s</span>%s</div>' % (
        " winner" if winner else "", seed, slot["tid"], label, score)


def match_html(t, match, editable):
    status = match["status"]
    court = "" if match["court"] is None else match["court"]
    court_html = '<div class="court">%s</div>' % court if status in ("ready", "done") else ""
    win = match["winner"]["tid"]
    a = side_html(t, match["a"], "sa", match["sa"], status == "done" and win == match["a"]["tid"], editable and status in ("ready", "done"))
    b = side_html(t, match["b"], "sb", match["sb"], status == "done" and win == match["b"]["tid"], editable and status in ("ready", "done"))
    if editable and status in ("ready", "done"):
        walk = ""
        if status == "ready":
            walk = ('<span class="walk">%s %s</span>' % (
                button_form("/day2/match/%s/walkover" % match["id"], "&uarr; 13-7", "small", {"winner": match["a"]["tid"]}),
                button_form("/day2/match/%s/walkover" % match["id"], "&darr; 13-7", "small", {"winner": match["b"]["tid"]})))
        inner = ('<form method="post" action="/day2/match/%s/score" class="mform">%s%s'
                 '<div class="actions"><button class="small">Save</button>%s</div></form>' % (match["id"], a, b, walk))
    else:
        inner = a + b
    return '<div class="match %s" id="%s">%s%s</div>' % (status, match["id"], court_html, inner)


def bracket_html(t, group, kind, rounds, editable):
    if not rounds:
        return ""
    columns = []
    for rnd, matches in enumerate(rounds):
        shuffle = ""
        if editable and any(m["status"] == "ready" for m in matches):
            shuffle = button_form("/day2/%s/%s/%d/shuffle" % (group["name"], kind, rnd), "shuffle courts", "small")
        columns.append('<div class="round"><h3>%s %s</h3><div class="matches">%s</div></div>' % (
            esc(brackets.round_name(len(matches))), shuffle, "".join(match_html(t, m, editable) for m in matches)))
    title = "Group %s" % group["name"] if kind == brackets.MAIN else "Group %s%s (consolation)" % (group["name"], group["name"])
    return '<section class="bracketsec"><h2>%s</h2><div class="bracket">%s</div></section>' % (esc(title), "".join(columns))


@route("GET", r"/day2/([A-Z])")
def group_page(app, req):
    t = app.tournament
    group = brackets.get_group(t, req.args[0])
    b = brackets.brackets(t, group)
    unplaced = [m for kind in brackets.KINDS for r in b[kind] for m in r if m["status"] == "ready" and m["court"] is None]
    names = " &middot; ".join(
        '<a href="/day2/%s">%s</a>' % (g["name"], g["name"]) if g["name"] != group["name"] else "<strong>%s</strong>" % g["name"]
        for g in brackets.day2(t)["groups"])
    body = """
<p class="switcher"><a href="/day2">All groups</a> &middot; %s</p>
<p class="row">
  <a class="button" href="/print/day2/%s" target="_blank">Print brackets</a>
  <span class="muted">Type both scores and the winner moves on. Courts are drawn when both teams are known,
  avoiding courts either team has played; shuffle redraws a round. &uarr; 13-7 and &darr; 13-7 record a no-show.</span>
</p>
%s
%s
%s
""" % (
        names, group["name"],
        "<div class='flash warn'>%d game(s) have no free court right now. Shuffle a round once other games finish.</div>" % len(unplaced) if unplaced else "",
        bracket_html(t, group, brackets.MAIN, b[brackets.MAIN], True),
        bracket_html(t, group, brackets.CONS, b[brackets.CONS], True),
    )
    return layout(app, req, "Group %s" % group["name"], body, "/day2")


def back_to_group(mid, msg=None, err=None):
    """Redirect to the group page, scrolled to the match (query before the anchor)."""
    from .server import redirect
    response = redirect("/day2/%s" % mid.split("-")[0], msg=msg, err=err)
    response.headers = [(k, v + "#" + mid if k == "Location" else v) for k, v in response.headers]
    return response


@route("POST", r"/day2/match/([A-Z]-(?:main|cons)-\d+-\d+)/score")
def match_score(app, req):
    mid = req.args[0]
    match = brackets.record_result(app.tournament, mid, req.get("sa", None), req.get("sb", None))
    app.save()
    if match["status"] == "done":
        return back_to_group(mid, msg="%s: %s wins" % (mid, model.team_name(app.tournament, match["winner"]["tid"])))
    return back_to_group(mid, msg="%s cleared." % mid)


@route("POST", r"/day2/match/([A-Z]-(?:main|cons)-\d+-\d+)/walkover")
def match_walkover(app, req):
    mid = req.args[0]
    winner = req.get("winner")
    if not winner.isdigit():
        raise model.ModelError("Bad team number.")
    brackets.record_walkover(app.tournament, mid, int(winner))
    app.save()
    return back_to_group(mid, msg="Recorded 13-7 for team %s." % winner)


@route("POST", r"/day2/([A-Z])/(main|cons)/(\d+)/shuffle")
def round_shuffle(app, req):
    name, kind, rnd = req.args
    brackets.shuffle_round(app.tournament, name, kind, rnd)
    app.save()
    from .server import redirect
    return redirect("/day2/%s" % name, msg="Courts redrawn.")


##################################
#######  print views        ######
##################################

@route("GET", r"/print/day2/([A-Z])")
def print_group(app, req):
    t = app.tournament
    group = brackets.get_group(t, req.args[0])
    b = brackets.brackets(t, group)
    pages = ['<section class="page landscape">%s</section>' % bracket_html(t, group, brackets.MAIN, b[brackets.MAIN], False)]
    if b[brackets.CONS]:
        pages.append('<section class="page landscape">%s</section>' % bracket_html(t, group, brackets.CONS, b[brackets.CONS], False))
    return print_layout(app, "Group %s brackets" % group["name"], "".join(pages), "print in landscape")


@route("GET", "/print/day2/groups")
def print_groups(app, req):
    t = app.tournament
    rows_by_tid = {row["tid"]: row for row in standings.standings(t)}
    pages = []
    for group in brackets.day2(t)["groups"]:
        rows = []
        for tid in group["teams"]:
            r = rows_by_tid.get(tid)
            rows.append([r["rank"] if r else "", esc(model.team_name(t, tid)), tid, r["wins"] if r else ""])
        pages.append('<section class="page"><h1>Group %s</h1>%s</section>' % (
            group["name"], table(["Rank", "Team", "Team #", "W"], rows, "list")))
    return print_layout(app, "Teams by group", "".join(pages))
