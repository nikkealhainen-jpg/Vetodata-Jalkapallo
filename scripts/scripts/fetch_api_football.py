"""Hakee API-Footballista CL/EL/UECL/PL-otteluiden tilastot ja tulevien otteluiden tuomarit."""
import datetime as dt, json, os, pathlib, urllib.parse, urllib.request

KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
LEAGUES = {"CL": 2, "EL": 3, "UECL": 848, "PL": 39}
SEASON = int(os.environ.get("SEASON") or 2026)
OUT = pathlib.Path("data")
status = {"run_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "calls": 0, "remaining": None, "errors": []}

def get(path, **params):
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        status["remaining"] = r.headers.get("x-ratelimit-requests-remaining")
        data = json.load(r)
    status["calls"] += 1
    if data.get("errors"):
        status["errors"].append({"path": path, "params": params, "errors": data["errors"]})
    return data.get("response") or []

def stat(team_stats, name):
    for s in team_stats.get("statistics", []):
        if s["type"] == name:
            v = s["value"]
            if isinstance(v, str) and v.endswith("%"):
                v = int(v[:-1])
            return v or 0
    return None

def paf_cards(events):
    """Pafin sääntö: keltainen 1, suora punainen 1, saman pelaajan kaksi keltaista 2."""
    second, n = set(), 0
    for e in events:
        if e.get("type") != "Card":
            continue
        pid, d = (e.get("player") or {}).get("id"), (e.get("detail") or "").lower()
        if "second yellow" in d:
            n += 1
            second.add(pid)
        elif "yellow" in d:
            n += 1
        elif "red" in d and pid not in second:
            n += 1  # suora punainen = 1; toinen keltainen punaisena merkittynä = 1 lisää
    return n

def summary(comp, f):
    fx, teams, goals = f["fixture"], f["teams"], f["goals"]
    st = {s["team"]["id"]: s for s in f.get("statistics", [])}
    h, a = st.get(teams["home"]["id"], {}), st.get(teams["away"]["id"], {})
    row = {"comp": comp, "fixture_id": fx["id"], "date": fx["date"][:10], "round": f["league"].get("round"),
           "home": teams["home"]["name"], "away": teams["away"]["name"], "hg": goals["home"], "ag": goals["away"],
           "referee": fx.get("referee"), "cards": paf_cards(f.get("events", []))}
    for key, name in [("yellow", "Yellow Cards"), ("red", "Red Cards"), ("fouls", "Fouls"), ("corners", "Corner Kicks"),
                      ("shots", "Total Shots"), ("sot", "Shots on Goal"), ("poss", "Ball Possession"), ("xg", "expected_goals")]:
        row[f"{key}_h"], row[f"{key}_a"] = stat(h, name), stat(a, name)
    shots = []
    for team in f.get("players", []):
        for p in team.get("players", []):
            s = (p.get("statistics") or [{}])[0]
            sh = (s.get("shots") or {}).get("total")
            if sh:
                shots.append({"team": team["team"]["name"], "player": p["player"]["name"],
                              "pos": (s.get("games") or {}).get("position"), "minutes": (s.get("games") or {}).get("minutes"),
                              "shots": sh, "sot": (s.get("shots") or {}).get("on") or 0,
                              "goals": (s.get("goals") or {}).get("total") or 0})
    row["player_shots"] = shots
    return row

now = dt.datetime.utcnow()
day = os.environ.get("DATE") or (now.date() if now.hour >= 12 else now.date() - dt.timedelta(days=1)).isoformat()

# 1) Pelatut ottelut: perustiedot liigoittain, sitten täydet tiedot (tilastot, tapahtumat, pelaajat) 20 kerrallaan
played = []
for comp, lid in LEAGUES.items():
    for f in get("fixtures", league=lid, season=SEASON, date=day):
        if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN"):
            played.append((comp, f["fixture"]["id"]))
rows = []
for i in range(0, len(played), 20):
    chunk = played[i:i + 20]
    comp_of = dict((fid, c) for c, fid in chunk)
    for f in get("fixtures", ids="-".join(str(fid) for _, fid in chunk)):
        rows.append(summary(comp_of[f["fixture"]["id"]], f))
if rows:
    (OUT / "matches").mkdir(parents=True, exist_ok=True)
    (OUT / "matches" / f"{day}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))

# 2) Tulevat ottelut (tänään ja huomenna UTC): tuomarit ja ottelu-ID:t
upcoming = []
for d in (now.date(), now.date() + dt.timedelta(days=1)):
    for comp, lid in LEAGUES.items():
        for f in get("fixtures", league=lid, season=SEASON, date=d.isoformat()):
            if f["fixture"]["status"]["short"] in ("NS", "TBD"):
                upcoming.append({"comp": comp, "fixture_id": f["fixture"]["id"], "kickoff_utc": f["fixture"]["date"],
                                 "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
                                 "referee": f["fixture"].get("referee")})
OUT.mkdir(exist_ok=True)
(OUT / "upcoming.json").write_text(json.dumps(upcoming, ensure_ascii=False, indent=1))
status.update({"date": day, "played": len(rows), "upcoming": len(upcoming)})
(OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1))
print(json.dumps(status, ensure_ascii=False))
