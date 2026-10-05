#!/usr/bin/env python3
"""Petanque America Open (PAO) tournament scheduler.

An interactive shell for running a multi-round petanque tournament: import
teams from a CSV, tell it which courts are available, then generate rounds
that avoid rematches and avoid pairing teams from the same group. Each round
can be exported as CSV for printing and for score entry.

    python3 pao.py <tournament-name>

Type `help` at the prompt for a guided command list. The same tournament
file can be opened in the web app: `python3 -m paoweb <tournament-name>`.
"""

import cmd
import csv
import pprint
import sys
import time

from paolib import model, scheduler, store, teamsio
from paolib.model import (  # noqa: F401  (re-exported for callers and tests)
    BYE_GROUP, DEFAULT_COURT_MAP, UNUSED_SECTION, new_tournament, migrate, utcnow,
)
from paolib.scheduler import MAX_ROUND_ATTEMPTS  # noqa: F401
from paolib.store import tournament_path  # noqa: F401
from paolib.teamsio import CSV_GROUP, CSV_NAME, CSV_NUMBER  # noqa: F401

VERSION = "0.4.0"


##################################
#######  table rendering   #######
##################################

def _normalize(rows):
    """Convert rows to equal-length lists of strings."""
    rows = [["" if c is None else str(c) for c in row] for row in rows]
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows], width


def _column_widths(rows, width):
    return [max(len(r[i]) for r in rows) for i in range(width)]


def _align(rows, col):
    """Right-align a column when every value in it looks like a number."""
    values = [r[col] for r in rows if r[col] != ""]
    return str.rjust if values and all(v.lstrip("-").isdigit() for v in values) else str.ljust


def render_grid(rows):
    """Render rows as an ASCII table with a border around every cell."""
    if not rows:
        return ""
    rows, width = _normalize(rows)
    widths = _column_widths(rows, width)
    aligns = [_align(rows, i) for i in range(width)]
    rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    out = [rule]
    for row in rows:
        cells = (align(cell, w) for cell, w, align in zip(row, widths, aligns))
        out.append("| " + " | ".join(cells) + " |")
        out.append(rule)
    return "\n".join(out)


def render_plain(rows):
    """Render rows as aligned columns with no borders."""
    if not rows:
        return ""
    rows, width = _normalize(rows)
    widths = _column_widths(rows, width)
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
        for row in rows
    )


def parse_flags(line):
    """Split a command line into (flags, positional arguments)."""
    tokens = line.split()
    flags = [t for t in tokens if t.startswith("-")]
    rest = [t for t in tokens if not t.startswith("-")]
    return flags, rest


HELP_OVERVIEW = """
Petanque America Open v%s

A typical tournament, start to finish:

    use amelia2025          open (or create) the tournament file
    cset a 1 90             courts 1-90 are the main field
    cset b 91 104           courts 91-104 are the annex (optional)
    load teams.csv          import teams from a CSV export
    tlist                   check the teams came in correctly
    zmake                   schedule a round     (repeat per round)
    zexport 1               write round 1 to CSV for printing and scoring
    save                    write the tournament file

Tournament
    use <name>       Open or create a tournament file
    info [-v]        Show tournament summary (-v dumps everything)
    save             Save now (most commands save automatically)
    quit             Exit

Teams
    load <file.csv>  Import teams from CSV
    team <n> <group> <name>   Add or update a team  (alias: tadd)
    tlist            List every team           (alias: ls teams)
    tshow <n>        Show one team and its schedule
    trem <n>         Remove a team
    tannex <n> <c>   Set how many times a team has played the annex
    texport          Export all teams to CSV

Courts
    cset <a|b> <from> <to>    Define a court section
    cusage [round]            Show used and unused courts for a round

Rounds
    zmake [-f]       Schedule the next round (-f ignores court history)
    zshow [round]    Show a round, or all rounds  (alias: ls schedule)
    zexport <round>  Export a round to CSV for printing and scoring
    zrem [round]     Delete a round (default: the last one)
    zclean           Delete every round, keeping the teams
    gadd <n> <opp> <court> [-s]   Add a single game by hand

Type `help <command>` for details on any one of these.
""".strip() % VERSION


