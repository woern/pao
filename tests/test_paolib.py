#!/usr/bin/env python3
"""Tests for the shared library: model edits, scores, standings, imports, storage."""

import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paolib import model, scheduler, standings, store, teamsio  # noqa: E402

GROUPS = ("FL", "GA", "TX", "MID", "LA", "CA")


def build(teams=0, courts=(1, 10), annex=None, name="t"):
    t = model.new_tournament(name)
    t["court_map"]["a"] = courts
    t["court_map"]["b"] = annex or model.UNUSED_SECTION
    for i in range(1, teams + 1):
        model.add_team(t, i, GROUPS[i % len(GROUPS)], "Team%d" % i)
    return t


class TestGames(unittest.TestCase):

    def test_games_in_round_lists_each_game_once_by_court(self):
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 3)
        model.add_game(t, 3, 4, 1)
        games = model.games_in_round(t, 0)
        self.assertEqual([(g.court, g.tid, g.oid) for g in games], [(1, 3, 4), (3, 1, 2)])

    def test_single_sided_game_still_listed(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 3, both=False)
        self.assertEqual(model.games_in_round(t, 0), [model.Game(3, 1, 2)])

    def test_set_game_replaces_both_sides_and_clears_scores(self):
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 3, 4, 2)
        model.set_game_score(t, 0, 1, 2, 13, 5)
        model.set_game(t, 0, 1, 3, 4)
        self.assertEqual(t["teams"][1]["games"], [3])
        self.assertEqual(t["teams"][3]["games"], [1])
        self.assertEqual(t["teams"][1]["courts"], [4])
        self.assertIsNone(model.get_score(t, 0, 1))
        self.assertEqual(model.get_score(t, 0, 2), 5)  # untouched team keeps its score

    def test_set_game_appends_when_round_is_next(self):
        t = build(2, courts=(1, 4))
        model.set_game(t, 0, 1, 2, 2)
        self.assertEqual(model.rounds_played(t), 1)

    def test_set_game_rejects_gaps_self_and_unknown(self):
        t = build(2, courts=(1, 4))
        with self.assertRaises(model.ModelError):
            model.set_game(t, 2, 1, 2, 1)       # round 3 before round 1
        with self.assertRaises(model.ModelError):
            model.set_game(t, 0, 1, 1, 1)
        with self.assertRaises(model.ModelError):
            model.set_game(t, 0, 1, 9, 1)

    def test_set_game_tracks_annex_count(self):
        t = build(2, courts=(1, 2), annex=(3, 4))
        model.add_game(t, 1, 2, 3)
        self.assertEqual(t["teams"][1]["played_b"], 1)
        model.set_game(t, 0, 1, 2, 1)
        self.assertEqual(t["teams"][1]["played_b"], 0)

    def test_remove_round_shifts_scores_down(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 1, 2, 2)
        model.set_game_score(t, 0, 1, 2, 13, 1)
        model.set_game_score(t, 1, 1, 2, 13, 2)
        model.remove_round(t, 0)
        self.assertEqual(model.get_score(t, 0, 2), 2)
        self.assertNotIn(1, t["scores"])

    def test_remove_team_drops_its_scores(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.set_game_score(t, 0, 1, 2, 13, 1)
        self.assertEqual(model.remove_team(t, 2), 1)
        self.assertNotIn(2, t["scores"][0])

    def test_clear_rounds_clears_scores_and_tiebreaks(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.set_game_score(t, 0, 1, 2, 13, 1)
        t["tiebreaks"][1] = {"key": [1, 12, 13.0], "pos": 1}
        model.clear_rounds(t)
        self.assertEqual(t["scores"], {})
        self.assertEqual(t["tiebreaks"], {})


class TestScores(unittest.TestCase):

    def test_parse_score(self):
        self.assertEqual(model.parse_score("13"), 13)
        self.assertEqual(model.parse_score(" 7 "), 7)
        self.assertIsNone(model.parse_score(""))
        self.assertIsNone(model.parse_score(None))
        for bad in ("14", "-1", "x", "1.5"):
            with self.assertRaises(model.ModelError):
                model.parse_score(bad)

    def test_game_status(self):
        self.assertEqual(model.game_status(None, None), "missing")
        self.assertEqual(model.game_status(13, None), "partial")
        self.assertEqual(model.game_status(7, 7), "tied")
        self.assertEqual(model.game_status(13, 7), "ok")

    def test_set_game_score_requires_drawn_round(self):
        t = build(2, courts=(1, 4))
        with self.assertRaises(model.ModelError):
            model.set_game_score(t, 0, 1, 2, 13, 7)

    def test_clearing_a_score(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.set_game_score(t, 0, 1, 2, 13, 7)
        model.set_game_score(t, 0, 1, 2, None, None)
        self.assertEqual(t["scores"], {})

    def test_walkover(self):
        t = build(2, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.record_walkover(t, 0, 2, 1)
        self.assertEqual(model.game_scores(t, 0, model.Game(1, 1, 2)), (7, 13))

    def test_bye_is_scored_automatically_on_draw(self):
        random.seed(1)
        t = build(5, courts=(1, 6))
        rnd = scheduler.draw_round(t)
        bye = [tid for tid, team in t["teams"].items() if model.is_bye(team)]
        self.assertEqual(len(bye), 1)
        opp, _ = model.team_game(t, bye[0], rnd)
        self.assertEqual(model.get_score(t, rnd, opp), 13)
        self.assertEqual(model.get_score(t, rnd, bye[0]), 7)
        self.assertNotIn(bye[0], [tid for tid, _ in model.real_teams(t)])
        self.assertEqual(model.round_score_summary(t, rnd)["ok"], 1)


class TestScheduler(unittest.TestCase):

    def byes(self, t):
        return sorted(tid for tid, team in t["teams"].items() if model.is_bye(team))

    def test_even_count_never_gets_a_bye(self):
        random.seed(3)
        t = build(8, courts=(1, 8))
        scheduler.draw_round(t)
        self.assertEqual(self.byes(t), [])

    def test_bye_sits_out_once_the_count_is_even_again(self):
        random.seed(3)
        t = build(5, courts=(1, 20))
        scheduler.draw_round(t)
        self.assertEqual(len(self.byes(t)), 1)
        bye = self.byes(t)[0]
        with self.assertRaises(model.ModelError):
            model.add_team(t, bye, "TX", "Late arrival")   # the BYE's number is taken
        model.add_team(t, bye + 1, "TX", "Late arrival")
        rnd = scheduler.draw_round(t)
        self.assertEqual(len(self.byes(t)), 1, "a second BYE was added")
        self.assertNotIn(bye, [tid for tid, _ in model.teams_in_round(t, rnd)])
        self.assertEqual(len(model.games_in_round(t, rnd)), 3)

    def test_existing_bye_is_reused_when_needed_again(self):
        random.seed(3)
        t = build(5, courts=(1, 20))
        scheduler.draw_round(t)
        bye = self.byes(t)[0]
        model.add_team(t, bye + 1, "TX", "Late arrival")
        scheduler.draw_round(t)          # even: bye sits out
        model.remove_team(t, bye + 1)
        rnd = scheduler.draw_round(t)    # odd again: same bye plays
        self.assertEqual(self.byes(t), [bye])
        self.assertIn(bye, [tid for tid, _ in model.teams_in_round(t, rnd)])
        # The round it sat out is a None placeholder, so round N is always index N.
        self.assertEqual(t["teams"][bye]["games"][1], None)
        self.assertEqual(len(t["teams"][bye]["games"]), 3)

    def test_repeated_courts_are_reported_after_a_forced_draw(self):
        # 4 teams on 2 courts: after round 1 every court has been used by a
        # team in each pairing, so round 2 cannot avoid a repeat.
        random.seed(0)
        t = build(4, courts=(1, 2))
        scheduler.draw_round(t)
        self.assertEqual(model.repeated_courts(t, 0), [])
        with self.assertRaises(scheduler.DrawFailed):
            scheduler.draw_round(t)
        rnd = scheduler.draw_round(t, force=True)
        repeats = model.repeated_courts(t, rnd)
        self.assertTrue(repeats)
        for tid, court in repeats:
            self.assertIn(court, t["teams"][tid]["courts"][:rnd])

    def test_late_arrival_gets_placeholders_for_missed_rounds(self):
        random.seed(4)
        t = build(8, courts=(1, 20))
        scheduler.draw_round(t)
        model.add_team(t, 9, "TX", "Late")
        model.add_team(t, 10, "LA", "Later")
        rnd = scheduler.draw_round(t)
        self.assertEqual(t["teams"][9]["games"][0], None)
        self.assertIsNotNone(t["teams"][9]["games"][1])
        self.assertEqual(model.team_game(t, 9, 0), (None, None))
        self.assertEqual([tid for tid, _ in model.teams_absent_from_round(t, 0)], [9, 10])
        rows = {r["tid"]: r for r in standings.standings(t)}
        self.assertEqual(rows[9]["rounds"][0]["status"], "absent")
        self.assertEqual(rows[9]["played"], 0)

    def test_draw_round_returns_index_and_is_valid(self):
        for seed in range(5):
            random.seed(seed)
            t = build(24, courts=(1, 18))
            for expected in range(4):
                self.assertEqual(scheduler.draw_round(t), expected)
            for tid, team in t["teams"].items():
                self.assertEqual(len(set(team["games"])), 4, "rematch for %d" % tid)
                for oid in team["games"]:
                    self.assertNotEqual(team["group"], t["teams"][oid]["group"])

    def test_hard_errors(self):
        with self.assertRaises(scheduler.DrawError):
            scheduler.draw_round(build(1))
        with self.assertRaises(scheduler.DrawError):
            scheduler.draw_round(build(20, courts=(1, 4)))

    def test_deadlock_raises_draw_failed_and_force_recovers(self):
        random.seed(0)
        t = build(20, courts=(1, 6), annex=(7, 20))
        scheduler.draw_round(t)
        with self.assertRaises(scheduler.DrawFailed):
            scheduler.draw_round(t)
        self.assertEqual(model.rounds_played(t), 1)
        self.assertEqual(scheduler.draw_round(t, force=True), 1)


class TestStandings(unittest.TestCase):

    def scored(self):
        """Four teams, one round: 1 beats 2 13-5, 3 beats 4 13-11."""
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 3, 4, 2)
        model.set_game_score(t, 0, 1, 2, 13, 5)
        model.set_game_score(t, 0, 3, 4, 13, 11)
        return t

    def test_order_and_columns(self):
        rows = standings.standings(self.scored())
        self.assertEqual([r["tid"] for r in rows], [1, 3, 4, 2])
        top = rows[0]
        self.assertEqual((top["wins"], top["diff"], top["pf"], top["pa"]), (1, 8, 13, 5))
        self.assertAlmostEqual(top["ratio"], 13 / 5)
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3, 4])
        self.assertTrue(all(r["tie"] is None for r in rows))

    def test_buchholz_breaks_ties_before_the_coin_flip(self):
        # Teams 1 and 3 both win 13-5; 2 and 4 both lose. Then 2 beats 4, so
        # team 1's opponent (2) has a win and team 3's opponent (4) does not.
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 3, 4, 2)
        model.set_game_score(t, 0, 1, 2, 13, 5)
        model.set_game_score(t, 0, 3, 4, 13, 5)
        model.add_game(t, 2, 4, 1)
        model.add_game(t, 1, 3, 2)
        model.set_game_score(t, 1, 2, 4, 13, 12)
        model.set_game_score(t, 1, 1, 3, 13, 12)
        rows = {r["tid"]: r for r in standings.standings(t)}
        self.assertEqual(rows[1]["buchholz"], 1 + 1)   # opponents 2 (1 win) and 3 (1 win)
        self.assertEqual(rows[3]["buchholz"], 0 + 2)   # opponents 4 (0 wins) and 1 (2 wins)

        # Undo round 2 for 1 v 3 so they tie on wins, diff and ratio again.
        model.set_game_score(t, 1, 1, 3, None, None)
        rows = standings.standings(t)
        one, three = (r for r in rows if r["tid"] in (1, 3))
        self.assertEqual(one["key"][:3], three["key"][:3])
        self.assertEqual([r["tid"] for r in rows[:2]], [1, 3])   # 1 ahead on Buchholz (1 vs 0)
        self.assertEqual([r["rank"] for r in rows[:2]], [1, 2])
        self.assertEqual(standings.unresolved_ties(t, rows), [])

    def test_ratio_falls_back_to_points_for(self):
        self.assertEqual(standings.ratio(13, 0), 13.0)

    def test_unscored_games_do_not_count(self):
        t = self.scored()
        model.add_game(t, 1, 3, 1)
        model.add_game(t, 2, 4, 2)
        rows = {r["tid"]: r for r in standings.standings(t)}
        self.assertEqual(rows[1]["played"], 1)
        self.assertEqual(rows[1]["rounds"][1]["status"], "missing")

    def test_ties_are_detected_and_resolved_by_coin_flip(self):
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 3, 4, 2)
        model.set_game_score(t, 0, 1, 2, 13, 5)
        model.set_game_score(t, 0, 3, 4, 13, 5)
        rows = standings.standings(t)
        self.assertEqual([r["rank"] for r in rows], [1, 1, 3, 3])
        self.assertEqual(len(standings.unresolved_ties(t, rows)), 2)

        standings.set_tiebreak(t, [3, 1])
        rows = standings.standings(t)
        self.assertEqual([(r["tid"], r["rank"]) for r in rows[:2]], [(3, 1), (1, 2)])
        self.assertEqual(len(standings.unresolved_ties(t, rows)), 1)

    def test_stale_tiebreak_is_ignored_when_scores_change(self):
        t = build(4, courts=(1, 4))
        model.add_game(t, 1, 2, 1)
        model.add_game(t, 3, 4, 2)
        model.set_game_score(t, 0, 1, 2, 13, 5)
        model.set_game_score(t, 0, 3, 4, 13, 5)
        standings.set_tiebreak(t, [3, 1])
        model.set_game_score(t, 0, 1, 2, 13, 2)   # team 1 now clearly ahead
        rows = standings.standings(t)
        self.assertEqual(rows[0]["tid"], 1)
        self.assertEqual(rows[0]["tiebreak"], 0)

    def test_tiebreak_rejects_teams_that_are_not_tied(self):
        with self.assertRaises(model.ModelError):
            standings.set_tiebreak(self.scored(), [1, 2])
        with self.assertRaises(model.ModelError):
            standings.set_tiebreak(self.scored(), [1])
        with self.assertRaises(model.ModelError):
            standings.set_tiebreak(self.scored(), [1, 99])

    def test_bye_team_is_excluded(self):
        random.seed(2)
        t = build(5, courts=(1, 6))
        scheduler.draw_round(t)
        self.assertEqual(len(standings.standings(t)), 5)


