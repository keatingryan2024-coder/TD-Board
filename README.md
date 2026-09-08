# TD Board — NFL Anytime TD Model

A self-updating website that ranks the best anytime-touchdown bets each week, with
team offense/defense stats and an odds-vs-model edge finder.

## The model (backtested)

Built on the 2024 season, graded on all of 2025:

    score = 40% season hit rate  +  20% inside-10 volume  +  20% goal-line (inside-5) volume  +  20% Vegas team total
    prob  = calibrated probability the player scores a TD

- **Top-12 picks hit ~55%** in the backtest vs **~48%** for a naive "bet last year's TD leaders" baseline.
- **Rookies/no-data starters projected:** players with no 2025 stats who project to a starting role are estimated from their team's vacated red-zone volume + depth rank, flagged ROOKIE/PROJ and Low confidence.
- **Movers regressed:** players who changed teams have last year's numbers pulled 40% toward a positional baseline (the backtest showed the raw model over-rates them). Flagged LOW confidence.
- Recent-form (last-5) and defense matchup were tested and **left out of the score** — they
  hurt the top picks. They're shown as context chips only.
- Data: [nflverse](https://github.com/nflverse) (free). Red zone = inside-the-10 rush
  attempts + targets per game. Team totals derived from DraftKings spread + total.


## DraftKings odds (automatic)

`odds.py` pulls the anytime-touchdown market from [The Odds API](https://the-odds-api.com)
(a licensed feed that carries DraftKings prices) and writes each player's price,
the book's implied probability, and your edge into `data.json`. The board fills
the odds column in by itself and **Sort by edge** puts the biggest
model-vs-market disagreements on top.

**Setup (one time)**

1. Get a free key at the-odds-api.com — 500 credits a month, no card.
2. In your repo: **Settings → Secrets and variables → Actions → New repository secret**,
   name it `ODDS_API_KEY`, paste the key.
3. That's it. The workflow already reads it. Without the secret the board still
   builds; the odds column just stays empty for you to fill in by hand.

**Cost.** Listing games is free; each game's props cost 1 credit, so a 16-game
slate is about 16 credits. The workflow runs Tuesday (full rebuild) and Sunday
morning (prices only), which is roughly 130 credits a month against the free 500.

**Name matching.** Books write names differently ("C. McCaffrey", "Amon-Ra St.Brown",
"Travis Etienne Jr."). The matcher normalises accents, punctuation and suffixes, and
only matches within the two teams playing that game. If two players share a name it
refuses to guess rather than price the wrong man. Run `python odds.py --selftest`
to check the matcher without using any credits.

**A caution.** Don't scrape sportsbook sites directly for this. It breaks their terms
of use and the endpoints are bot-protected. The licensed feed is the right route.

## Files

- `index.html` — the site (3 tabs: TD Picks, Offense, Defense). Reads `data.json`.
- `data.json` — the current week's data. Rewritten by the updater.
- `update.py` — pulls fresh nflverse data, rebuilds `data.json`. Auto-detects preseason
  vs in-season.
- `.github/workflows/update.yml` — runs `update.py` every Tuesday.

## Deploy (one time)

1. Create a GitHub repo and add these files (keep the `.github/` folder).
2. **Settings → Pages** → deploy from `main`. That URL is your live site.
3. **Settings → Actions → General** → allow workflows to write (read/write permissions).
4. Done. The Action runs every Tuesday 12:00 UTC, pulls new data, and commits `data.json`.
   Run it by hand anytime from the **Actions** tab (`Update TD Board` → Run workflow).

Change the season in `update.yml` (`python update.py 2026`) once a year.

## Using the edge finder

On the TD Picks tab, type a player's DraftKings anytime-TD odds (e.g. `-160`) into the
odds box on his card. It shows the book's implied % and your **edge** = model % − book %.
Green edge means the model likes him more than the price. That gap is the bet.

*Not financial advice. Week 1 leans on prior-season data + preseason depth charts — confirm
the names you actually bet.*
