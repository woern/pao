# Tournament Day Runbook

The step-by-step procedure for running the Amelia Island Open, from preparing
the team list through posting the final rankings. The scheduler itself is
documented in `README.md`; this is the process around it.

Day 1 runs entirely in the web app. Day 2 still uses the Google Group
sheets for now; the app's printed rankings replace the Results workbook.

---

## 1. Prepare the team list

In the Google master sheet:

- Team names must contain **no `-`** and **no special characters** such as
  accents.
- Sanity check the names: no `/` problems, no stray blank spaces.

Copy the `ForCSV` sheet (select all, copy) or export it as CSV. The first
three columns must be **number, group, name**; anything after that is
ignored. Bad rows are skipped and reported, so this is worth doing but not
worth agonizing over.

---

## 2. Start the app

Double-click **Start PAO.command** in the `pao` folder (or, in a terminal,
`python3 -m paoweb` from that folder). A terminal window and a browser
window open; leave both open all day.

In the browser, type a name for this year's tournament, such as
`amelia2026`, and click **Create and open**. If the app was restarted, the
same page lists the tournament so you can reopen it. Then:

1. **Courts**: set the main field (for example 1 to 90) and the annex (91 to
   104, or 0 to 0 if there is none). Keep the annex to **at most half the
   size of the main field**, or later rounds become impossible to draw.
2. **Teams**: paste the team list into the box, or pick the CSV file, and
   click Import. Check the count. Re-importing is safe: it updates names and
   groups and keeps schedules.

Back up `<name>.p` from the `pao` directory to somewhere safe between
rounds. It is the whole tournament.

---

## 3. Each round

Do **one round at a time** as the day goes on, in case someone arrives late
or drops out.

1. **Rounds** > **Draw round N**. If the courts are too tight to give every
   team a fresh court, the round is still drawn and a notice lists the teams
   that repeat a court. That never creates a rematch. If it happens often,
   add courts.
2. Print the **court cards** and post them. Print the **score slips** and
   hand them to the courts if you use them.
3. As scores come in, open **enter scores** for the round and type them in.
   They save as you type; Enter moves to the next box. The page flags games
   with no score, half-entered games, and tied scores.
4. **No-show**: click the 13-7 button that points at the team that turned
   up. A **BYE** is scored 13-7 automatically.

---

## 4. Rankings

Open **Standings** at any time for the live table. Teams rank by wins,
then point differential, then points for over points against, then the sum
of their opponents' wins (Buchholz). Once every game of every round is
scored, any teams still tied on all four are listed with a coin-flip form:
flip the coin, enter the order, click Record.

Print the **rankings** and post them to the board and to Facebook.

---

## 5. Day 2

Day 2 is not in the app yet. Use the printed rankings from the app and the
Google Group sheets:

1. Split the rankings into groups of 32 by rank: A is ranks 1-32, B is
   33-64, and so on; the last group takes the remainder.

For each `Group-X`:

1. Open the `Group-X` sheet.
2. Copy/paste the teams and team numbers into the `Players` tab.
3. Print pages 1-3 and post to the board.

---

## Handling problems during the day

**A team is lost mid-day.** If it happens before the rounds are drawn,
remove the team on the **Teams** page and draw. If rounds are already
drawn, their opponents get a 13-7 walkover in later rounds (the no-show
button), or replace the games by hand on each **Round** page.

**A team is kicked out.** They are out for good.

**A player is sick.** Their teammate can play with 3 boules. They may also be
able to play the next day.

**A single game needs fixing.** On the round's page, open **Fix one game by
hand** and enter team, opponent and court. Both teams' games in that round
are replaced and their scores for it cleared.

**A whole round needs redrawing.** On **Rounds**, delete the round, then draw
again.

**The app is down.** The command line works on the same file: `python3
pao.py <name>`, then `help`. Scores entered in the app are kept.

---

## Backups

The entire tournament, scores included, is the single file `<name>.p` in
the `pao` folder. Copy it somewhere safe between rounds. Print views can be
saved as PDF from the print dialog if you want a record of what was posted.