class TestTeamsIO(unittest.TestCase):

    def test_header_auto_detection(self):
        rows, skipped = teamsio.parse_teams("Number,Category,Team Name\n1,FL,Alpha\n2,GA,Bravo\n")
        self.assertEqual(rows, [(1, "FL", "Alpha"), (2, "GA", "Bravo")])
        rows, _ = teamsio.parse_teams("1,FL,Alpha\n2,GA,Bravo\n")
        self.assertEqual(len(rows), 2)
        rows, _ = teamsio.parse_teams("1,FL,Alpha\n2,GA,Bravo\n", header=True)
        self.assertEqual(len(rows), 1)

    def test_tab_separated_paste(self):
        rows, _ = teamsio.parse_teams("Number\tCategory\tTeam Name\tCaptain\n1\tFL\tAlpha\tSomeone\n")
        self.assertEqual(rows, [(1, "FL", "Alpha")])

    def test_bad_rows_reported_with_line_numbers(self):
        text = "n,g,name\n1,FL,Alpha\nx,GA,Bravo\n3,TX,\n4\n\n5,LA,Echo\n"
        rows, skipped = teamsio.parse_teams(text)
        self.assertEqual([r[0] for r in rows], [1, 5])
        self.assertEqual(skipped, [3, 4])   # bad number; no name. "4" alone is an empty row.
        self.assertIn("Skipped 2", teamsio.format_skipped(skipped))

    def test_bom_is_stripped(self):
        rows, _ = teamsio.parse_teams("﻿1,FL,Alpha\n")
        self.assertEqual(rows, [(1, "FL", "Alpha")])

    def test_empty_rows_ignored_and_half_empty_rows_reported(self):
        text = "1,FL,Alpha\n2,,/\n3,,\n\n4,,Delta\n5,GA,/\n6,GA,Foxtrot\n"
        rows, skipped = teamsio.parse_teams(text)
        self.assertEqual([r[0] for r in rows], [1, 6])
        self.assertEqual(skipped, [5, 6])   # no group; no name
        self.assertTrue(teamsio.is_blank(" / "))
        self.assertFalse(teamsio.is_blank("Smith/Jones"))

    def test_import_counts_added_and_updated(self):
        t = build(1)
        added, updated, rejected = teamsio.import_teams(t, [(1, "FL", "New name"), (2, "GA", "Two")])
        self.assertEqual((added, updated, rejected), (1, 1, []))
        self.assertEqual(t["teams"][1]["name"], "New name")

    def test_import_cannot_overwrite_the_bye(self):
        t = build(3)
        bye = model.add_bye_team(t)
        added, updated, rejected = teamsio.import_teams(t, [(bye, "FL", "Sneaky")])
        self.assertEqual((added, updated), (0, 0))
        self.assertEqual(rejected[0][0], bye)
        self.assertTrue(model.is_bye(t["teams"][bye]))


class TestStore(unittest.TestCase):

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="pao-test-")
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_roundtrip_keeps_scores(self):
        t = build(2, courts=(1, 4), name="rt")
        model.add_game(t, 1, 2, 1)
        model.set_game_score(t, 0, 1, 2, 13, 7)
        store.save(t)
        loaded = store.load("rt")
        self.assertEqual(model.get_score(loaded, 0, 1), 13)
        self.assertEqual(os.listdir("."), ["rt.p"])   # no temp files left behind

    def test_open_or_create(self):
        t, created = store.open_or_create("fresh")
        self.assertTrue(created)
        self.assertTrue(os.path.isfile("fresh.p"))
        _, created = store.open_or_create("fresh")
        self.assertFalse(created)

    def test_bad_file_raises(self):
        with open("bad.p", "wb") as fh:
            fh.write(b"nope")
        with self.assertRaises(store.StoreError):
            store.load("bad")


if __name__ == "__main__":
    unittest.main()
