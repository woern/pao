# Petanque America Open — Tournament Scheduler

A small command-line program that builds the round-by-round schedule for a
multi-round petanque tournament. You give it a list of teams and the court
numbers you have; it draws each round so that

- no two teams ever play each other twice,
- teams from the same group are never drawn against each other,
- no team plays the same court twice, and
- teams pushed onto the annex courts get first claim on the main field the
  following round.

Each round can then be exported as CSV: one file to print and post, one file
to type scores into.

---

## Requirements

- **Python 3.9 or newer.** Tested on 3.9 and 3.13.
- **No third-party packages.** Nothing to install, no virtualenv needed.

Check your Python before tournament day:

```
python3 --version
```

---

## Quick start

From the folder containing `pao.py`:

```
python3 pao.py amelia2025
```

That opens the tournament named `amelia2025`, creating `amelia2025.p` if it
does not exist. You will land at a prompt:

```
amelia2025 >>
```

Type `help` at any time for the command list, or `help zmake` for detail on a
single command. `quit` saves and exits.

A whole tournament looks like this:

```
amelia2025 >> cset a 1 90            main field is courts 1-90
amelia2025 >> cset b 91 104          annex is courts 91-104 (skip if none)
amelia2025 >> load teams.csv         import the team list
amelia2025 >> tlist                  eyeball the teams
amelia2025 >> zmake                  draw round 1
amelia2025 >> zmake                  draw round 2
amelia2025 >> zmake                  draw round 3
amelia2025 >> zmake                  draw round 4
amelia2025 >> zmake                  draw round 5
amelia2025 >> zexport 1              write round 1 to CSV
amelia2025 >> zexport 2
amelia2025 >> zexport 3
amelia2025 >> zexport 4
amelia2025 >> zexport 5
amelia2025 >> texport                write the team list to CSV
amelia2025 >> quit
```

Every command that changes something saves immediately, so a crash or a
closed laptop will not lose the draw.

---

## Concepts

**Tournament file.** All state lives in `<name>.p` in the current directory.
Copy that one file and you have copied the whole tournament. Files written by
earlier versions of this program still open.

**Team.** A number, a group, and a name. The number is what appears on the
printed sheets, and it is how you refer to the team in every command.

**Group.** A tag such as `FL`, `GA`, `TX`. Teams sharing a group are never
drawn against each other — the usual use is to stop teams from the same club
or region meeting in the early rounds. If you do not want this behavior, give
every team a different group, or the same group for none of them.

**Court sections.** Courts are split into two sections:

- **Section `a`** is the main field.
- **Section `b`** is the annex or overflow field — courts that are further
  away, or otherwise less desirable.

The draw fills section `a` first and only spills into section `b` when it runs
out. A team sent to the annex has its annex count raised, and in the next
round teams with a non-zero annex count are scheduled first, onto section `a`,
so nobody gets stuck out there twice running.

If you have only one field, set section `a` and leave `b` unused.

**Round.** `zmake` always builds the *next* round. It takes no round number.
To redraw a round, delete it with `zrem` and run `zmake` again.

**Bye.** If the team count is odd, the program adds a filler team named
`BYE-<n>` so everyone has an opponent. Whoever draws it has a bye. The filler
team is added to the tournament permanently and shows up in `tlist`. By
convention it is put in group `EU` — no real team should use that group, or
those teams could never draw the bye.

---

## Preparing the team list

`load` reads a CSV whose **first row is a header** and whose first three
columns are, in order:

| column | meaning | example |
| ------ | ------- | ------- |
| 1 | team number (whole number) | `12` |
| 2 | group | `FL` |
| 3 | team name | `Smith/Jones` |

Any further columns are ignored, so you can export a wide sheet with captain
names, emails and so on without trimming it first. See `sample-teams.csv` for
a working example.

Before importing, check that:

- team numbers are real numbers, not text — Excel and Sheets sometimes keep
  them as text after a paste;
- there are no blank rows or leftover junk rows in the middle;
- names have no `/` problems, stray blank spaces, or accented characters that
  your printing workflow cannot handle.

Rows without a numeric team number or without a name are skipped, and the
line numbers are reported so you can go fix them:

```
>> load teams.csv
Imported 178 teams from teams.csv
[WARN] Skipped 2 unusable row(s) on line(s): 96, 181
```

Importing is safe to repeat. Re-importing updates the group and name of teams
that already exist and keeps their schedule, so you can fix a spelling and
load again mid-tournament.

---

## Command reference

### Tournament

| command | what it does |
| ------- | ------------ |
| `use <name>` | Open a tournament, creating it if new |
| `info` | Summary: name, dates, courts, team and round counts |
| `info -v` | The above plus a full dump of the underlying data |
| `save` | Write to disk now (most commands already do) |
| `quit` / `exit` | Save and exit (Ctrl-D also works) |

### Teams

| command | what it does |
| ------- | ------------ |
| `load <file.csv>` | Import teams from CSV |
| `team <n> <group> <name>` | Add a team, or update an existing one |
| `tadd ...` | Same as `team` |
| `tlist` | List every team, its opponents so far and courts played |
| `tshow <n>` | One team's details and full schedule |
| `trem <n>` | Remove a team |
| `tannex <n> <count>` | Set how many times a team has played the annex |
| `texport` | Export all teams to CSV |

### Courts

| command | what it does |
| ------- | ------------ |
| `cset a <from> <to>` | Define the main field, e.g. `cset a 1 90` |
| `cset b <from> <to>` | Define the annex, e.g. `cset b 91 104` |
| `cset b 0 0` | Mark a section unused |
| `cusage [round]` | Which courts were used and which sat empty |

### Rounds

| command | what it does |
| ------- | ------------ |
| `zmake` | Draw the next round |
| `zmake -f` | Draw the next round ignoring court history (see below) |
| `zmake -d` | Draw and print each pairing as it is made |
| `zshow` | Print every round drawn so far |
| `zshow <round>` | Print one round |
| `zexport <round>` | Write a round to CSV for printing and scoring |
| `zrem` | Delete the most recent round |
| `zrem <round>` | Delete a specific round |
| `zclean` | Delete every round, keeping the teams |
| `gadd <n> <opp> <court>` | Add one game by hand |
| `gadd <n> <opp> <court> -s` | Record it for `<n>` only, not the opponent |

`ls teams` and `ls schedule` are shortcuts for `tlist` and `zshow`.

---

## Files the program writes

Everything is written to the directory you ran the program from.

| file | what it is |
| ---- | ---------- |
| `<name>.p` | The tournament itself. Back this up. |
| `<name>_round_<n>_<stamp>.csv` | Matchups for round `n`, for printing |
| `<name>_score_round_<n>_<stamp>.csv` | Blank score rows for round `n` |
| `<name>_teams_<stamp>.csv` | The full team list |

`<stamp>` is a timestamp, so exporting the same round twice never overwrites
the earlier file — the newest one is the one with the largest number.

The matchup file has one row per team, listing both sides of the game:

```
1,Diebold/Diebold,vs,7,Nguyen/Tran,court,1
7,Nguyen/Tran,vs,1,Diebold/Diebold,court,1
```

The score file has one row per *game*, with blanks for the two scores:

```
court,team,score,,opponent,score
1,1,0,,7,0
```

---

## Troubleshooting

**`Could not create a round after 3 attempts. Try zmake -f.`**

The draw is random and greedy, so on a tight board it can run out of legal
pairings and give up. Run `zmake -f`. The `-f` flag relaxes only the
court-history and annex rules — it will still never create a rematch or pair
two teams from the same group.

The usual cause is a small field with no court headroom. Because no team plays
the same court twice, every team needs a distinct court in each round, and the
draw needs spare courts to find one. Measured over 20 draws of five rounds:

| teams | games/round | courts = games | 1.5 × games |
| ----- | ----------- | -------------- | ----------- |
| 12 | 6 | 3.0 rounds | 4.6 rounds |
| 24 | 12 | 4.3 rounds | 5.0 rounds |
| 60 | 30 | 4.5 rounds | 5.0 rounds |
| 120 | 60 | 5.0 rounds | 5.0 rounds |
| 179 | 90 | 5.0 rounds | 5.0 rounds |

