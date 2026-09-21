"""Loading and saving tournament files.

The whole tournament is one pickle file, <name>.p, in the current
directory. Saves write a temporary file first and rename it into place, so
a crash mid-write never leaves a half-written tournament.
"""

import glob
import os
import pickle
import re
import tempfile

from . import model


class StoreError(Exception):
    """The file could not be read or written; the message says why."""


def tournament_path(name):
    return "./%s.p" % name


def exists(name):
    return os.path.isfile(tournament_path(name))


def load(name):
    path = tournament_path(name)
    try:
        with open(path, "rb") as handle:
            return model.migrate(pickle.load(handle))
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ValueError, TypeError) as exc:
        raise StoreError("Could not read %s: %s" % (path, exc))


def save(tournament):
    tournament["modified_at"] = model.utcnow()
    path = tournament_path(tournament["name"])
    directory = os.path.dirname(os.path.abspath(path))
    try:
        fd, tmp = tempfile.mkstemp(prefix=".%s." % tournament["name"], suffix=".tmp", dir=directory)
        with os.fdopen(fd, "wb") as handle:
            pickle.dump(tournament, handle)
        os.replace(tmp, path)
    except OSError as exc:
        raise StoreError("Could not save %s: %s" % (path, exc))
    return path


VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")


def clean_name(name):
    """Validate a tournament name typed by a person. Returns the name or raises."""
    name = (name or "").strip()
    if name.endswith(".p"):
        name = name[:-2].strip()
    if not name or not VALID_NAME.match(name):
        raise StoreError("Use letters, numbers, spaces, dashes or underscores for the tournament name.")
    return name


def list_tournaments():
    """[(name, teams, rounds, modified)] for every readable tournament file here."""
    found = []
    for filename in sorted(glob.glob("./*.p")):
        name = os.path.basename(filename)[:-2]
        try:
            tournament = load(name)
        except StoreError:
            continue
        teams = tournament["teams"]
        found.append((name, len(teams), max((len(t["games"]) for t in teams.values()), default=0),
                      tournament.get("modified_at")))
    found.sort(key=lambda row: row[3] or model.utcnow(), reverse=True)
    return found


def open_or_create(name):
    """Load the tournament, or create and save a new one. Returns (tournament, created)."""
    if exists(name):
        return load(name), False
    tournament = model.new_tournament(name)
    save(tournament)
    return tournament, True