class PetanqueTournament(cmd.Cmd):
    """Interactive shell for building and exporting tournament rounds."""

    prompt = ">> "
    intro = "Petanque America Open v%s\nType `help` for a guided command list, `quit` to quit." % VERSION

    def __init__(self, completekey="tab", stdin=None, stdout=None):
        super().__init__(completekey, stdin, stdout)
        self.tournament = new_tournament()

    ##################################
    #######  private helpers    ######
    ##################################

    def tournament_loaded(self):
        if self.tournament.get("name"):
            return True

        print("[ERROR] No tournament open. Start one with `use <name>`.")
        return False

    def set_prompt(self):
        self.prompt = "%s >> " % self.tournament.get("name")

    def save(self):
        try:
            store.save(self.tournament)
        except store.StoreError as exc:
            print("[ERROR]", exc)

    def export_csv(self, filename, rows):
        try:
            with open(filename, "wt", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(rows)
        except OSError as exc:
            print("[ERROR] Could not write %s: %s" % (filename, exc))
            return

        print("Exported ...", filename)

    def read_csv(self, filename):
        """Import teams from a CSV whose first row is a header."""
        try:
            rows, skipped = teamsio.read_teams_file(filename)
        except OSError:
            print("[ERROR] File not found:", filename)
            return

        added, updated, rejected = teamsio.import_teams(self.tournament, rows)
        self.save()
        print("Imported %d teams from %s" % (added + updated, filename))
        if skipped:
            print("[WARN]", teamsio.format_skipped(skipped))
        if teamsio.ungrouped(rows):
            print("[WARN]", teamsio.format_ungrouped(rows))
        for number, reason in rejected:
            print("[WARN] Team %d not imported: %s" % (number, reason))

    def add_team(self, num, group, name, quiet=False):
        """Insert or update a team, keeping any schedule it already has."""
        created, previous = model.add_team(self.tournament, num, group, name)
        if quiet:
            return
        if created:
            print("Added", num, group, name)
        else:
            print("Updated", num, group, name, "from", previous[0], previous[1])

    def is_court_a(self, num):
        return model.is_court_a(self.tournament, num)

    def is_court_b(self, num):
        return model.is_court_b(self.tournament, num)

    def court_map(self):
        """Return (all courts, section-a courts) as sorted lists."""
        return model.court_map(self.tournament)

    def rounds_played(self):
        return model.rounds_played(self.tournament)

    def format_team_game(self, tid, team, rnd):
        oid, court = model.team_game(self.tournament, tid, rnd)
        if oid is None:
            return [tid, team["name"], "sat out", "", "", "", ""]
        opp_name = model.team_name(self.tournament, oid)
        return [tid, team["name"], "vs", oid, opp_name, "court", court if court is not None else "?"]

    def teams_in_round(self, rnd):
        """Yield (tid, team) for every team with a game scheduled in `rnd`."""
        return model.teams_in_round(self.tournament, rnd)

    def show_rnd(self, rnd):
        table = [self.format_team_game(tid, team, rnd) for tid, team in self.teams_in_round(rnd)]
        if not table:
            print("Round %d has not been scheduled." % (rnd + 1))
            return

        print("Round", rnd + 1)
        print(render_grid(table))

    def export_rnd(self, rnd):
        matchups = [self.format_team_game(tid, team, rnd) for tid, team in self.teams_in_round(rnd)]
        if not matchups:
            print("[ERROR] Round %d has not been scheduled." % (rnd + 1))
            return

        scores = [[g.court if g.court is not None else "?", g.tid, 0, "", g.oid, 0]
                  for g in model.games_in_round(self.tournament, rnd)]

        stamp = int(time.time())
        name = self.tournament["name"]

        # One file to print and post, one file to type scores into.
        self.export_csv("%s_round_%d_%d.csv" % (name, rnd + 1, stamp), matchups)
        self.export_csv("%s_score_round_%d_%d.csv" % (name, rnd + 1, stamp), scores)

    ##################################
    #######  tournament CLI     ######
    ##################################

    def do_use(self, line):
        """usage: use <name>

        Open a tournament, creating it if it does not exist yet. The
        tournament is stored as <name>.p in the current directory.

        Example:
            use amelia2025
        """
        name = line.strip()
        if name.endswith(".p"):
            name = name[:-2]

        if not name:
            print("[ERROR] usage: use <name>")
            return

        try:
            self.tournament, created = store.open_or_create(name)
        except store.StoreError as exc:
            print("[ERROR]", exc)
            return

        if created:
            print("Created", tournament_path(name))
        else:
            print("Opened %s (%d teams, %d rounds)"
                  % (name, len(self.tournament["teams"]), self.rounds_played()))

        self.set_prompt()

    def do_save(self, line):
        """usage: save

        Write the tournament to disk. Most commands save automatically;
        this is here for peace of mind.
        """
        if self.tournament_loaded():
            self.save()
            print("Saved", tournament_path(self.tournament["name"]))

    def do_info(self, line):
        """usage: info [-v]

        Show a summary of the open tournament. -v also dumps the full
        underlying data, which is useful when something looks wrong.
        """
        if not self.tournament_loaded():
            return

        courts, courts_a = self.court_map()
        table = [
            ["Name", self.tournament.get("name")],
            ["Created", self.tournament.get("created_at")],
            ["Modified", self.tournament.get("modified_at")],
            ["Courts", ", ".join("%s: %s-%s" % (k, v[0], v[1])
                                 for k, v in sorted(self.tournament["court_map"].items())
                                 if tuple(v) != UNUSED_SECTION) or "none set"],
            ["Courts available", len(courts)],
            ["Teams", len(self.tournament["teams"])],
            ["Rounds", self.rounds_played()],
        ]
        print(render_grid(table))

        if "-v" in line:
            pprint.PrettyPrinter(indent=2).pprint(self.tournament)

    def do_help(self, arg):
        """usage: help [command]

        With no argument, print a guided overview of every command.
        With a command name, print the details for that command.
        """
        if arg:
            super().do_help(arg)
        else:
            print(HELP_OVERVIEW)

    def do_quit(self, line):
        """usage: quit

        Save and exit.
        """
        if self.tournament.get("name"):
            self.save()
        print("Bye.")
        return True

    def do_exit(self, line):
        """usage: exit

        Same as quit.
        """
        return self.do_quit(line)

    def do_EOF(self, line):
        """Exit on Ctrl-D."""
        print()
        return self.do_quit(line)

    ##################################
    #######  team CLI           ######
    ##################################

    def do_load(self, line):
        """usage: load <file.csv>

        Import teams from a CSV file. The first row is treated as a header
        and skipped. Columns must be, in order:

            number, group, name

        Extra columns are ignored. Rows without a numeric team number or
        without a name are skipped and reported.

        Example:
            load teams.csv
        """
        if not self.tournament_loaded():
            return

        filename = line.strip()
        if not filename:
            print("[ERROR] usage: load <file.csv>")
            return

        self.read_csv(filename)

    def do_team(self, line):
        """usage: team <number> <group> <name>

        Add a team, or update the group and name of an existing one. The
        name may contain spaces. Teams in the same group are never drawn
        against each other.

        Updating a team keeps any games it has already been scheduled for,
        so avoid renumbering teams once the tournament has started.

        Example:
            team 12 FL Smith/Jones
        """
        if not self.tournament_loaded():
            return

        args = line.split()
        if len(args) < 3:
            print("[ERROR] usage: team <number> <group> <name>")
            return

        number = args[0]
        if not number.isdigit():
            print("[ERROR] Team number must be a whole number.")
            return

        self.add_team(int(number), args[1], " ".join(args[2:]))
        self.save()

    def do_tadd(self, line):
        """usage: tadd <number> <group> <name>

        Same as `team`.
        """
        self.do_team(line)

    def do_tlist(self, line):
        """usage: tlist

        List every team with its group, opponents so far, courts played,
        and how many times it has played the annex.
        """
        if not self.tournament_loaded():
            return

        table = [[tid, t["group"], t["name"], t["games"], t["courts"], t["played_b"]]
                 for tid, t in sorted(self.tournament["teams"].items())]
        if table:
            print(render_grid([["No", "Group", "Name", "Played", "Courts", "Annex"]] + table))
        print("%d teams" % len(table))

    def do_tshow(self, line):
        """usage: tshow <number>

        Show one team's details and its full round-by-round schedule.

        Example:
            tshow 12
        """
        if not self.tournament_loaded():
            return

        if not line.strip().isdigit():
            print("[ERROR] usage: tshow <number>")
            return

        tid = int(line.strip())
        team = self.tournament["teams"].get(tid)
        if not team:
            print("[ERROR] Team %d not found." % tid)
            return

        print("Team Info")
        print(render_grid([
            ["No", tid],
            ["Name", team["name"]],
            ["Group", team["group"]],
            ["Played Annex", team["played_b"]],
        ]))

        schedule = [[rnd + 1] + self.format_team_game(tid, team, rnd)[3:]
                    for rnd in range(len(team["games"]))]
        if schedule:
            print("Schedule")
            print(render_grid(schedule))
        else:
            print("No games scheduled yet.")

    def do_trem(self, line):
        """usage: trem <number>

        Remove a team. If the team already appears in scheduled rounds,
        those games are reported so you can fix them by hand; the opponents
        keep their court assignments and show "(removed team)".

        Before the first round, `zclean` then `zmake` is usually cleaner.

        Example:
            trem 12
        """
        if not self.tournament_loaded():
            return

        if not line.strip().isdigit():
            print("[ERROR] usage: trem <number>")
            return

        tid = int(line.strip())
        team = self.tournament["teams"].get(tid)
        if not team:
            print("[ERROR] Team %d not found." % tid)
            return

        orphaned = model.remove_team(self.tournament, tid)
        self.save()
        print("Removed", tid, team["name"])

        if orphaned:
            print("[WARN] %d scheduled game(s) still reference this team. "
                  "Re-run `zmake`, or fix the affected rounds by hand." % orphaned)

    def do_tannex(self, line):
        """usage: tannex <number> <count>

        Record how many times a team has played on the annex courts
        (section b). Teams with a count above zero are given first claim on
        section a in the next round.

        Example:
            tannex 12 1
        """
        if not self.tournament_loaded():
            return

        args = line.split()
        if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
            print("[ERROR] usage: tannex <number> <count>")
            return

        tid, count = int(args[0]), int(args[1])
        team = self.tournament["teams"].get(tid)
        if not team:
            print("[ERROR] Team %d not found." % tid)
            return

        team["played_b"] = count
        self.save()
        print("Updated", tid, "played annex", count)

    def do_texport(self, line):
        """usage: texport

        Export every team to <tournament>_teams_<timestamp>.csv, with
        columns: number, name, group, opponents, courts, annex count.
        """
        if not self.tournament_loaded():
            return

        data = [[tid, t["name"], t["group"], t["games"], t["courts"], t["played_b"]]
                for tid, t in sorted(self.tournament["teams"].items())]
        self.export_csv("%s_teams_%d.csv" % (self.tournament["name"], int(time.time())), data)

    ##################################
    #######  court CLI          ######
    ##################################

    def do_cset(self, line):
        """usage: cset <a|b> <from> <to>

        Define the court numbers in a section. Section a is the main field
        and section b is the annex. Setting a section to `0 0` marks it
        unused.

        Example:
            cset a 1 90
            cset b 91 104
            cset b 0 0        no annex this year
        """
        if not self.tournament_loaded():
            return

        args = line.split()
        if len(args) != 3 or args[0] not in ("a", "b"):
            print("[ERROR] usage: cset <a|b> <from> <to>")
            return

        if not (args[1].isdigit() and args[2].isdigit()):
            print("[ERROR] Court numbers must be whole numbers.")
            return

        low, high = int(args[1]), int(args[2])
        try:
            model.set_section(self.tournament, args[0], low, high)
        except model.ModelError as exc:
            print("[ERROR]", exc)
            return
        self.save()

        courts, _ = self.court_map()
        if (low, high) == UNUSED_SECTION:
            print("Section %s is now unused. %d courts available." % (args[0], len(courts)))
        else:
            print("Section %s is courts %d-%d. %d courts available." % (args[0], low, high, len(courts)))

    def do_cusage(self, line):
        """usage: cusage [round]

        Show which courts were used and which sat empty in a round.
        Defaults to the most recent round.

        Example:
            cusage 3
        """
        if not self.tournament_loaded():
            return

        arg = line.strip()
        if arg and not arg.isdigit():
            print("[ERROR] usage: cusage [round]")
            return

        rnd = int(arg) - 1 if arg else self.rounds_played() - 1
        if rnd < 0:
            print("[ERROR] No rounds have been scheduled.")
            return

        courts, _ = self.court_map()
        used = sorted({team["courts"][rnd] for _, team in self.teams_in_round(rnd)
                       if len(team["courts"]) > rnd})
        if not used:
            print("[ERROR] Round %d has not been scheduled." % (rnd + 1))
            return

        print("Round %d used courts (%d)" % (rnd + 1, len(used)))
        print(render_plain([used]))

        unused = sorted(set(courts) - set(used))
        print("Round %d unused courts (%d)" % (rnd + 1, len(unused)))
        print(render_plain([unused]) if unused else "none")

    ##################################
    #######  round CLI          ######
    ##################################

    def do_zmake(self, line):
        """usage: zmake [-f] [-d]

        Schedule the next round. Opponents are drawn at random, avoiding
        rematches and avoiding teams from the same group. Courts are drawn
        at random from courts neither team has played on.

        If the draw paints itself into a corner it retries a few times.
        When it still cannot finish, use -f, which ignores court history
        and the annex rule so the round can be completed.

            -f   force: ignore previous court assignments
            -d   print each pairing as it is drawn

        `zmake` always creates the *next* round, so it takes no round
        number. Use `zrem` to delete a round you want to redraw.
        """
        if not self.tournament_loaded():
            return

        flags, extra = parse_flags(line)
        if extra:
            print("[NOTE] zmake always builds the next round; ignoring '%s'." % " ".join(extra))

        force = "-f" in flags
        debug = "-d" in flags or "-v" in flags

        def log(msg):
            if debug or msg.startswith("[INFO]"):
                print(msg)

        try:
            rnd = scheduler.draw_round(self.tournament, force=force, log=log)
        except scheduler.DrawFailed as exc:
            print("%s Try `zmake -f`." % exc)
            return
        except scheduler.DrawError as exc:
            print("[ERROR]", exc)
            return
        except Exception as exc:  # a bad draw should not kill the session
            print("[ERROR] Could not build the round:", exc)
            return

        self.save()
        self.show_rnd(rnd)

    def do_zshow(self, line):
        """usage: zshow [round | all]

        Print the matchups for a round. With no argument, or with `all`,
        print every round scheduled so far.

        Example:
            zshow 2
        """
        if not self.tournament_loaded():
            return

        arg = line.strip()
        total = self.rounds_played()

        if total == 0:
            print("No rounds have been scheduled. Use `zmake`.")
            return

        if arg in ("", "all"):
            for rnd in range(total):
                self.show_rnd(rnd)
            return

        if not arg.isdigit():
            print("[ERROR] usage: zshow [round | all]")
            return

        rnd = int(arg) - 1
        if not 0 <= rnd < total:
            print("[ERROR] Round %s does not exist. Rounds 1-%d are scheduled." % (arg, total))
            return

        self.show_rnd(rnd)

    def do_zexport(self, line):
        """usage: zexport <round>

        Write two CSV files for a round:

            <name>_round_<n>_<stamp>.csv         matchups, for printing
            <name>_score_round_<n>_<stamp>.csv   blank scores, for entry

        Example:
            zexport 1
        """
        if not self.tournament_loaded():
            return

        arg = line.strip()
        if not arg.isdigit():
            print("[ERROR] usage: zexport <round>   (a round number, starting at 1)")
            return

        rnd = int(arg) - 1
        total = self.rounds_played()
        if not 0 <= rnd < total:
            print("[ERROR] Round %s does not exist. Rounds 1-%d are scheduled." % (arg, total))
            return

        self.export_rnd(rnd)

    def do_zrem(self, line):
        """usage: zrem [round]

        Delete a round. With no argument, deletes the most recent round.
        Later rounds shift down, so deleting round 2 of 5 leaves 4 rounds.

        Example:
            zrem            delete the last round
            zrem 2          delete round 2
        """
        if not self.tournament_loaded():
            return

        arg = line.strip()
        total = self.rounds_played()
        if total == 0:
            print("No rounds have been scheduled.")
            return

        if arg in ("", "all"):
            rnd = -1
            label = "last round"
        elif arg.isdigit():
            rnd = int(arg) - 1
            if not 0 <= rnd < total:
                print("[ERROR] Round %s does not exist. Rounds 1-%d are scheduled." % (arg, total))
                return
            label = "round %s" % arg
        else:
            print("[ERROR] usage: zrem [round]")
            return

        affected = model.remove_round(self.tournament, rnd)
        self.save()
        print("Removed %s from %d teams. %d rounds remain." % (label, affected, self.rounds_played()))

    def do_zclean(self, line):
        """usage: zclean

        Delete every round, leaving the teams in place. Useful when the
        team list changes before the tournament starts.
        """
        if not self.tournament_loaded():
            return

        total = model.clear_rounds(self.tournament)
        self.save()
        print("Cleared %d round(s). %d teams kept." % (total, len(self.tournament["teams"])))

    def do_gadd(self, line):
        """usage: gadd <number> <opponent> <court> [-s]

        Add a single game by hand, appending it to both teams' schedules.
        Use this to patch a round rather than redrawing it.

            -s   record the game for <number> only, not for <opponent>

        Example:
            gadd 12 40 7
        """
        if not self.tournament_loaded():
            return

        flags, args = parse_flags(line)
        if len(args) != 3:
            print("[ERROR] usage: gadd <number> <opponent> <court> [-s]")
            return

        if not all(a.isdigit() for a in args):
            print("[ERROR] Team, opponent and court must be whole numbers.")
            return

        tid, oid, court = (int(a) for a in args)
        teams = self.tournament["teams"]
        try:
            model.add_game(self.tournament, tid, oid, court, both="-s" not in flags)
        except model.ModelError as exc:
            print("[ERROR]", exc)
            return

        self.save()
        print(tid, teams[tid]["name"], "vs", oid, teams[oid]["name"], "court", court)

    ##################################
    #######  shortcuts          ######
    ##################################

    def do_list(self, line):
        """usage: list <teams | schedule>

        Shortcut for `tlist` and `zshow`. Same as `ls`.
        """
        if not self.tournament_loaded():
            return

        arg = line.strip()
        if arg == "teams":
            self.do_tlist("")
        elif arg == "schedule":
            self.do_zshow("")
        else:
            print("[ERROR] usage: list <teams | schedule>")

    def do_ls(self, line):
        """usage: ls <teams | schedule>

        Same as `list`.
        """
        self.do_list(line)

    def emptyline(self):
        """Do nothing on a blank line rather than repeating the last command."""

    def default(self, line):
        print("[ERROR] Unknown command: %s. Type `help` for the command list." % line.split()[0])


def main(argv):
    name = argv[1] if len(argv) > 1 else "tournament"
    if name.endswith(".p"):
        name = name[:-2]

    cli = PetanqueTournament()
    cli.do_use(name)

    while True:
        try:
            cli.cmdloop()
            break
        except KeyboardInterrupt:
            print("\n(Ctrl-C ignored. Type `quit` to exit.)")
            cli.intro = None


if __name__ == "__main__":
    main(sys.argv)
