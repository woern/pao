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

Everything runs in the app. Before you start, check **Standings**: every
game must have a score and every tie a coin flip, or the groups cannot be
made.

1. Open **Day 2**. Set the number of groups and each group's size. The
   form suggests groups of 32 with the remainder in the last group; sizes
   of 8, 16, 32 or 64 give a clean bracket, anything else gives the top
   seeds a bye. Untick **consolation** for a group whose first-round losers
   do not play on. Check the preview, then **Create groups and brackets**.
2. Print **team lists by group** and post them.
3. Open each group, print its brackets, and post them. Courts are already
   drawn for the first round; use **shuffle courts** if you want a
   different set.
4. As results come in, type both scores into the match. The winner moves
   into the next round and, in the first round, the loser moves into the
   consolation bracket. Courts for the new matches are drawn on the spot.
   For a no-show, click the 13-7 arrow pointing at the team that turned up.
5. Reprint a bracket whenever you want to post an update. The Day 2
   overview shows each group's progress and champion.

Day 1 changes after the groups are made are flagged on the Day 2 page; if
they matter, delete the groups and create them again.

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

**A Day 2 result was entered wrongly.** Fix it on the match. Everything
that depended on it, including later scores, is cleared and drawn again.

**No court is free for a match.** Its court shows a question mark. Once
other games finish, click **shuffle courts** on that round.

**The app is down.** The command line works on the same file for Day 1:
`python3 pao.py <name>`, then `help`. Scores entered in the app are kept.
Day 2 has no command-line equivalent; restart the app.

---

## Backups

The entire tournament, scores included, is the single file `<name>.p` in
the `pao` folder. Copy it somewhere safe between rounds. Print views can be
saved as PDF from the print dialog if you want a record of what was posted.
