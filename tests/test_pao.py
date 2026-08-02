#!/usr/bin/env python3
"""Tests for the PAO tournament scheduler.

Run from the repository root:

    python3 -m unittest discover

The scheduler is random, so the invariant tests sweep a range of seeds rather
than pinning one. Anything that touches disk runs inside a temporary
directory, because the program reads and writes relative to the current one.
"""

import contextlib
import glob
import io
import os
import pickle
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pao  # noqa: E402


GROUPS = ("FL", "GA", "TX", "MID", "LA", "CA")


@contextlib.contextmanager
def _redirected(fn, buf):
    """Redirect both print() and cmd.Cmd's own self.stdout writes into buf."""
    owner = getattr(fn, "__self__", None)
    had_stdout = hasattr(owner, "stdout")
    previous = getattr(owner, "stdout", None)
    if had_stdout:
        owner.stdout = buf
    try:
        with contextlib.redirect_stdout(buf):
            yield
    finally:
        if had_stdout:
            owner.stdout = previous


def quiet(fn, *args):
    """Call fn, swallowing what it prints."""
    with _redirected(fn, io.StringIO()):
        return fn(*args)


def capture(fn, *args):
    """Call fn, returning what it printed."""
    buf = io.StringIO()
    with _redirected(fn, buf):
        fn(*args)
    return buf.getvalue()


