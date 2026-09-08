#!/usr/bin/env python3
"""
TD Board — weekly data builder (free, no API key).

Backtested model (built on 2024, graded on 2025):
    score = 0.40*season_hit_rate + 0.40*red_zone_volume + 0.20*vegas_team_total
    prob  = calibrated logistic of score  ->  P(scores a TD)
Top-12 picks hit ~55% in backtest vs ~48% for a naive baseline.

Modes (auto):
  PRESEASON  (current season has no games): stats/red-zone come from LAST season,
             team totals + matchups come from the CURRENT season's upcoming week.
  IN-SEASON: everything from the current season to date.

Usage: python update.py 2026      # current season
Writes data.json next to index.html. Run weekly via the GitHub Action.
"""
import io, sys, json, urllib.request
import numpy as np, pandas as pd

SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
BASE = "https://github.com/nflverse/nflverse-data/releases/download"
TEAM_FIX = {"AZ": "ARI"}
OUT_REASON = {"PUP":"PUP (out 4+ wks)","EXE":"exempt list","SUS":"suspended",
              "RES":"reserve/IR","RSR":"reserve/IR","RSN":"reserve","RLS":"released","DEV":"practice squad"}
# How the model's stated probability maps to what actually happened, measured on
# 10,616 out-of-sample player-weeks. The site uses this to turn a model % into a
# true % before comparing it with a price.
CALIBRATION_CURVE = [[10.3, 9.7], [19.2, 22.3], [29.4, 33.5],
                     [39.6, 38.0], [49.8, 43.2], [62.1, 58.3]]
CONF_PENALTY = {"High": 0.0, "Medium": -2.0, "Low": -5.0}   # bet-score points

# Extra prop markets off the same score. Fitted on one season, graded on the next:
#   2+ TDs   top bucket predicted 9.5% / actual 10.0%   top-12 19.9% vs 17.1% baseline
#   first TD top bucket predicted 10.6% / actual 10.1%  top-12 17.6% vs 13.0% baseline
MARKETS = {
    "anytime":  None,                                  # uses CALIB_POS
    "first_td": {"b0": -4.281, "b1": 3.619},
    "two_plus": {"b0": -4.887, "b1": 4.390},
}
MATCHUP_WEIGHT = 25.0        # points per unit of the offence-vs-defence index

