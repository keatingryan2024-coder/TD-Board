# Going live

Ten minutes, no cost, no server. GitHub hosts the page and runs the weekly job.

## 1. Make the repository

1. github.com → **New repository**. Name it whatever you like (`td-board` is fine).
   Public is required for free Pages. Don't add a README, you already have one.
2. Upload these files, keeping the folder structure:

```
index.html          the site
data.json           the current board (prices already in it)
update.py           weekly model rebuild
odds.py             price refresh
README.md           what the model is
DEPLOY.md           this file
.nojekyll           stops GitHub reformatting the site
.github/workflows/update.yml
```

The `.github` folder matters. If you drag files into the browser uploader it is
easy to lose it — check that **Actions → Update TD Board** appears afterwards.
If it doesn't, the workflow file didn't land in the right place.

## 2. Turn on the site

**Settings → Pages → Source: Deploy from a branch → main / (root) → Save.**

Give it a minute, then your board is at:

```
https://<your-username>.github.io/<repo-name>/
```

That link works on your phone. Add it to your home screen.

## 3. Let the job write back

**Settings → Actions → General → Workflow permissions → Read and write → Save.**

Without this the weekly refresh runs but can't commit, so the board never updates.

## 4. Optional: automatic prices

Free key at [the-odds-api.com](https://the-odds-api.com) (500 credits a month, no card).

**Settings → Secrets and variables → Actions → New repository secret**,
name `ODDS_API_KEY`, paste the key.

Skip this and everything still works — you just paste the sportsbook board in by
hand on the Picks tab instead.

## 5. Check it before Week 1

**Actions → Update TD Board → Run workflow.** Watch it finish green. The log tells
you how many players were priced and how many credits were used.

## What runs when

| When | What happens |
|---|---|
| Tuesday 12:00 UTC | Full rebuild: new stats, rosters, depth charts, lines |
| Wednesday 15:00 UTC (11am ET) | Prices only — for Wednesday night games |
| Thursday 15:00 UTC (11am ET) | Prices only — for Thursday night games |
| Sunday 13:00 UTC (9am ET) | Prices only — before the main slate |

About 64 credits a week against the free 500 a month.

A rebuild carries existing prices forward, so the Bets tab is never blank even if
the odds step is skipped.

## Season rollover

One edit a year: in `.github/workflows/update.yml`, change `python update.py 2026`
to the new season. The script handles the rest — it uses last season's stats until
the new one has games, then switches over on its own.

## If something looks wrong

- **Board looks stale** → Actions tab, check the last run. Red means read the log.
- **Prices are missing** → the odds step needs the secret, or props aren't posted
  yet. Paste them in manually; it takes a few seconds.
- **A player looks wrong** → click the card. The game log and the inputs behind
  the number are all there.

Not financial advice. The model is a tool, not a guarantee.