class TempDirCase(unittest.TestCase):
    """Base case that runs each test in its own scratch directory."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="pao-test-")
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def make_cli(self, teams=0, courts=(1, 10), annex=None, name="test", groups=GROUPS):
        cli = pao.PetanqueTournament()
        cli.tournament = pao.new_tournament(name)
        cli.tournament["court_map"]["a"] = courts
        cli.tournament["court_map"]["b"] = annex or pao.UNUSED_SECTION
        for i in range(1, teams + 1):
            cli.add_team(i, groups[i % len(groups)], "Team%d" % i, quiet=True)
        return cli

    def draw(self, cli, rounds, flags=""):
        """Draw up to `rounds` rounds; return how many actually succeeded."""
        for _ in range(rounds):
            quiet(cli.do_zmake, flags)
        return cli.rounds_played()

    def assertScheduleValid(self, cli, msg=""):
        """Assert every invariant the draw is supposed to guarantee."""
        teams = cli.tournament["teams"]

        for rnd in range(cli.rounds_played()):
            occupancy = {}
            for tid, team in teams.items():
                if len(team["games"]) <= rnd:
                    continue
                oid = team["games"][rnd]
                court = team["courts"][rnd]

                self.assertIn(oid, teams, "%s r%d: team %d plays unknown team %d" % (msg, rnd, tid, oid))
                self.assertEqual(teams[oid]["games"][rnd], tid,
                                 "%s r%d: %d/%d schedules disagree" % (msg, rnd, tid, oid))
                self.assertEqual(teams[oid]["courts"][rnd], court,
                                 "%s r%d: %d/%d on different courts" % (msg, rnd, tid, oid))
                self.assertNotEqual(tid, oid, "%s r%d: team %d plays itself" % (msg, rnd, tid))
                self.assertNotEqual(team["group"], teams[oid]["group"],
                                    "%s r%d: %d vs %d share group" % (msg, rnd, tid, oid))
                self.assertNotEqual(court, 0, "%s r%d: team %d on court 0" % (msg, rnd, tid))

                occupancy.setdefault(court, set()).update((tid, oid))

            for court, occupants in occupancy.items():
                self.assertEqual(len(occupants), 2,
                                 "%s r%d: court %d holds %d teams" % (msg, rnd, court, len(occupants)))

        for tid, team in teams.items():
            self.assertEqual(len(set(team["games"])), len(team["games"]),
                             "%s: team %d has a rematch: %s" % (msg, tid, team["games"]))
            self.assertEqual(len(team["games"]), len(team["courts"]),
                             "%s: team %d games/courts out of step" % (msg, tid))


class TestTableRendering(unittest.TestCase):

    def test_grid_borders_and_padding(self):
        out = pao.render_grid([["a", "bb"]]).splitlines()
        self.assertEqual(out[0], "+---+----+")
        self.assertEqual(out[1], "| a | bb |")
        self.assertEqual(out[2], "+---+----+")

    def test_numeric_columns_right_align(self):
        out = pao.render_grid([["x", 1], ["y", 100]]).splitlines()
        self.assertIn("|   1 |", out[1])
        self.assertIn("| 100 |", out[3])

    def test_text_columns_left_align(self):
        out = pao.render_grid([["a", "x"], ["bbb", "y"]]).splitlines()
        self.assertIn("| a   |", out[1])

    def test_ragged_rows_are_padded(self):
        # A short row must not raise or misalign the table.
        out = pao.render_grid([["a", "b", "c"], ["d"]]).splitlines()
        self.assertEqual(len(out[1]), len(out[3]))

    def test_empty_input(self):
        self.assertEqual(pao.render_grid([]), "")
        self.assertEqual(pao.render_plain([]), "")

    def test_none_renders_blank(self):
        self.assertIn("|  |", pao.render_grid([[None]]))

    def test_plain_has_no_borders(self):
        out = pao.render_plain([[1, 2, 3]])
        self.assertNotIn("|", out)
        self.assertNotIn("+", out)


class TestParseFlags(unittest.TestCase):

    def test_splits_flags_from_positionals(self):
        self.assertEqual(pao.parse_flags("1 -f 2 -d"), (["-f", "-d"], ["1", "2"]))

    def test_empty(self):
        self.assertEqual(pao.parse_flags(""), ([], []))

    def test_flags_only(self):
        self.assertEqual(pao.parse_flags("  -f  "), (["-f"], []))


class TestCourtMap(TempDirCase):

    def test_unused_section_contributes_no_courts(self):
        cli = self.make_cli(courts=(1, 5))
        courts, courts_a = cli.court_map()
        self.assertEqual(courts, [1, 2, 3, 4, 5])
        self.assertEqual(courts_a, [1, 2, 3, 4, 5])

    def test_default_map_excludes_court_zero(self):
        # The b=(0,0) sentinel used to leak court 0 into the playable pool.
        cli = pao.PetanqueTournament()
        cli.tournament = pao.new_tournament("t")
        courts, _ = cli.court_map()
        self.assertNotIn(0, courts)

    def test_annex_courts_included_but_not_in_section_a(self):
        cli = self.make_cli(courts=(1, 3), annex=(4, 6))
        courts, courts_a = cli.court_map()
        self.assertEqual(courts, [1, 2, 3, 4, 5, 6])
        self.assertEqual(courts_a, [1, 2, 3])
        self.assertTrue(cli.is_court_a(2))
        self.assertFalse(cli.is_court_a(5))
        self.assertTrue(cli.is_court_b(5))

    def test_unused_section_is_not_a_court(self):
        cli = self.make_cli(courts=(1, 3))
        self.assertFalse(cli.is_court_b(0))

    def test_cset_rejects_bad_input(self):
        cli = self.make_cli(courts=(1, 5))
        for bad in ("a 0 5", "x 1 2", "a 5 1", "a", "a one two"):
            quiet(cli.do_cset, bad)
        # None of the rejected inputs may have changed the map.
        self.assertEqual(tuple(cli.tournament["court_map"]["a"]), (1, 5))

    def test_cset_accepts_zero_zero_as_unused(self):
        cli = self.make_cli(courts=(1, 5), annex=(6, 8))
        quiet(cli.do_cset, "b 0 0")
        courts, _ = cli.court_map()
        self.assertEqual(courts, [1, 2, 3, 4, 5])


class TestTeams(TempDirCase):

    def test_add_then_update_preserves_schedule(self):
        cli = self.make_cli(teams=4, courts=(1, 4))
        self.draw(cli, 1)
        before = list(cli.tournament["teams"][1]["games"])

        quiet(cli.do_team, "1 ZZ Renamed Team")
        team = cli.tournament["teams"][1]
        self.assertEqual(team["name"], "Renamed Team")
        self.assertEqual(team["group"], "ZZ")
        self.assertEqual(team["games"], before)

    def test_team_name_may_contain_spaces(self):
        cli = self.make_cli()
        quiet(cli.do_team, "1 FL Smith / Jones Jr")
        self.assertEqual(cli.tournament["teams"][1]["name"], "Smith / Jones Jr")

    def test_team_rejects_non_numeric_number(self):
        cli = self.make_cli()
        quiet(cli.do_team, "abc FL Someone")
        self.assertEqual(cli.tournament["teams"], {})

    def test_team_requires_three_fields(self):
        cli = self.make_cli()
        quiet(cli.do_team, "1 FL")
        self.assertEqual(cli.tournament["teams"], {})

    def test_tannex_sets_count(self):
        cli = self.make_cli(teams=2)
        quiet(cli.do_tannex, "1 3")
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 3)

    def test_tannex_rejects_bad_input(self):
        cli = self.make_cli(teams=2)
        for bad in ("1", "1 x", "x 1", "1 2 3"):
            quiet(cli.do_tannex, bad)
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 0)

    def test_trem_warns_about_scheduled_games(self):
        cli = self.make_cli(teams=4, courts=(1, 4))
        self.draw(cli, 1)
        out = capture(cli.do_trem, "1")
        self.assertNotIn(1, cli.tournament["teams"])
        self.assertIn("WARN", out)

    def test_removed_team_does_not_break_rendering(self):
        # Previously a dangling opponent id raised KeyError when showing a round.
        cli = self.make_cli(teams=4, courts=(1, 4))
        self.draw(cli, 1)
        quiet(cli.do_trem, "1")
        out = capture(cli.do_zshow, "1")
        self.assertIn("removed team", out)

    def test_trem_on_unscheduled_team_is_silent(self):
        cli = self.make_cli(teams=4)
        out = capture(cli.do_trem, "1")
        self.assertNotIn("WARN", out)


class TestCsvImport(TempDirCase):

    def write_csv(self, text, name="teams.csv", encoding="utf-8"):
        with open(name, "w", encoding=encoding) as fh:
            fh.write(text)
        return name

    def test_imports_and_skips_header(self):
        path = self.write_csv("Number,Category,Team Name\n1,FL,Alpha\n2,GA,Bravo\n")
        cli = self.make_cli()
        quiet(cli.do_load, path)
        self.assertEqual(len(cli.tournament["teams"]), 2)
        self.assertEqual(cli.tournament["teams"][1]["name"], "Alpha")
        self.assertEqual(cli.tournament["teams"][2]["group"], "GA")

    def test_extra_columns_are_ignored(self):
        path = self.write_csv("n,g,name,captain,email\n1,FL,Alpha,Someone,a@example.com\n")
        cli = self.make_cli()
        quiet(cli.do_load, path)
        self.assertEqual(cli.tournament["teams"][1]["name"], "Alpha")

    def test_bad_rows_are_skipped_and_reported(self):
        path = self.write_csv(
            "n,g,name\n"
            "1,FL,Alpha\n"
            "notanumber,GA,Bravo\n"   # non-numeric number
            "3,TX,\n"                 # no name
            "4\n"                     # too few columns
            "\n"                      # blank
            "5,LA,Echo\n"
        )
        cli = self.make_cli()
        out = capture(cli.do_load, path)
        self.assertEqual(sorted(cli.tournament["teams"]), [1, 5])
        self.assertIn("Skipped 3", out)

    def test_byte_order_mark_is_stripped(self):
        # Excel and Google Sheets prepend a BOM, which would otherwise make
        # the first team number non-numeric.
        path = self.write_csv("n,g,name\n1,FL,Alpha\n", encoding="utf-8-sig")
        cli = self.make_cli()
        quiet(cli.do_load, path)
        self.assertIn(1, cli.tournament["teams"])

    def test_reimport_updates_without_losing_schedule(self):
        path = self.write_csv("n,g,name\n1,FL,Alpha\n2,GA,Bravo\n3,TX,Chas\n4,LA,Delt\n")
        cli = self.make_cli(courts=(1, 4))
        quiet(cli.do_load, path)
        self.draw(cli, 1)
        games = list(cli.tournament["teams"][1]["games"])

        self.write_csv("n,g,name\n1,FL,Alpha Corrected\n2,GA,Bravo\n3,TX,Chas\n4,LA,Delt\n", path)
        quiet(cli.do_load, path)
        self.assertEqual(cli.tournament["teams"][1]["name"], "Alpha Corrected")
        self.assertEqual(cli.tournament["teams"][1]["games"], games)

    def test_missing_file_reports_error(self):
        cli = self.make_cli()
        out = capture(cli.do_load, "nope.csv")
        self.assertIn("ERROR", out)

    def test_blank_group_becomes_placeholder(self):
        path = self.write_csv("n,g,name\n1,,Alpha\n")
        cli = self.make_cli()
        quiet(cli.do_load, path)
        self.assertEqual(cli.tournament["teams"][1]["group"], "-")


class TestSchedulerInvariants(TempDirCase):
    """The draw must never quietly produce an invalid tournament."""

    def test_invariants_across_sizes_and_seeds(self):
        for n_teams, courts in ((8, (1, 8)), (24, (1, 24)), (60, (1, 45))):
            for seed in range(8):
                random.seed(seed)
                cli = self.make_cli(teams=n_teams, courts=courts)
                self.draw(cli, 5)
                self.assertScheduleValid(cli, "n=%d seed=%d" % (n_teams, seed))

    def test_real_tournament_size(self):
        # The configuration actually used at Amelia Island: 179 teams, 90 courts.
        for seed in range(3):
            random.seed(seed)
            cli = self.make_cli(teams=179, courts=(1, 90))
            drawn = self.draw(cli, 5)
            self.assertEqual(drawn, 5, "seed %d only drew %d rounds" % (seed, drawn))
            self.assertScheduleValid(cli, "179 teams seed=%d" % seed)

    def test_force_still_respects_rematch_and_group_rules(self):
        # -f relaxes court history only. It must not start pairing rematches.
        for seed in range(8):
            random.seed(seed)
            cli = self.make_cli(teams=20, courts=(1, 10))
            self.draw(cli, 5, "-f")
            self.assertScheduleValid(cli, "forced seed=%d" % seed)

    def test_force_recovers_a_tight_board(self):
        random.seed(3)
        cli = self.make_cli(teams=20, courts=(1, 5), annex=(6, 10))
        unforced = self.draw(cli, 5)
        forced = self.draw(cli, 5 - unforced, "-f")
        self.assertGreater(forced, unforced, "-f should complete rounds the plain draw could not")
        self.assertScheduleValid(cli, "tight board")

    def test_odd_team_count_gets_one_bye(self):
        random.seed(0)
        cli = self.make_cli(teams=7, courts=(1, 8))
        self.draw(cli, 1)

        self.assertEqual(len(cli.tournament["teams"]), 8)
        byes = [t for t in cli.tournament["teams"].values() if t["name"].startswith("BYE-")]
        self.assertEqual(len(byes), 1)
        self.assertEqual(byes[0]["group"], pao.BYE_GROUP)
        self.assertScheduleValid(cli, "odd count")

    def test_no_second_bye_on_later_rounds(self):
        random.seed(0)
        cli = self.make_cli(teams=7, courts=(1, 8))
        self.draw(cli, 3)
        byes = [t for t in cli.tournament["teams"].values() if t["name"].startswith("BYE-")]
        self.assertEqual(len(byes), 1)

    def test_refuses_to_draw_without_enough_courts(self):
        cli = self.make_cli(teams=20, courts=(1, 4))
        out = capture(cli.do_zmake, "")
        self.assertEqual(cli.rounds_played(), 0)
        self.assertIn("courts", out)

    def test_refuses_to_draw_with_one_team(self):
        cli = self.make_cli(teams=1, courts=(1, 4))
        quiet(cli.do_zmake, "")
        self.assertEqual(cli.rounds_played(), 0)

    def test_round_number_argument_is_reported_not_silently_ignored(self):
        cli = self.make_cli(teams=4, courts=(1, 4))
        out = capture(cli.do_zmake, "1 -f")
        self.assertIn("NOTE", out)
        self.assertEqual(cli.rounds_played(), 1)

    def test_failed_draw_leaves_previous_rounds_untouched(self):
        random.seed(0)
        cli = self.make_cli(teams=6, courts=(1, 3))
        self.draw(cli, 1)
        snapshot = {k: (list(v["games"]), list(v["courts"]))
                    for k, v in cli.tournament["teams"].items()}

        for _ in range(6):  # keep drawing until one fails
            quiet(cli.do_zmake, "")

        for tid, team in cli.tournament["teams"].items():
            games, courts = snapshot[tid]
            self.assertEqual(team["games"][:len(games)], games)
            self.assertEqual(team["courts"][:len(courts)], courts)


class TestAnnexFairness(TempDirCase):

    def test_annex_teams_move_to_main_field_next_round(self):
        # Section a is deliberately smaller than the number of games, so the
        # first round spills onto the annex.
        for seed in range(4):
            random.seed(seed)
            cli = self.make_cli(teams=20, courts=(1, 8), annex=(9, 40))
            self.draw(cli, 1)

            annexed = {tid for tid, t in cli.tournament["teams"].items() if t["played_b"] > 0}
            self.assertTrue(annexed, "seed %d: expected the first round to use the annex" % seed)

            self.assertEqual(self.draw(cli, 1), 2, "seed %d: second round did not draw" % seed)

            for tid in annexed:
                court = cli.tournament["teams"][tid]["courts"][1]
                self.assertTrue(cli.is_court_a(court),
                                "seed %d: team %d played the annex then got court %d again"
                                % (seed, tid, court))

    def test_oversized_annex_deadlocks_until_forced(self):
        """Annex teams cannot be drawn against each other, so each one needs a
        section-a court of its own. When more teams are sent to the annex than
        there are main-field courts, no later round can be built at all --- on
        any seed --- and the only way out is -f.

        Here: 10 games on 6 main courts spills 4 games (8 teams) onto the
        annex, and those 8 teams then need 8 main courts that do not exist.
        """
        for seed in range(4):
            random.seed(seed)
            cli = self.make_cli(teams=20, courts=(1, 6), annex=(7, 20))
            self.assertEqual(self.draw(cli, 1), 1)

            annexed = sum(1 for t in cli.tournament["teams"].values() if t["played_b"] > 0)
            _, courts_a = cli.court_map()
            self.assertGreater(annexed, len(courts_a))

            self.assertEqual(self.draw(cli, 3), 1, "seed %d: expected a deadlock" % seed)
            self.assertEqual(self.draw(cli, 1, "-f"), 2, "seed %d: -f should break the deadlock" % seed)
            self.assertScheduleValid(cli, "forced past deadlock, seed=%d" % seed)

    def test_annex_counter_tracks_actual_play(self):
        cli = self.make_cli(teams=2, courts=(1, 2), annex=(3, 4))
        quiet(cli.do_gadd, "1 2 3")
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 1)
        quiet(cli.do_gadd, "1 2 4")
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 2)


class TestRoundRemoval(TempDirCase):

    def test_zrem_removes_last_round(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 3)
        quiet(cli.do_zrem, "")
        self.assertEqual(cli.rounds_played(), 2)
        self.assertScheduleValid(cli)

    def test_zrem_removes_specific_round_and_shifts(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 3)
        third = {k: v["games"][2] for k, v in cli.tournament["teams"].items()}

        quiet(cli.do_zrem, "2")
        self.assertEqual(cli.rounds_played(), 2)
        for tid, opponent in third.items():
            self.assertEqual(cli.tournament["teams"][tid]["games"][1], opponent,
                             "round 3 should have shifted down into slot 2")

    def test_zrem_decrements_annex_count(self):
        # The old implementation reset played_b to 0, losing earlier annex duty.
        cli = self.make_cli(teams=2, courts=(1, 2), annex=(3, 4))
        quiet(cli.do_gadd, "1 2 3")
        quiet(cli.do_gadd, "1 2 4")
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 2)

        quiet(cli.do_zrem, "")
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 1)

    def test_zrem_rejects_out_of_range(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 2)
        out = capture(cli.do_zrem, "9")
        self.assertIn("ERROR", out)
        self.assertEqual(cli.rounds_played(), 2)

    def test_zclean_keeps_teams(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 3)
        quiet(cli.do_zclean, "")
        self.assertEqual(cli.rounds_played(), 0)
        self.assertEqual(len(cli.tournament["teams"]), 8)
        self.assertTrue(all(t["played_b"] == 0 for t in cli.tournament["teams"].values()))

    def test_redraw_after_clean_is_valid(self):
        random.seed(2)
        cli = self.make_cli(teams=12, courts=(1, 12))
        self.draw(cli, 3)
        quiet(cli.do_zclean, "")
        self.draw(cli, 3)
        self.assertScheduleValid(cli, "after zclean")


class TestGadd(TempDirCase):

    def test_gadd_records_both_teams(self):
        cli = self.make_cli(teams=2, courts=(1, 4))
        quiet(cli.do_gadd, "1 2 3")
        self.assertEqual(cli.tournament["teams"][1]["games"], [2])
        self.assertEqual(cli.tournament["teams"][2]["games"], [1])

    def test_gadd_single_sided_flag(self):
        # -s used to be dropped because of an off-by-one on the argument list.
        cli = self.make_cli(teams=2, courts=(1, 4))
        quiet(cli.do_gadd, "1 2 3 -s")
        self.assertEqual(cli.tournament["teams"][1]["games"], [2])
        self.assertEqual(cli.tournament["teams"][2]["games"], [])

    def test_gadd_rejects_unknown_team(self):
        cli = self.make_cli(teams=2, courts=(1, 4))
        out = capture(cli.do_gadd, "1 99 3")
        self.assertIn("ERROR", out)
        self.assertEqual(cli.tournament["teams"][1]["games"], [])

    def test_gadd_rejects_non_numeric(self):
        cli = self.make_cli(teams=2, courts=(1, 4))
        out = capture(cli.do_gadd, "1 two 3")
        self.assertIn("ERROR", out)

    def test_gadd_requires_three_arguments(self):
        cli = self.make_cli(teams=2, courts=(1, 4))
        out = capture(cli.do_gadd, "1 2")
        self.assertIn("usage", out)


class TestPersistence(TempDirCase):

    def test_use_creates_and_reopens(self):
        cli = pao.PetanqueTournament()
        quiet(cli.do_use, "alpha")
        quiet(cli.do_team, "1 FL Alpha")

        reopened = pao.PetanqueTournament()
        quiet(reopened.do_use, "alpha")
        self.assertEqual(reopened.tournament["teams"][1]["name"], "Alpha")

    def test_use_does_not_carry_teams_between_tournaments(self):
        # State used to live on the class, so a new tournament inherited the
        # previous one's teams and immediately saved them.
        cli = pao.PetanqueTournament()
        quiet(cli.do_use, "first")
        quiet(cli.do_team, "1 FL Alpha")
        quiet(cli.do_use, "second")

        self.assertEqual(cli.tournament["teams"], {})
        with open("second.p", "rb") as fh:
            self.assertEqual(pickle.load(fh)["teams"], {})

    def test_fresh_instances_do_not_share_state(self):
        a = pao.PetanqueTournament()
        b = pao.PetanqueTournament()
        quiet(a.do_use, "one")
        quiet(a.do_team, "1 FL Alpha")
        quiet(b.do_use, "two")
        self.assertEqual(b.tournament["teams"], {})

    def test_use_strips_dot_p_suffix(self):
        cli = pao.PetanqueTournament()
        quiet(cli.do_use, "alpha.p")
        self.assertEqual(cli.tournament["name"], "alpha")
        self.assertTrue(os.path.isfile("alpha.p"))

    def test_commands_require_an_open_tournament(self):
        cli = pao.PetanqueTournament()
        out = capture(cli.do_tlist, "")
        self.assertIn("ERROR", out)

    def test_legacy_file_migrates(self):
        # Files written by the 2021-2024 versions have no court_map and their
        # teams have no played_b.
        legacy = {
            "name": "legacy",
            "teams": {
                1: {"name": "Old A", "group": "FL", "games": [2], "courts": [3]},
                2: {"name": "Old B", "group": "GA", "games": [1], "courts": [3]},
            },
        }
        with open("legacy.p", "wb") as fh:
            pickle.dump(legacy, fh)

        cli = pao.PetanqueTournament()
        quiet(cli.do_use, "legacy")

        self.assertEqual(cli.tournament["court_map"]["a"], pao.DEFAULT_COURT_MAP["a"])
        self.assertEqual(cli.tournament["teams"][1]["played_b"], 0)
        self.assertEqual(cli.rounds_played(), 1)
        quiet(cli.do_zshow, "1")  # must not raise

    def test_corrupt_file_reports_error(self):
        with open("broken.p", "wb") as fh:
            fh.write(b"this is not a pickle")

        cli = pao.PetanqueTournament()
        out = capture(cli.do_use, "broken")
        self.assertIn("ERROR", out)


class TestExports(TempDirCase):

    def only(self, pattern):
        matches = glob.glob(pattern)
        self.assertEqual(len(matches), 1, "expected one %s, found %s" % (pattern, matches))
        return matches[0]

    def read_rows(self, path):
        import csv
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))

    def test_zexport_writes_matchup_and_score_files(self):
        random.seed(0)
        cli = self.make_cli(teams=8, courts=(1, 8), name="expo")
        self.draw(cli, 1)
        quiet(cli.do_zexport, "1")

        matchups = self.read_rows(self.only("expo_round_1_*.csv"))
        scores = self.read_rows(self.only("expo_score_round_1_*.csv"))

        # One matchup row per team, one score row per game.
        self.assertEqual(len(matchups), 8)
        self.assertEqual(len(scores), 4)

        for row in matchups:
            self.assertEqual(len(row), 7)
            self.assertEqual(row[2], "vs")
            self.assertEqual(row[5], "court")

        for row in scores:
            self.assertEqual(len(row), 6)
            self.assertEqual(row[2], "0")   # blank score for the first team
            self.assertEqual(row[3], "")    # spacer column
            self.assertEqual(row[5], "0")   # blank score for the opponent

    def test_score_rows_cover_every_team_once(self):
        random.seed(0)
        cli = self.make_cli(teams=8, courts=(1, 8), name="expo")
        self.draw(cli, 1)
        quiet(cli.do_zexport, "1")

        scores = self.read_rows(self.only("expo_score_round_1_*.csv"))
        listed = [int(r[1]) for r in scores] + [int(r[4]) for r in scores]
        self.assertEqual(sorted(listed), list(range(1, 9)))

    def test_zexport_rejects_missing_round(self):
        cli = self.make_cli(teams=8, courts=(1, 8), name="expo")
        self.draw(cli, 1)
        out = capture(cli.do_zexport, "4")
        self.assertIn("ERROR", out)
        self.assertEqual(glob.glob("expo_round_4_*.csv"), [])

    def test_zexport_requires_a_round_number(self):
        cli = self.make_cli(teams=8, courts=(1, 8), name="expo")
        self.draw(cli, 1)
        out = capture(cli.do_zexport, "")
        self.assertIn("usage", out)

    def test_texport_lists_every_team(self):
        cli = self.make_cli(teams=5, courts=(1, 6), name="expo")
        quiet(cli.do_texport, "")
        rows = self.read_rows(self.only("expo_teams_*.csv"))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][0], "1")


class TestDisplayCommands(TempDirCase):
    """These mostly guard against regressions in output-only commands."""

    def test_zshow_all_lists_every_round(self):
        # zshow used a Python 2 idiom and failed on every invocation.
        random.seed(0)
        cli = self.make_cli(teams=8, courts=(1, 8))
        drawn = self.draw(cli, 3)
        self.assertGreaterEqual(drawn, 2, "need several rounds for this to be meaningful")

        for arg in ("", "all"):
            out = capture(cli.do_zshow, arg)
            for rnd in range(1, drawn + 1):
                self.assertIn("Round %d" % rnd, out)
            self.assertNotIn("Round %d" % (drawn + 1), out)
            self.assertNotIn("went wrong", out)

    def test_zshow_single_round(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 2)
        out = capture(cli.do_zshow, "2")
        self.assertIn("Round 2", out)
        self.assertNotIn("Round 1", out)

    def test_zshow_rejects_out_of_range(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 1)
        self.assertIn("ERROR", capture(cli.do_zshow, "5"))

    def test_zshow_without_rounds(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.assertIn("zmake", capture(cli.do_zshow, ""))

    def test_cusage_splits_used_and_unused(self):
        random.seed(0)
        cli = self.make_cli(teams=8, courts=(1, 10))
        self.draw(cli, 1)
        out = capture(cli.do_cusage, "1")
        self.assertIn("used courts (4)", out)
        self.assertIn("unused courts (6)", out)

    def test_cusage_defaults_to_latest_round(self):
        cli = self.make_cli(teams=8, courts=(1, 10))
        self.draw(cli, 2)
        self.assertIn("Round 2", capture(cli.do_cusage, ""))

    def test_tshow_reports_schedule(self):
        cli = self.make_cli(teams=8, courts=(1, 8))
        self.draw(cli, 2)
        out = capture(cli.do_tshow, "1")
        self.assertIn("Team Info", out)
        self.assertIn("Schedule", out)

    def test_tshow_unknown_team(self):
        cli = self.make_cli(teams=4)
        self.assertIn("ERROR", capture(cli.do_tshow, "99"))

    def test_help_overview_lists_command_groups(self):
        cli = self.make_cli()
        out = capture(cli.do_help, "")
        for heading in ("Tournament", "Teams", "Courts", "Rounds"):
            self.assertIn(heading, out)

    def test_help_for_one_command(self):
        cli = self.make_cli()
        self.assertIn("usage: zmake", capture(cli.do_help, "zmake"))

    def test_every_command_has_help(self):
        cli = self.make_cli()
        for name in (n[3:] for n in dir(cli) if n.startswith("do_")):
            if name == "EOF":
                continue
            self.assertTrue(getattr(cli, "do_" + name).__doc__,
                            "command `%s` has no help text" % name)

    def test_unknown_command_is_reported(self):
        cli = self.make_cli()
        self.assertIn("Unknown command", capture(cli.default, "wibble"))

    def test_info_reports_counts(self):
        cli = self.make_cli(teams=6, courts=(1, 6))
        self.draw(cli, 1)
        out = capture(cli.do_info, "")
        self.assertIn("Teams", out)
        self.assertIn("Rounds", out)

    def test_ls_shortcuts(self):
        cli = self.make_cli(teams=4, courts=(1, 4))
        self.draw(cli, 1)
        self.assertIn("teams", capture(cli.do_ls, "teams").lower())
        self.assertIn("Round 1", capture(cli.do_ls, "schedule"))
        self.assertIn("usage", capture(cli.do_ls, "nonsense"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