# 2026 NFL Preseason team totals, sourced footballdb.com, snapshot 2026-09-03.
# Format: team -> [games, rush_yds, rush_ypg, pass_yds, pass_ypg, tot_yds, tot_ypg, pts_pg]
PRE_OFF = {
"ARI":[4,600,150.0,1010,252.5,1610,402.5,27.0],"CHI":[3,275,91.7,875,291.7,1150,383.3,22.3],
"BAL":[3,395,131.7,743,247.7,1138,379.3,26.0],"DAL":[3,403,134.3,676,225.3,1079,359.7,25.0],
"BUF":[3,378,126.0,652,217.3,1030,343.3,29.3],"LA":[3,392,130.7,632,210.7,1024,341.3,24.7],
"CIN":[3,372,124.0,650,216.7,1022,340.7,24.3],"LAC":[3,376,125.3,626,208.7,1002,334.0,20.7],
"DEN":[3,333,111.0,663,221.0,996,332.0,24.7],"NYG":[3,377,125.7,615,205.0,992,330.7,19.7],
"LV":[3,375,125.0,593,197.7,968,322.7,16.0],"CAR":[4,448,112.0,804,201.0,1252,313.0,24.2],
"NE":[3,337,112.3,602,200.7,939,313.0,16.7],"ATL":[3,263,87.7,669,223.0,932,310.7,19.3],
"SF":[3,376,125.3,548,182.7,924,308.0,24.0],"DET":[3,484,161.3,425,141.7,909,303.0,18.7],
"KC":[3,384,128.0,517,172.3,901,300.3,12.0],"NO":[3,330,110.0,566,188.7,896,298.7,15.7],
"CLE":[3,358,119.3,529,176.3,887,295.7,18.0],"PIT":[3,267,89.0,592,197.3,859,286.3,18.3],
"JAX":[3,284,94.7,558,186.0,842,280.7,20.0],"TEN":[3,380,126.7,435,145.0,815,271.7,17.7],
"MIN":[3,265,88.3,541,180.3,806,268.7,7.3],"WAS":[3,284,94.7,470,156.7,754,251.3,12.0],
"IND":[3,252,84.0,496,165.3,748,249.3,11.7],"GB":[3,264,88.0,477,159.0,741,247.0,28.0],
"NYJ":[3,224,74.7,487,162.3,711,237.0,13.0],"SEA":[3,278,92.7,395,131.7,673,224.3,10.7],
"PHI":[3,236,78.7,434,144.7,670,223.3,13.7],"HOU":[3,270,90.0,331,110.3,601,200.3,13.3],
"TB":[3,224,74.7,350,116.7,574,191.3,13.3],"MIA":[3,245,81.7,319,106.3,564,188.0,7.3],
}
# defense: yards ALLOWED
PRE_DEF = {
"NYG":[3,232,77.3,247,82.3,479,159.7,7.3],"BUF":[3,242,80.7,385,128.3,627,209.0,16.0],
"BAL":[3,216,72.0,419,139.7,635,211.7,4.3],"PIT":[3,214,71.3,500,166.7,714,238.0,18.0],
"DET":[3,166,55.3,562,187.3,728,242.7,15.0],"JAX":[3,259,86.3,490,163.3,749,249.7,18.0],
"ATL":[3,325,108.3,434,144.7,759,253.0,15.0],"SF":[3,348,116.0,411,137.0,759,253.0,16.0],
"DEN":[3,266,88.7,494,164.7,760,253.3,15.3],"TB":[3,281,93.7,486,162.0,767,255.7,16.7],
"CIN":[3,285,95.0,521,173.7,806,268.7,12.0],"DAL":[3,411,137.0,396,132.0,807,269.0,15.7],
"LAC":[3,405,135.0,423,141.0,828,276.0,22.7],"KC":[3,246,82.0,583,194.3,829,276.3,15.0],
"MIN":[3,229,76.3,626,208.7,855,285.0,19.0],"LV":[3,380,126.7,488,162.7,868,289.3,21.7],
"NYJ":[3,341,113.7,547,182.3,888,296.0,15.7],"CHI":[3,257,85.7,662,220.7,919,306.3,17.3],
"WAS":[3,481,160.3,480,160.0,961,320.3,21.7],"SEA":[3,420,140.0,548,182.7,968,322.7,15.0],
"TEN":[3,308,102.7,663,221.0,971,323.7,17.7],"CAR":[4,455,113.8,857,214.2,1312,328.0,22.2],
"LA":[3,434,144.7,567,189.0,1001,333.7,10.0],"MIA":[3,347,115.7,656,218.7,1003,334.3,21.0],
"NO":[3,360,120.0,648,216.0,1008,336.0,27.3],"NE":[3,389,129.7,646,215.3,1035,345.0,23.7],
"ARI":[4,502,125.5,888,222.0,1390,347.5,30.8],"HOU":[3,362,120.7,705,235.0,1067,355.7,21.7],
"CLE":[3,334,111.3,740,246.7,1074,358.0,26.0],"IND":[3,433,144.3,659,219.7,1092,364.0,24.0],
"GB":[3,308,102.7,794,264.7,1102,367.3,26.3],"PHI":[3,493,164.3,755,251.7,1248,416.0,27.3],
}
PRE_SNAPSHOT_DATE = "2026-09-03"
# ^ 2026 preseason team totals, footballdb.com. No official feed exists for
# preseason games (nflverse tracks REG/playoffs only), so this is a one-time
# manual snapshot rather than something the weekly job can refresh. It stays
# out of the score -- there is no way to grade whether preseason predicted
# anything, because the season it would predict has not happened yet.

