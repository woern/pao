#!/usr/bin/env python3
"""Smoke tests for the web app: a real server on a spare port, in a temp dir."""

import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paoweb import pages  # noqa: E402
from paoweb.server import App, serve  # noqa: E402

TEAMS = "n,g,name\n" + "".join("%d,%s,Team%d\n" % (i, "FL" if i % 2 else "GA", i) for i in range(1, 13))


class WebCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls._tmp = tempfile.mkdtemp(prefix="pao-web-")
        os.chdir(cls._tmp)
        cls.app = App("webtest")
        pages.register(cls.app)
        cls.server = serve(cls.app, port=0, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        os.chdir(cls._cwd)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def request(self, method, path, form=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, data, headers)
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        location = response.getheader("Location", "")
        conn.close()
        return response.status, location, text

    def test_full_day_one_flow(self):
        status, _, text = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Import the team list", text)

        status, location, _ = self.request("POST", "/teams/import", form={"text": TEAMS})
        self.assertEqual(status, 303)
        self.assertIn("Imported+12+teams", location)

        status, location, _ = self.request("POST", "/setup", form={"a_from": 1, "a_to": 8, "b_from": 0, "b_to": 0})
        self.assertEqual(status, 303)
        self.assertIn("Courts+saved", location)

        for expected in (1, 2):
            status, location, _ = self.request("POST", "/rounds/draw", form={})
            self.assertEqual(status, 303)
            self.assertTrue(location.endswith("?msg=Drew+round+%d." % expected), location)

        status, _, text = self.request("GET", "/rounds/1")
        self.assertEqual(status, 200)
        self.assertIn("Team1", text)

        # Autosave one game through the JSON endpoint.
        opp = self.app.tournament["teams"][1]["games"][0]
        status, _, text = self.request("POST", "/api/score", body={"round": 1, "tid": 1, "oid": opp, "a": "13", "b": "4"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["status"], "ok")

        # Bad score comes back as a JSON error, not a crash.
        status, _, text = self.request("POST", "/api/score", body={"round": 1, "tid": 1, "oid": opp, "a": "14", "b": "4"})
        self.assertEqual(status, 400)
        self.assertIn("between 0 and 13", json.loads(text)["error"])

        # Save-all form and a walkover.
        form = {"s_%d" % tid: "" for tid in self.app.tournament["teams"]}
        form["s_1"], form["s_%d" % opp] = "13", "9"
        status, location, _ = self.request("POST", "/rounds/1/scores", form=form)
        self.assertEqual(status, 303)
        self.assertIn("1+of+6+games+scored", location)

        tid2 = 2 if 2 != opp else 3
        opp2 = self.app.tournament["teams"][tid2]["games"][0]
        status, location, _ = self.request("POST", "/rounds/1/walkover", form={"winner": tid2, "loser": opp2})
        self.assertEqual(status, 303)
        self.assertEqual(self.app.tournament["scores"][0][tid2], 13)

        # Round 1 stays editable after round 2 is drawn, and the page links both rounds.
        status, _, text = self.request("GET", "/rounds/1/scores")
        self.assertEqual(status, 200)
        self.assertIn('href="/rounds/2/scores"', text)
        self.assertIn('href="/rounds">All rounds</a>', text)
        status, _, text = self.request("GET", "/rounds/2")
        self.assertIn('href="/rounds">All rounds</a>', text)
        form["s_1"], form["s_%d" % opp] = "13", "11"
        status, _, _ = self.request("POST", "/rounds/1/scores", form=form)
        self.assertEqual(status, 303)
        self.assertEqual(self.app.tournament["scores"][0][opp], 11)

        status, _, text = self.request("GET", "/standings")
        self.assertEqual(status, 200)
        self.assertIn("not fully scored", text)
        self.assertIn("Team1", text)

        for path in ("/print/rounds/1/cards", "/print/rounds/1/list", "/print/rounds/1/slips", "/print/standings"):
            status, _, text = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIn("window.print()", text)

        # Persisted: a fresh load sees the scores.
        from paolib import store
        self.assertEqual(store.load("webtest")["scores"][0][1], 13)

    def test_tight_courts_draw_anyway_and_warn(self):
        app = App("tight")
        pages.register(app)
        server = serve(app, port=0, quiet=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            saved_port, self.port = self.port, server.server_address[1]
            teams = "n,g,name\n1,A,One\n2,B,Two\n3,C,Three\n4,D,Four\n"
            self.request("POST", "/teams/import", form={"text": teams})
            self.request("POST", "/setup", form={"a_from": 1, "a_to": 2, "b_from": 0, "b_to": 0})
            status, location, _ = self.request("POST", "/rounds/draw", form={})
            self.assertEqual(status, 303)
            self.assertNotIn("err=", location)
            status, location, _ = self.request("POST", "/rounds/draw", form={})
            self.assertEqual(status, 303)
            self.assertIn("/rounds/2?", location)
            self.assertIn("court+history+was+ignored", location)
            self.assertIn("used+before", location)
            self.assertEqual(max(len(t["games"]) for t in app.tournament["teams"].values()), 2)
        finally:
            self.port = saved_port
            server.shutdown()
            server.server_close()

    def test_chooser_when_started_without_a_name(self):
        app = App()
        pages.register(app)
        server = serve(app, port=0, quiet=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            saved_port, self.port = self.port, server.server_address[1]
            status, location, _ = self.request("GET", "/")
            self.assertEqual((status, location), (303, "/open"))
            status, _, text = self.request("GET", "/open")
            self.assertEqual(status, 200)
            self.assertIn("webtest", text)          # the file the other test made
            status, location, _ = self.request("POST", "/open", form={"name": "bad/name"})
            self.assertIn("err=", location)
            status, location, _ = self.request("POST", "/open", form={"name": " Amelia 2026 "})
            self.assertEqual(location, "/?msg=Created+Amelia+2026")
            self.assertEqual(app.name, "Amelia 2026")
            self.assertTrue(os.path.isfile("Amelia 2026.p"))
            status, _, text = self.request("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("Switch tournament", text)
        finally:
            self.port = saved_port
            server.shutdown()
            server.server_close()

    def test_errors(self):
        status, _, _ = self.request("GET", "/nope")
        self.assertEqual(status, 404)
        status, _, text = self.request("GET", "/rounds/99")
        self.assertEqual(status, 400)
        self.assertIn("has not been drawn", text)
        status, location, _ = self.request("POST", "/teams/import", form={"text": "   "})
        self.assertEqual(status, 303)
        self.assertIn("err=", location)


if __name__ == "__main__":
    unittest.main()
