#!/usr/bin/env python3
"""
TD Board — DraftKings anytime-touchdown odds.

Pulls the anytime-TD market from The Odds API (licensed feed that carries
DraftKings prices), matches each price to a player on the board, and writes
dk_odds / book_prob / edge into data.json. The site then fills the odds column
in automatically and shows where the model disagrees with the price.

    export ODDS_API_KEY=xxxx
    python odds.py                 # merge live odds into data.json
    python odds.py --selftest      # run the name matcher offline, no API key

Cost: the events list is free; each game's props cost 1 credit
(1 market x 1 region). A 16-game slate is ~16 credits. The free plan gives
500 credits a month, so twice-weekly refreshes use well under half of it.

Do not scrape sportsbook sites directly for this — it breaks their terms of
use and the endpoints are bot-protected. Use the licensed feed.
"""
import json, os, sys, time, unicodedata, urllib.parse, urllib.request

API = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
KEY = os.environ.get("ODDS_API_KEY", "").strip()
BOOK = os.environ.get("ODDS_BOOK", "draftkings").strip()
MARKET = "player_anytime_td"
TEAM_FULL = {"Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF","Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE","Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB","Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC","Los Angeles Chargers":"LAC","Los Angeles Rams":"LA","Las Vegas Raiders":"LV","Miami Dolphins":"MIA","Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG","New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","Seattle Seahawks":"SEA","San Francisco 49ers":"SF","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}

def norm(name):
    """Fold a player name to a comparable key: no accents, punctuation or suffix."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace(".", "").replace("'", "").replace("\u2019", "").replace("-", " ")
    parts = [p for p in s.split() if p and p not in SUFFIX]
    return " ".join(parts)

def initial_key(name):
    """First initial + last name, e.g. 'c mccaffrey' — catches 'C.J.' vs 'CJ' styles."""
    p = norm(name).split()
    return (p[0][0] + " " + p[-1]) if len(p) >= 2 else norm(name)

def tight_key(name):
    """Same letters, no spacing — catches 'St.Brown' vs 'St. Brown'."""
    return norm(name).replace(" ", "")

def build_index(players):
    """Map name keys -> player dicts, scoped later by team so matches stay honest."""
    exact, tight, loose = {}, {}, {}
    for p in players:
        exact.setdefault(norm(p["name"]), []).append(p)
        tight.setdefault(tight_key(p["name"]), []).append(p)
        loose.setdefault(initial_key(p["name"]), []).append(p)
    return exact, tight, loose

def match(book_name, team_pool, exact, tight, loose):
    """Resolve a book's player name to one board player, restricted to the two
    teams playing that game. Returns the player or None."""
    for table, key in ((exact, norm(book_name)), (tight, tight_key(book_name)),
                       (loose, initial_key(book_name))):
        hits = [p for p in table.get(key, []) if not team_pool or p["team"] in team_pool]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:            # same name, same game — refuse to guess
            return None
    return None

def american_to_prob(o):
    o = float(o)
    return (-o) / (-o + 100) if o < 0 else 100 / (o + 100)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "td-board"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r), dict(r.headers)

def fetch_and_merge(path="data.json"):
    if not KEY:
        print("No ODDS_API_KEY set — leaving data.json unchanged.")
        return 0
    data = json.load(open(path))
    players = data.get("players", [])
    exact, tight, loose = build_index(players)

    try:
        events, _ = get(f"{API}/events?apiKey={urllib.parse.quote(KEY)}")   # free call
    except Exception as e:
        print("Could not list events:", e)
        return 0
    print(f"{len(events)} scheduled games from the feed")

    matched = unmatched = 0
    misses, used, remaining = [], None, None
    for ev in events:
        pool = {TEAM_FULL.get(ev.get("home_team"), ""), TEAM_FULL.get(ev.get("away_team"), "")}
        pool.discard("")
        q = urllib.parse.urlencode({"apiKey": KEY, "regions": "us", "markets": MARKET,
                                    "oddsFormat": "american", "bookmakers": BOOK})
        try:
            odds, hdr = get(f"{API}/events/{ev['id']}/odds?{q}")
        except Exception as e:
            print(f"  {ev.get('away_team')} at {ev.get('home_team')}: no props ({e})")
            continue
        used = hdr.get("x-requests-used", used); remaining = hdr.get("x-requests-remaining", remaining)
        for bk in odds.get("bookmakers", []):
            if bk.get("key") != BOOK:
                continue
            for mk in bk.get("markets", []):
                if mk.get("key") != MARKET:
                    continue
                for out in mk.get("outcomes", []):
                    if str(out.get("name", "Yes")).lower() not in ("yes", "over"):
                        continue          # skip the "won't score" side
                    who = out.get("description") or out.get("participant") or ""
                    price = out.get("price")
                    if who == "" or price is None:
                        continue
                    p = match(who, pool, exact, tight, loose)
                    if p is None:
                        unmatched += 1; misses.append(f"{who} ({'/'.join(sorted(pool))})")
                        continue
                    bp = american_to_prob(price)
                    p["dk_odds"] = int(price)
                    p["book_prob"] = round(bp, 4)
                    p["edge"] = round(p.get("prob", 0) - bp, 4)
                    matched += 1
        time.sleep(0.25)

    data.setdefault("meta", {})["odds"] = {
        "book": BOOK, "market": MARKET, "matched": matched,
        "fetched": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    }
    json.dump(data, open(path, "w"), separators=(",", ":"))
    print(f"priced {matched} players, {unmatched} unmatched")
    if misses:
        print("  unmatched:", ", ".join(misses[:12]))
    if used:
        print(f"  credits used {used}, remaining {remaining}")
    return matched

def selftest():
    """Prove the matcher handles real-world name drift without touching the API."""
    board = [
        {"name": "Christian McCaffrey", "team": "SF", "prob": .6},
        {"name": "Ja'Marr Chase", "team": "CIN", "prob": .4},
        {"name": "Marvin Harrison Jr.", "team": "ARI", "prob": .3},
        {"name": "D.J. Moore", "team": "BUF", "prob": .3},
        {"name": "Amon-Ra St. Brown", "team": "DET", "prob": .45},
        {"name": "Kenneth Walker III", "team": "KC", "prob": .4},
        {"name": "Travis Etienne", "team": "NO", "prob": .34},
        {"name": "Michael Carter", "team": "ARI", "prob": .2},
        {"name": "Michael Carter", "team": "SF", "prob": .2},   # duplicate name trap
    ]
    exact, tight, loose = build_index(board)
    cases = [
        ("Christian McCaffrey", {"SF", "LA"}, "Christian McCaffrey"),
        ("C. McCaffrey",        {"SF", "LA"}, "Christian McCaffrey"),
        ("Ja'Marr Chase",       {"CIN", "TB"}, "Ja'Marr Chase"),
        ("JaMarr Chase",        {"CIN", "TB"}, "Ja'Marr Chase"),
        ("Marvin Harrison",     {"ARI", "LAC"}, "Marvin Harrison Jr."),
        ("Marvin Harrison Jr",  {"ARI", "LAC"}, "Marvin Harrison Jr."),
        ("DJ Moore",            {"BUF", "HOU"}, "D.J. Moore"),
        ("Amon-Ra St.Brown",    {"DET", "NO"}, "Amon-Ra St. Brown"),
        ("Kenneth Walker",      {"KC", "DEN"}, "Kenneth Walker III"),
        ("Travis Etienne Jr.",  {"NO", "DET"}, "Travis Etienne"),
        ("Christian McCaffrey", {"DAL", "NYG"}, None),   # right name, wrong game
        ("Michael Carter",      {"ARI", "SF"},  None),   # ambiguous, must refuse
        ("Some Practice Squader", {"SF", "LA"}, None),
    ]
    bad = 0
    for book_name, pool, want in cases:
        got = match(book_name, pool, exact, tight, loose)
        got_name = got["name"] if got else None
        ok = got_name == want
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {book_name:24s} -> {got_name}")
    print(("all matcher cases passed" if not bad else f"{bad} FAILED"))
    return bad

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(1 if selftest() else 0)
    fetch_and_merge()