CALIB_POS = {  # per-position score->P(TD), fitted on 2025
    "RB": {"b0": -2.861, "b1": 4.096}, "WR": {"b0": -2.956, "b1": 4.755},
    "TE": {"b0": -2.858, "b1": 4.930}, "QB": {"b0": -2.999, "b1": 4.421},
}
CALIB = {"b0": -2.816, "b1": 4.229}          # fallback (all positions)
W_SEASON, W_TT, W_RZ10, W_RZ5, W_YDS = 0.32, 0.16, 0.16, 0.16, 0.20
WK1_PAIRS = [("NE","SEA"),("SF","LA"),("CHI","CAR"),("TB","CIN"),("NO","DET"),("BUF","HOU"),
             ("BAL","IND"),("CLE","JAX"),("ATL","PIT"),("NYJ","TEN"),("ARI","LAC"),("MIA","LV"),
             ("GB","MIN"),("WAS","PHI"),("DAL","NYG"),("DEN","KC")]

def url(p): return f"{BASE}/{p}"
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"}), timeout=180).read()
def load(u): return pd.read_csv(io.BytesIO(get(u)), low_memory=False)
def try_load(u):
    try: return load(u)
    except Exception as e: print("skip:", u.split('/')[-1], e); return None

def stats_for(season):
    for p in (f"stats_player/stats_player_week_{season}.csv", f"player_stats/stats_player_week_{season}.csv"):
        d = try_load(url(p))
        if d is not None: return d
    return None

def redzone_pg(season, games_by_pid):
    """inside-10 and inside-5 (goal line) touches per game, per player, for a season."""
    cols = ["season_type","yardline_100","rush_attempt","pass_attempt","rusher_player_id","receiver_player_id"]
    d = try_load(url(f"pbp/play_by_play_{season}.csv"))
    if d is None: return {}, {}
    d = d[d.season_type=="REG"]
    def per(line):
        z = d[d.yardline_100<=line]
        r = z[z.rush_attempt==1][["rusher_player_id"]].rename(columns={"rusher_player_id":"pid"})
        p = z[z.pass_attempt==1][["receiver_player_id"]].rename(columns={"receiver_player_id":"pid"})
        tot = pd.concat([r,p]).dropna().groupby("pid").size()
        return {pid: round(tot.get(pid,0)/max(games_by_pid.get(pid,1),1), 3) for pid in games_by_pid}
    return per(10), per(5)

def role_of(pos, rank):
    if pd.isna(rank): return ""
    rank=int(rank)
    return {"QB":"" if rank==1 else f"QB{rank}","RB":"" if rank==1 else f"RB{rank}",
            "TE":"" if rank==1 else f"TE{rank}","WR":"" if rank<=3 else f"WR{rank}"}.get(pos,"")

def carry_prices(path="data.json"):
    """Keep any prices already on the board so a rebuild never blanks the Bets tab.
    odds.py overwrites these whenever it can reach the feed."""
    try:
        old = json.load(open(path))
    except Exception:
        return {}, {}
    keep = {p["name"]: {k: p[k] for k in ("dk_odds", "book_prob", "edge") if k in p}
            for p in old.get("players", []) if "dk_odds" in p}
    meta = old.get("meta", {})
    return keep, {"odds": meta.get("odds"), "book_bias": meta.get("book_bias")}

