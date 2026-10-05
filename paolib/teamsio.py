"""Reading team lists.

The first three columns are, in order: team number, group, team name. Any
further columns are ignored.

Rows with neither a group nor a name are empty and ignored silently: the
ForCSV sheet numbers every row and builds names as "last/last", so its
unused rows arrive as a number, a blank group and a name of "/". A row with
a name but no group is a real team whose category was never filled in
(team 33 in 2024); it is imported with the placeholder group "-" and
reported so the director can fix it. Rows with a group but no name, or no
numeric team number, are skipped and reported.
"""

import csv
import io

from . import model

CSV_NUMBER = 0
CSV_GROUP = 1
CSV_NAME = 2

# Characters that do not make a name: a "/" on its own is an empty team.
SEPARATORS = " /\\-_.,;:\t"

# Group given to a team whose group cell was empty. The draw treats it as
# "no group": such teams may meet anyone, including each other.
NO_GROUP = "-"


def is_blank(text):
    return text.strip(SEPARATORS) == ""


def parse_teams(text, header="auto"):
    """Parse CSV or tab-separated text into ([(number, group, name)], skipped).

    `skipped` is a list of (line number, reason) for rows that were not
    imported. Rows with a name but no group are imported with group "-"
    and are not in `skipped`; see `ungrouped()`.

    header: True skips line 1, False keeps it, "auto" skips line 1 only when
    its first cell is not a number.
    """
    if text.startswith("﻿"):
        text = text[1:]
    delimiter = "\t" if "\t" in text and text.count("\t") >= text.count(",") else ","

    rows = []
    skipped = []
    for lineno, row in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
        if not any(cell.strip() for cell in row):
            continue

        if lineno == 1:
            first = row[0].strip() if row else ""
            if header is True or (header == "auto" and not first.isdigit()):
                continue

        number = row[CSV_NUMBER].strip() if row else ""
        group = row[CSV_GROUP].strip() if len(row) > CSV_GROUP else ""
        name = row[CSV_NAME].strip() if len(row) > CSV_NAME else ""

        if is_blank(group) and is_blank(name):
            continue   # an empty row, numbered or not

        if not number.isdigit():
            skipped.append((lineno, "team number %r is not a number" % number))
            continue
        if is_blank(name):
            skipped.append((lineno, "team %s has no name" % number))
            continue

        rows.append((int(number), NO_GROUP if is_blank(group) else group, name))

    return rows, skipped


def ungrouped(rows):
    """The (number, name) of parsed rows that arrived without a group."""
    return [(number, name) for number, group, name in rows if group == NO_GROUP]


def read_teams_file(path, header=True):
    # utf-8-sig strips the byte-order mark that Excel and Sheets add.
    with open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return parse_teams(handle.read(), header=header)


def import_teams(tournament, rows):
    """Add or update every parsed row. Returns (added, updated, rejected).

    `rejected` lists (number, reason) for rows the model refused, such as a
    team numbered the same as the BYE filler.
    """
    added = updated = 0
    rejected = []
    for number, group, name in rows:
        try:
            created, _ = model.add_team(tournament, number, group, name)
        except model.ModelError as exc:
            rejected.append((number, str(exc)))
            continue
        if created:
            added += 1
        else:
            updated += 1
    return added, updated, rejected


def format_skipped(skipped):
    shown = "; ".join("line %d: %s" % (lineno, reason) for lineno, reason in skipped[:10])
    more = "; ..." if len(skipped) > 10 else ""
    return "Skipped %d unusable row(s): %s%s" % (len(skipped), shown, more)


def format_ungrouped(rows):
    teams = ungrouped(rows)
    if not teams:
        return ""
    shown = ", ".join("%d %s" % (number, name) for number, name in teams[:10])
    more = ", ..." if len(teams) > 10 else ""
    return "%d team(s) have no group and were imported with '-': %s%s. Give them a group on the Teams page." % (
        len(teams), shown, more)
