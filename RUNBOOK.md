# Tournament Day Runbook

The step-by-step procedure for running the Amelia Island Open, from preparing
the team list through posting the final rankings. The scheduler itself is
documented in `README.md`; this is the process around it.

---

## 1. Prepare the master sheet

In the Google master sheet:

- Team names must contain **no `-`** and **no special characters** such as
  accents.
- Sanity check the names: no `/` problems, no stray blank spaces.

In the **Results** workbook:

- Delete the Round-X matchups and scores. The main sheet will then show `N/A`
  everywhere — that is expected.

In each **Game** sheet:

- Delete the data in the `Draw` tab.

---

## 2. Export the team list

1. Export the `ForCSV` sheet from Google Sheets.
2. In Excel, convert the team numbers into **actual numbers**, not text.
3. Remove empty rows and rows with bad data.
4. Save it as `teams.csv` in the tournament folder.

The importer skips unusable rows and tells you which line numbers they were
on, so this is worth doing but not worth agonizing over — `load` will report
anything it could not read.

---

## 3. Build the draw

From the `pao` directory:

```
python3 pao.py <tournament name>
```

Then, at the prompt:

```
>> cset a 1 90          set the courts you actually have
>> load teams.csv       import the teams
>> tlist                confirm the team count is right
>> texport              export the team list for the Results workbook

>> zmake                round 1
>> zmake                round 2
>> zmake                round 3
>> zmake                round 4
>> zmake                round 5

>> zexport 1
>> zexport 2
>> zexport 3
>> zexport 4
>> zexport 5

>> save
```

Notes:

- **`zmake` takes no round number.** It always builds the next round. Earlier
  versions of this runbook said `zmake 1 -f`; the number was silently ignored.
- **Only add `-f` if a `zmake` fails.** If you see
  `Could not create a round after 3 attempts`, run `zmake -f`. Using `-f`
  when you do not need it produces a worse draw, because it stops trying to
  give teams fresh courts. It never creates a rematch either way.
- If you have an annex field, set it too — `cset b 91 104` — so the program
  can keep annex duty from landing on the same teams twice. Keep the annex to
  **at most half the size of the main field**, or later rounds become
  impossible to draw; see the troubleshooting section of `README.md`.
- Each `zexport` writes two files per round: the matchups for printing, and
  the blank score rows for entry.

---

## 4. Day 1 in Google Sheets

Do **one game at a time** as the day goes on, in case someone arrives late or
drops out.

### Matchups

- Copy the game matchups into the sheets labeled `GAME 1` through `GAME 5`.
- Print the sheets that look like `g1-20 v2` for posting. You can print the
  whole workbook, but in the second screen select **pages 1-10**.

### Results

Open the **Results** workbook in Google Sheets.

1. In cell `B2`, enter the number of teams **+2**. If there are 178 teams,
   enter 180.
2. Copy/paste from the teams export into columns `B:C`. Delete any extra junk.
3. Go to the `Round-X` sheet and copy/paste from the score export into columns
   `A:F`. Delete any extra junk.

As scores come in, enter them into the `Round-X` sheet.

**For a BYE, score it 13-7.**

---

## 5. Day 2

In the Results sheet from Day 1, the `Rankings` tab is auto-populated.

1. Copy the `Rank`-`Team` columns and paste into **Final Rankings**.
2. If there are any rank ties, **flip a coin** for each to determine the final
   ranking. Write the result into column `K` (`Rank`).
3. Copy and paste `Rank` - `W` into **Ranking for Printing**.
4. Print, then post to the board and to Facebook.

For each `Group-X`:

1. Open the `Group-X` sheet.
2. Copy/paste the teams and team numbers into the `Players` tab.
3. Print pages 1-3 and post to the board.

---

## Handling problems during the day

**A team is lost mid-day.** Update the sheets manually. If it happens before
the rounds are drawn, it is cleaner to fix the team list and redraw:

```
>> zclean          clear all rounds, keep the teams
>> trem 42         remove the team
>> zmake           redraw
```

**A team is kicked out.** They are out for good.

**A player is sick.** Their teammate can play with 3 boules. They may also be
able to play the next day.

**A single game needs fixing.** Use `gadd <team> <opponent> <court>` to append
a corrected game rather than redrawing the whole round.

**A whole round needs redrawing.** `zrem` deletes the most recent round, then
`zmake` draws a fresh one.

---

## Backups

The entire tournament is the single file `<name>.p` in the tournament folder.
Copy it somewhere safe between rounds. The exported CSVs are timestamped and
never overwrite each other, so old exports remain available if you need to
compare against what was actually posted.