def build():
    prior_prices, prior_meta = carry_prices()
    cur = stats_for(SEASON); cur_reg = cur[cur.season_type=="REG"] if cur is not None else None
    in_season = cur_reg is not None and len(cur_reg) > 0
    stat_season = SEASON if in_season else SEASON-1
    print(f"mode: {'IN-SEASON' if in_season else 'PRESEASON'} | stats {stat_season} | lines {SEASON}")

    df = stats_for(stat_season)
    df = df[df.season_type=="REG"].copy()
    df["team"]=df.team.replace(TEAM_FIX); df["opponent_team"]=df.opponent_team.replace(TEAM_FIX)
    df["position"]=df.position.replace({"FB":"RB"}); df=df[df.position.isin(["RB","WR","TE","QB"])].copy()
    for c in ["passing_yards","rushing_yards","receiving_yards","passing_tds","rushing_tds","receiving_tds"]: df[c]=df[c].fillna(0)
    df["any_td"]=df.rushing_tds+df.receiving_tds

    games_by_pid = df.groupby("player_id").week.nunique().to_dict()
    rz10_pg, rz5_pg = redzone_pg(stat_season, games_by_pid)
    df["yds"] = df.rushing_yards + df.receiving_yards
    yds_tot = df.groupby("player_id").yds.sum().to_dict()
    yds_pg = {pid: round(yds_tot.get(pid, 0) / max(games_by_pid.get(pid, 1), 1), 1) for pid in games_by_pid}

    # schedule: upcoming week in SEASON -> team totals + opponents
    sch = load(url("schedules/games.csv"))
    ssn = sch[(sch.season==SEASON) & (sch.game_type=="REG")].copy()
    unplayed = ssn[ssn.home_score.isna()] if "home_score" in ssn else ssn
    up_week = int(unplayed.week.min()) if len(unplayed) else int(ssn.week.max())
    wk = ssn[ssn.week==up_week]
    itt, next_opp, gline, games = {}, {}, {}, []
    for x in wk.itertuples():
        if not pd.isna(x.total_line):
            sp = x.spread_line if not pd.isna(x.spread_line) else 0
            itt[TEAM_FIX.get(x.home_team,x.home_team)] = round(x.total_line/2 + sp/2, 1)
            itt[TEAM_FIX.get(x.away_team,x.away_team)] = round(x.total_line/2 - sp/2, 1)
        h=TEAM_FIX.get(x.home_team,x.home_team); a=TEAM_FIX.get(x.away_team,x.away_team)
        next_opp[h]=a; next_opp[a]=h
        if not pd.isna(x.total_line):
            sp=x.spread_line if not pd.isna(x.spread_line) else 0
            gline[h]=(float(x.total_line), -float(sp)); gline[a]=(float(x.total_line), float(sp))
        games.append(dict(home=h, away=a,
            ou=(float(x.total_line) if not pd.isna(x.total_line) else None),
            spread_home=(-float(x.spread_line) if not pd.isna(x.spread_line) else None),
            day=str(getattr(x,"gameday","")), wd=str(getattr(x,"weekday",""))))
    if not next_opp:
        for a,b in WK1_PAIRS: next_opp[a]=b; next_opp[b]=a
    print(f"upcoming: {SEASON} week {up_week} | {len(itt)} team totals")

    # matchup context (not scored)
    dvp=df.groupby(["opponent_team","position"]).agg(t=("any_td","sum"),w=("week","nunique")).reset_index()
    dvp["pg"]=(dvp.t/dvp.w).round(3); lg=dvp.groupby("position").pg.mean().round(3).to_dict()
    dvp["idx"]=dvp.apply(lambda r:round(r.pg/lg[r.position],3) if lg[r.position] else 1.0,axis=1)
    dvp["soft_rank"]=dvp.groupby("position").pg.rank(ascending=False,method="min").astype(int)
    matchup={}
    for r in dvp.itertuples(): matchup.setdefault(r.opponent_team,{})[r.position]={"allowed_pg":r.pg,"idx":r.idx,"soft_rank":int(r.soft_rank)}

    # per-team per-position tables
    STAT=["rushing_yards","receiving_yards","passing_yards","rushing_tds","receiving_tds","passing_tds","any_td"]
    SH={"rushing_yards":"ruY","receiving_yards":"reY","passing_yards":"paY","rushing_tds":"ruT","receiving_tds":"reT","passing_tds":"paT","any_td":"aTD"}
    def pack(g): return {SH[s]:int(round(g[s])) for s in STAT}
    def sidew(col):
        G=df.groupby(col).week.nunique().to_dict(); tot=df.groupby(col)[STAT].sum(); pos=df.groupby([col,"position"])[STAT].sum(); o={}
        for t in G:
            rec={"G":int(G[t]),"total":pack(tot.loc[t]),"pos":{}}
            for pp in ["RB","WR","TE","QB"]: rec["pos"][pp]=pack(pos.loc[(t,pp)]) if (t,pp) in pos.index else {v:0 for v in SH.values()}
            o[t]=rec
        return o
    teams={t:{"off":sidew("team")[t],"def":sidew("opponent_team")[t]} for t in sidew("team")}
    PRE_KEYS=["G","ruY","ruYpg","paY","paYpg","totY","totYpg","ptsPg"]
    for t in teams:
        if t in PRE_OFF: teams[t]["pre_off"]=dict(zip(PRE_KEYS,PRE_OFF[t]))
        if t in PRE_DEF: teams[t]["pre_def"]=dict(zip(PRE_KEYS,PRE_DEF[t]))

    # Matchup lens: own offense in a phase x opponent defense allowing it, indexed to league
    # average. Shown for judgement only, NOT in the score -- backtests on 2024 and 2025 showed
    # every weighted version made the top picks worse, because the Vegas team total already
    # prices most of it (r = .47 run, .57 pass).
    _G = 17.0
    def _ix(m):
        avg = (sum(m.values())/len(m)) if m else 1.0
        return {k: (v/avg if avg else 1.0) for k, v in m.items()}
    o_run = _ix({t: teams[t]["off"]["pos"]["RB"]["ruY"]/_G for t in teams})
    d_run = _ix({t: teams[t]["def"]["pos"]["RB"]["ruY"]/_G for t in teams})
    o_pass= _ix({t: (teams[t]["off"]["pos"]["WR"]["reY"]+teams[t]["off"]["pos"]["TE"]["reY"])/_G for t in teams})
    d_pass= _ix({t: (teams[t]["def"]["pos"]["WR"]["reY"]+teams[t]["def"]["pos"]["TE"]["reY"])/_G for t in teams})

    # rosters + depth overlay
    ros=try_load(url(f"rosters/roster_{SEASON}.csv"))
    if ros is not None:
        ros["team"]=ros.team.replace(TEAM_FIX); ros=ros[["gsis_id","team","status"]].rename(columns={"gsis_id":"player_id","team":"cur_team"})
    dc=try_load(url(f"depth_charts/depth_charts_{SEASON}.csv")); dcrank=None
    if dc is not None and "pos_rank" in dc:
        dc=dc[dc.pos_abb.isin(["QB","RB","WR","TE","FB"])].copy(); dc["dt"]=pd.to_datetime(dc.get("dt"),errors="coerce")
        dcrank=dc.sort_values("dt").groupby("gsis_id").tail(1)[["gsis_id","pos_rank"]].rename(columns={"gsis_id":"player_id"})

    # positional means for mover regression (qualifying pool)
    q=df.groupby("player_id").agg(g=("week","nunique"),tdg=("any_td",lambda s:(s>0).sum()),pos=("position","first"))
    q=q[q.g>=6].copy(); q["hit"]=q.tdg/q.g; q["rz10"]=[rz10_pg.get(i,0.0) for i in q.index]; q["rz5"]=[rz5_pg.get(i,0.0) for i in q.index]; q["yds"]=[yds_pg.get(i,0.0) for i in q.index]
    posmean_hit=q.groupby("pos").hit.mean().to_dict(); posmean_rz10=q.groupby("pos").rz10.mean().to_dict()
    posmean_rz5=q.groupby("pos").rz5.mean().to_dict(); posmean_yds=q.groupby("pos").yds.mean().to_dict()
    MOVE_K=0.4
    sig=lambda x:1/(1+np.exp(-x))
    players=[]
    for pid,sub in df.sort_values("week").groupby("player_id"):
        sub=sub.sort_values("week"); g=sub.week.nunique()
        if g<6: continue
        tds=int(sub.any_td.sum())
        if tds<3: continue
        tp=sub.team.iloc[-1]; l5=sub.tail(5); pos=sub.position.iloc[-1]
        rostered,cur=True,tp
        if ros is not None:
            hit=ros[ros.player_id==pid]; onroster=len(hit)>0
            status=hit.status.iloc[0] if onroster else None
            cur=hit.cur_team.iloc[0] if onroster else tp
            rostered=(status=="ACT")
        rank=None
        if dcrank is not None:
            h=dcrank[dcrank.player_id==pid]; rank=int(h.pos_rank.iloc[0]) if len(h) else None
        moved=bool(ros is not None and rostered and tp!=cur)
        out_reason=("" if (ros is None or rostered) else (OUT_REASON.get(status,"not active") if onroster else "not on 53-man"))
        gw=[int(x) for x in sub.week.tolist()]; gt=[int(x) for x in sub.any_td.tolist()]
        go=[str(x) for x in sub.opponent_team.tolist()]
        cpts=2; cnote=[]
        if not rostered: cpts=-9
        if moved: cpts-=2; cnote.append("new team")
        if rank and rank>=3: cpts-=2; cnote.append("buried on depth chart")
        elif rank==2: cpts-=1; cnote.append("backup/committee")
        if g<10: cpts-=1; cnote.append("small sample ("+str(g)+" g)")
        conf=("High" if cpts>=2 else ("Medium" if cpts>=1 else "Low"))
        season_hit=round(int((sub.any_td>0).sum())/g,3)
        rz10=rz10_pg.get(pid,0.0); rz5=rz5_pg.get(pid,0.0); ypg=yds_pg.get(pid,0.0)
        team_itt=itt.get(cur) if rostered else None
        eff_hit,eff_10,eff_5,eff_y=season_hit,rz10,rz5,ypg
        if moved:
            eff_hit=(1-MOVE_K)*season_hit+MOVE_K*posmean_hit.get(pos,season_hit)
            eff_10=(1-MOVE_K)*rz10+MOVE_K*posmean_rz10.get(pos,rz10)
            eff_5=(1-MOVE_K)*rz5+MOVE_K*posmean_rz5.get(pos,rz5)
            eff_y=(1-MOVE_K)*ypg+MOVE_K*posmean_yds.get(pos,ypg)
        rz10N=min(eff_10/2.5,1.0); rz5N=min(eff_5/1.2,1.0); ydN=min(eff_y/90.0,1.0)
        ittN=(min(max((team_itt-15)/13,0),1) if team_itt is not None else 0.5)
        s01=W_SEASON*eff_hit+W_TT*ittN+W_RZ10*rz10N+W_RZ5*rz5N+W_YDS*ydN
        gl=gline.get(cur,(None,None)) if rostered else (None,None)
        players.append(dict(name=sub.player_display_name.iloc[-1],pos=pos,team=cur,team_prev=(tp if moved else ""),
            moved=moved,rostered=rostered,rank=rank,role=role_of(pos,rank),
            games=int(g),td_games=int((sub.any_td>0).sum()),tds=tds,season_hit=season_hit,
            l5_hit=round(float((l5.any_td>0).mean()),3),l5_gp=int(len(l5)),l5_hits=int((l5.any_td>0).sum()),
            rz_pg=rz10,gl_pg=rz5,yds_pg=ypg,eff_hit=round(eff_hit,3),eff_rz10=round(eff_10,3),eff_rz5=round(eff_5,3),eff_yds=round(eff_y,1),itt=team_itt,score=round(s01*100),prob=round(float(sig((CALIB_POS.get(pos,CALIB))["b0"]+(CALIB_POS.get(pos,CALIB))["b1"]*s01)),3),
            prob_first=round(float(sig(MARKETS["first_td"]["b0"]+MARKETS["first_td"]["b1"]*s01)),4),
            prob_two=round(float(sig(MARKETS["two_plus"]["b0"]+MARKETS["two_plus"]["b1"]*s01)),4),
            conf=conf,conf_note=", ".join(cnote),out_reason=out_reason,gw=gw,gt=gt,go=go,
            ou=gl[0],spread=gl[1],regressed=bool(moved),
            next_opp=(next_opp.get(cur,"") if rostered else "")))
    # --- Rookie / no-2025-data projected starters (role-based projection) ---
    try:
        have=set(df.player_id.unique())
        pinfo=df.groupby("player_id").agg(pos=("position","first"),team=("team","last"))
        pool10,pool5={},{}
        for pid in games_by_pid:
            if pid in pinfo.index:
                key=(pinfo.loc[pid,"team"],pinfo.loc[pid,"pos"])
                pool10[key]=pool10.get(key,0)+rz10_pg.get(pid,0)*games_by_pid[pid]
                pool5[key]=pool5.get(key,0)+rz5_pg.get(pid,0)*games_by_pid[pid]
        pool10={k:v/17 for k,v in pool10.items()}; pool5={k:v/17 for k,v in pool5.items()}
        rosf=try_load(url(f"rosters/roster_{SEASON}.csv"))
        dca=try_load(url(f"depth_charts/depth_charts_{SEASON}.csv"))
        if rosf is not None and dca is not None:
            rosf["team"]=rosf.team.replace(TEAM_FIX)
            expmap=rosf.set_index("gsis_id").years_exp.to_dict(); nmmap=rosf.set_index("gsis_id").full_name.to_dict()
            teammap=rosf.set_index("gsis_id").team.to_dict()
            dca=dca[dca.pos_abb.isin(["QB","RB","WR","TE"])].copy(); dca["dt"]=pd.to_datetime(dca.get("dt"),errors="coerce")
            latest=dca.sort_values("dt").groupby("gsis_id").tail(1)
            SHARE={("RB",1):0.55,("RB",2):0.28,("WR",1):0.30,("WR",2):0.24,("WR",3):0.16,("TE",1):0.65,("QB",1):0.85}
            BASE_HIT={("RB",1):0.45,("RB",2):0.28,("WR",1):0.33,("WR",2):0.24,("WR",3):0.16,("TE",1):0.24,("QB",1):0.30}
            THR={"RB":2,"WR":3,"TE":1,"QB":1}
            for r in latest.itertuples():
                pid=r.gsis_id; pos=r.pos_abb; rank=int(r.pos_rank)
                stt=rosf[rosf.gsis_id==pid]
                if len(stt) and stt.status.iloc[0]!="ACT": continue
                if pid in have or rank>THR.get(pos,1): continue
                team=teammap.get(pid,getattr(r,"team",None))
                if team is None or team not in itt and not rostered: pass
                share=SHARE.get((pos,rank),0.1)
                rz10p=round(pool10.get((team,pos),0.4)*share,3); rz5p=round(pool5.get((team,pos),0.2)*share,3)
                bh=BASE_HIT.get((pos,rank),0.25); team_itt=itt.get(team)
                ypj=round(posmean_yds.get(pos,40.0)*(share/0.3),1)
                rz10N=min(rz10p/2.5,1); rz5N=min(rz5p/1.2,1); ydN=min(ypj/90.0,1)
                ittN=(min(max((team_itt-15)/13,0),1) if team_itt is not None else 0.5)
                s01=W_SEASON*bh+W_TT*ittN+W_RZ10*rz10N+W_RZ5*rz5N+W_YDS*ydN
                cc=CALIB_POS.get(pos,CALIB); gl=gline.get(team,(None,None))
                rookie=(expmap.get(pid,1)==0)
                players.append(dict(name=nmmap.get(pid,"?"),pos=pos,team=team,team_prev="",moved=False,
                    rostered=True,rank=rank,role=("" if (pos in("RB","QB","TE") and rank==1) or (pos=="WR" and rank<=3) else f"{pos}{rank}"),
                    games=0,td_games=0,tds=0,season_hit=bh,l5_hit=0.0,l5_gp=0,l5_hits=0,
                    rz_pg=rz10p,gl_pg=rz5p,yds_pg=ypj,eff_hit=round(bh,3),eff_rz10=rz10p,eff_rz5=rz5p,eff_yds=ypj,itt=team_itt,
                    score=round(s01*100),prob=round(float(sig(cc["b0"]+cc["b1"]*s01)),3),
                    conf="Low",conf_note=("rookie · role projection" if rookie else "no 2025 data · role projection"),
                    prob_first=round(float(sig(MARKETS["first_td"]["b0"]+MARKETS["first_td"]["b1"]*s01)),4),
                    prob_two=round(float(sig(MARKETS["two_plus"]["b0"]+MARKETS["two_plus"]["b1"]*s01)),4),
                    projected=True,out_reason="",gw=[],gt=[],go=[],ou=gl[0],spread=gl[1],
                    next_opp=next_opp.get(team,"")))
            print(f"projected starters added: {sum(1 for p in players if p.get('projected'))}")
    except Exception as e:
        print("projection step skipped:",e)

    for p in players:
        opp = p.get("next_opp") or ""
        phase = "run" if p["pos"] == "RB" else "pass"
        O, D = (o_run, d_run) if phase == "run" else (o_pass, d_pass)
        off_i, def_i = O.get(p["team"]), D.get(opp)
        if off_i is None or def_i is None:
            p["mu_phase"], p["mu_off"], p["mu_def"], p["mu"] = phase, None, None, None
        else:
            p["mu_phase"], p["mu_off"], p["mu_def"] = phase, round(off_i,3), round(def_i,3)
            p["mu"] = round(off_i*def_i, 3)
    _vals = sorted([p["mu"] for p in players if p.get("mu") is not None], reverse=True)
    for p in players:
        p["mu_rank"] = (_vals.index(p["mu"])+1) if p.get("mu") is not None else None

    if prior_prices:
        n = 0
        for p in players:
            keep = prior_prices.get(p["name"])
            if keep:
                p.update(keep); n += 1
        print(f"carried {n} existing prices into the rebuild")

    players.sort(key=lambda p:(p["score"],p["prob"]),reverse=True)

    out=dict(meta=dict(season=stat_season,predict_week=f"{SEASON} Week {up_week}",
        source=f"nflverse: {stat_season} stats+pbp + {SEASON} rosters/lines",
        generated=pd.Timestamp.now("UTC").strftime("updated %Y-%m-%d %H:%M UTC"),
        weights=dict(season=int(W_SEASON*100),team_total=int(W_TT*100),red_zone_10=int(W_RZ10*100),goal_line_5=int(W_RZ5*100),yardage=int(W_YDS*100)),
        calib=CALIB,calib_pos=CALIB_POS, backtest=dict(top5_hit=0.567,top12_hit=0.537,top24_hit=0.475,baseline_top12=0.477,
                      val2024=0.546,val2024_base=0.514,weeks=18,graded=5365,base_rate=0.191,
                      note="current weights, trained on the prior season, graded out-of-sample"),
        calibration_curve=CALIBRATION_CURVE, conf_penalty=CONF_PENALTY,
        matchup_weight=MATCHUP_WEIGHT, markets=MARKETS,
        odds=prior_meta.get("odds"), book_bias=prior_meta.get("book_bias") or {},
        preseason_note=f"2026 preseason team totals, footballdb.com, snapshot {PRE_SNAPSHOT_DATE}. Mostly backups; not part of the model score.",
        statkeys=SH),players=players,matchup=matchup,teams=teams,games=games,week1={a:b for a,b in WK1_PAIRS}|{b:a for a,b in WK1_PAIRS})
    json.dump(out,open("data.json","w"),separators=(",",":"))
    print(f"data.json: {len(players)} players | moved {sum(p['moved'] for p in players)} | off-roster {sum(not p['rostered'] for p in players)}")

if __name__=="__main__": build()
