#!/usr/bin/env python3
"""Tests for Day 2: groups, seeding, advancement, consolation and courts."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paolib import brackets, model, scheduler, standings  # noqa: E402

GROUPS = ("FL", "GA", "TX", "MID", "LA", "CA", "NE", "NW")


def played(teams, rounds=1, courts=(1, 120)):
    """A tournament with `rounds` drawn and every game scored, lower number wins."""
    random.seed(1)
    t = model.new_tournament("d2")
    t["court_map"]["a"] = courts
    for i in range(1, teams + 1):
        model.add_team(t, i, GROUPS[i % len(GROUPS)], "Team%d" % i)
    for _ in range(rounds):
        rnd = scheduler.draw_round(t)
        for g in model.games_in_round(t, rnd):
            if model.game_status(*model.game_scores(t, rnd, g)) == "ok":
                continue   # the BYE game is already 13-7
            lo, hi = sorted((g.tid, g.oid))
            model.set_game_score(t, rnd, lo, hi, 13, (lo * 7) % 12)
    for tie in standings.unresolved_ties(t):
        standings.set_tiebreak(t, [r["tid"] for r in tie])
    return t


def score(t, mid, sa, sb):
    return brackets.record_result(t, mid, sa, sb)


class TestShape(unittest.TestCase):

    def test_seed_order_matches_the_sheets(self):
        order = brackets.seed_order(32)
        pairs = [tuple(order[i:i + 2]) for i in range(0, 32, 2)]
        self.assertEqual(pairs[:4], [(1, 32), (16, 17), (8, 25), (9, 24)])
        self.assertEqual(set(order), set(range(1, 33)))
        self.assertEqual(brackets.seed_order(2), [1, 2])

    def test_sizes_and_names(self):
        self.assertEqual([brackets.bracket_size(n) for n in (2, 3, 14, 32, 33)], [2, 4, 16, 32, 64])
        self.assertEqual(brackets.round_name(1), "Final")
        self.assertEqual(brackets.round_name(16), "1/16 Finals")
        self.assertEqual(brackets.suggest_sizes(174), [32, 32, 32, 32, 32, 14])
        self.assertEqual(brackets.suggest_sizes(11), [11])


class TestGroups(unittest.TestCase):

    def test_day1_must_be_complete(self):
        t = played(8)
        ok, reason = brackets.day1_complete(t)
        self.assertTrue(ok, reason)
        model.set_game_score(t, 0, 1, t["teams"][1]["games"][0], None, None)
        ok, reason = brackets.day1_complete(t)
        self.assertFalse(ok)
        self.assertIn("without a valid score", reason)
        with self.assertRaises(model.ModelError):
            brackets.make_groups(t, [8])

    def test_groups_follow_the_standings_and_skip_the_bye(self):
        t = played(11)   # odd: a BYE exists
        ranked = brackets.ranked_team_ids(t)
        self.assertEqual(len(ranked), 11)
        groups = brackets.make_groups(t, [8, 3], {"A": True, "B": False})
        self.assertEqual([g["name"] for g in groups], ["A", "B"])
        self.assertEqual(groups[0]["teams"], ranked[:8])
        self.assertEqual(groups[1]["teams"], ranked[8:])
        self.assertFalse(groups[1]["consolation"])
        self.assertFalse(brackets.groups_out_of_date(t))

    def test_bad_sizes(self):
        t = played(8)
        for sizes in ([], [4, 3], [9], [7, 1]):
            with self.assertRaises(model.ModelError):
                brackets.plan_groups(t, sizes)

    def test_out_of_date_after_day1_edit(self):
        t = played(8)
        brackets.make_groups(t, [8])
        top = brackets.ranked_team_ids(t)[0]
        opp = t["teams"][top]["games"][0]
        model.set_game_score(t, 0, top, opp, 0, 13)
        self.assertTrue(brackets.groups_out_of_date(t))


class TestBracket(unittest.TestCase):

    def test_first_round_pairs_seeds(self):
        t = played(32)
        group = brackets.make_groups(t, [32])[0]
        rounds = brackets.main_bracket(t, group)
        self.assertEqual(len(rounds), 5)
        self.assertEqual([len(r) for r in rounds], [16, 8, 4, 2, 1])
        first = rounds[0][0]
        self.assertEqual((first["a"]["seed"], first["b"]["seed"]), (1, 32))
        self.assertEqual(first["a"]["tid"], group["teams"][0])
        self.assertEqual(first["status"], "ready")
        self.assertEqual(rounds[1][0]["status"], "pending")
        self.assertEqual(brackets.consolation_bracket(t, group)[0][0]["status"], "pending")

    def test_winner_advances_and_loser_drops_to_consolation(self):
        t = played(32)
        group = brackets.make_groups(t, [32])[0]
        m0, m1 = brackets.main_bracket(t, group)[0][:2]
        score(t, m0["id"], 13, 5)               # seed 1 beats seed 32
        score(t, m1["id"], 7, 13)               # seed 17 beats seed 16
        b = brackets.brackets(t, group)
        second = b[brackets.MAIN][1][0]
        self.assertEqual((second["a"]["seed"], second["b"]["seed"]), (1, 17))
        self.assertEqual(second["status"], "ready")
        cons = b[brackets.CONS][0][0]
        self.assertEqual((cons["a"]["seed"], cons["b"]["seed"]), (32, 16))
        self.assertEqual(cons["status"], "ready")

    def test_rejects_ties_and_unready_matches(self):
        t = played(8)
        group = brackets.make_groups(t, [8])[0]
        rounds = brackets.main_bracket(t, group)
        with self.assertRaises(model.ModelError):
            score(t, rounds[0][0]["id"], 9, 9)
        with self.assertRaises(model.ModelError):
            score(t, rounds[1][0]["id"], 13, 1)
        with self.assertRaises(model.ModelError):
            score(t, rounds[0][0]["id"], 13, None)

    def test_changing_an_early_result_voids_what_depended_on_it(self):
        t = played(8)
        group = brackets.make_groups(t, [8])[0]
        r0 = brackets.main_bracket(t, group)[0]
        score(t, r0[0]["id"], 13, 2)
        score(t, r0[1]["id"], 13, 4)
        semi = brackets.main_bracket(t, group)[1][0]
        score(t, semi["id"], 13, 6)
        self.assertEqual(brackets.main_bracket(t, group)[1][0]["status"], "done")

        score(t, r0[0]["id"], 3, 13)            # the other team wins after all
        b = brackets.brackets(t, group)
        semi = b[brackets.MAIN][1][0]
        self.assertEqual(semi["status"], "ready")
        self.assertEqual(semi["a"]["seed"], 8)
        self.assertIsNone(semi["sa"])
        self.assertIsNone(t["day2"]["matches"][semi["id"]]["sa"])   # stale score pruned
        cons = b[brackets.CONS][0][0]
        self.assertEqual(cons["a"]["seed"], 1)  # seed 1 now in the consolation

    def test_clearing_a_result(self):
        t = played(8)
        group = brackets.make_groups(t, [8])[0]
        mid = brackets.main_bracket(t, group)[0][0]["id"]
        score(t, mid, 13, 2)
        score(t, mid, None, None)
        self.assertEqual(brackets.find_match(t, mid)["status"], "ready")

    def test_walkover(self):
        t = played(8)
        group = brackets.make_groups(t, [8])[0]
        match = brackets.main_bracket(t, group)[0][0]
        brackets.record_walkover(t, match["id"], match["b"]["tid"])
        match = brackets.find_match(t, match["id"])
        self.assertEqual((match["sa"], match["sb"]), (7, 13))
        with self.assertRaises(model.ModelError):
            brackets.record_walkover(t, match["id"], 999)

    def test_small_group_gets_byes_for_top_seeds(self):
        t = played(14, courts=(1, 40))
        group = brackets.make_groups(t, [14])[0]
        b = brackets.brackets(t, group)
        main = b[brackets.MAIN]
        self.assertEqual(len(main), 4)             # bracket of 16
        walkovers = [m for m in main[0] if m["status"] == "walkover"]
        self.assertEqual(len(walkovers), 2)
        self.assertEqual({m["winner"]["seed"] for m in walkovers}, {1, 2})
        # Seeds 1 and 2 are already in round 2; their consolation slots are byes.
        seeds_in_r1 = {s["seed"] for m in main[1] for s in (m["a"], m["b"]) if s["tid"]}
        self.assertEqual(seeds_in_r1, {1, 2})
        cons = b[brackets.CONS][0]
        self.assertEqual(sum(1 for m in cons if m["a"]["bye"] or m["b"]["bye"]), 2)

    def test_full_run_crowns_a_champion(self):
        t = played(8)
        group = brackets.make_groups(t, [8])[0]
        for _ in range(3):
            for kind in brackets.KINDS:
                for matches in brackets.brackets(t, group)[kind]:
                    for m in matches:
                        if m["status"] == "ready":
                            score(t, m["id"], 13, 8)
        s = brackets.group_summary(t, group)
        self.assertEqual((s["main_done"], s["main_total"]), (7, 7))
        self.assertEqual((s["cons_done"], s["cons_total"]), (3, 3))
        self.assertEqual(s["main_champion"], group["teams"][0])
        self.assertIsNotNone(s["cons_champion"])


class TestCourts(unittest.TestCase):

    def ready(self, t):
        return [m for m in brackets.all_matches(t) if m["status"] == "ready"]

    def test_ready_matches_get_distinct_free_courts(self):
        t = played(32, courts=(1, 40))
        brackets.make_groups(t, [16, 16])
        ready = self.ready(t)
        self.assertEqual(len(ready), 16)
        courts = [m["court"] for m in ready]
        self.assertTrue(all(c is not None for c in courts))
        self.assertEqual(len(set(courts)), len(courts))

    def test_courts_avoid_history_when_possible(self):
        t = played(8, courts=(1, 40))
        brackets.make_groups(t, [8])
        for m in self.ready(t):
            for tid in (m["a"]["tid"], m["b"]["tid"]):
                self.assertNotIn(m["court"], t["teams"][tid]["courts"])

    def test_court_is_released_after_a_result_and_next_round_gets_one(self):
        t = played(8, courts=(1, 4))            # only 4 courts for 4 first-round games
        group = brackets.make_groups(t, [8])[0]
        r0 = brackets.main_bracket(t, group)[0]
        self.assertEqual(len({m["court"] for m in r0}), 4)
        score(t, r0[0]["id"], 13, 1)
        score(t, r0[1]["id"], 13, 1)
        b = brackets.brackets(t, group)
        semi = b[brackets.MAIN][1][0]
        cons = b[brackets.CONS][0][0]
        self.assertIsNotNone(semi["court"])
        self.assertIsNotNone(cons["court"])
        held = [m["court"] for m in brackets.all_matches(t) if m["status"] == "ready"]
        self.assertEqual(len(held), len(set(held)))

    def test_shuffle_keeps_courts_valid(self):
        t = played(16, courts=(1, 40))
        group = brackets.make_groups(t, [16])[0]
        before = [m["court"] for m in brackets.main_bracket(t, group)[0]]
        random.seed(7)
        brackets.shuffle_round(t, "A", brackets.MAIN, 0)
        after = [m["court"] for m in brackets.main_bracket(t, group)[0]]
        self.assertEqual(len(set(after)), 8)
        self.assertNotEqual(before, after)
        with self.assertRaises(model.ModelError):
            brackets.shuffle_round(t, "A", brackets.MAIN, 9)

    def test_no_court_when_none_free(self):
        t = played(8, courts=(1, 4))
        t["court_map"]["a"] = (1, 2)             # two courts lost overnight
        brackets.make_groups(t, [8])
        ready = self.ready(t)
        self.assertEqual(sum(1 for m in ready if m["court"] is not None), 2)
        self.assertEqual(sum(1 for m in ready if m["court"] is None), 2)


if __name__ == "__main__":
    unittest.main()