So for a **large field this rarely comes up** — 90 games on 90 courts draws
all five rounds. For a **small field, give the draw spare courts** (roughly
half again as many courts as games) or expect to fall back on `-f` in the
later rounds.

**Every round after the first fails, no matter how many times I try.**

This is the one situation `-f` is genuinely required, and it is caused by an
annex that is too big for the main field.

Teams that played the annex are never drawn against each other, so each one
needs a section `a` court of its own. If a round sends more teams to the annex
than there are section `a` courts, the next round is impossible — not
unlucky, impossible — and retrying will never help.

The rule is:

> **annex courts in use must be at most half of section `a`.**

Each annex court holds 2 teams, and each of those teams needs its own main
court next round. So 6 annex courts send 12 teams to the annex, and those 12
teams need 12 section `a` courts.

A worked failure: 20 teams (10 games) on `cset a 1 6` plus `cset b 7 20`. Six
games fit on the main field, four spill to the annex, and those 8 annexed
teams then need 8 main courts that do not exist. Widening the main field to
`cset a 1 8` fixes it outright.

The real tournament is nowhere near this limit — 84 main courts and 6 annex
courts sends 12 teams to the annex against 84 main courts. But if you ever
find yourself with a small main field and a large annex, widen the main field
rather than reaching for `-f`.

**`90 games need 90 courts, but only 50 are defined. Use cset.`**

You have more games than courts. Widen section `a`, or add an annex with
`cset b`.

**`No tournament open. Start one with use <name>.`**

You launched without a name and the default tournament has not been created
yet. Run `use <name>`.

**A team drops out mid-tournament.**

If rounds are already drawn, `trem` warns you that other teams still reference
the removed team, and their sheets will show `(removed team)`. Fix those games
by hand with `gadd`, or fix them on the printed sheets. Before the first round
it is cleaner to run `zclean`, fix the team list, and redraw.

**A team needs to be moved to a different court or opponent.**

Use `gadd` to append the corrected game, or `zrem` the round and redraw it.

**I want to start the draw over but keep the teams.**

`zclean`.

**The rounds do not look random enough.**

They are drawn fresh each time. `zrem` then `zmake` gives a different draw.

---

## How the draw works

For each round:

1. If the team count is odd, a `BYE-<n>` team is added.
2. Teams are split into those that have played the annex and those that have
   not.
3. Annex teams are drawn first, against non-annex teams, onto section `a`
   courts. This is what keeps annex duty from landing on the same teams twice.
4. Everyone else is drawn in random order.
5. For each team, the opponent is picked at random from teams that are not
   already scheduled this round, have not played this team before, and are not
   in the same group.
6. The court is picked at random from the free courts that neither team has
   played on, preferring section `a`.
7. If any team cannot be paired or seated, the whole round is discarded and
   retried, up to three times.

Because step 5 and 6 commit as they go, an unlucky ordering can leave the last
team with no legal opponent or court. That is what the retries and `-f` are
for.

---

## Tests

There is a test suite covering the scheduler invariants — the part that could
otherwise produce a subtly wrong tournament without anyone noticing. It uses
only the standard library, so it needs no setup:

```
python3 -m unittest discover
```

It runs in well under a second. Every test works in a temporary directory, so
it will not touch your tournament files.

What it guards:

- no rematches, no same-group pairings, no double-booked courts, and both
  teams' schedules always agree — checked across a sweep of field sizes and
  random seeds, including the real 179-team / 90-court configuration
- `-f` relaxes court history *only*, and never starts producing rematches
- an odd team count produces exactly one `BYE`, and only one across rounds
- annex teams are moved back to the main field the following round
- a failed draw leaves earlier rounds untouched
- CSV import: header skipped, BOM stripped, extra columns ignored, bad rows
  skipped and reported, re-import preserves existing schedules
- CSV export column layouts, which the Google Sheets workflow depends on
- tournament files written by the 2021–2024 versions still load
- every command has help text

If you change the scheduler, run this before the tournament, not during it.

---

## See also

`RUNBOOK.md` — the tournament-day procedure, including the Google Sheets
scoring and ranking workflow that sits around this program.
