"""Bahis ligleri — TR + 6 büyük lig. Emir yok."""
from __future__ import annotations

from contextvars import ContextVar

# football-data: euro mmz4281/{season}/{fd}.csv · Brezilya new/BRA.csv
# Fotmob id: 71 TR · 47 EPL · 87 La Liga · 55 Serie A · 54 Bundesliga · 53 Ligue 1 · 268 Brasileirão

EURO_SEASONS = (
    "1617", "1718", "1819", "1920", "2021",
    "2122", "2223", "2324", "2425", "2526", "2627",
)
EURO_LABEL = {
    "1617": "2016/17", "1718": "2017/18", "1819": "2018/19", "1920": "2019/20",
    "2021": "2020/21", "2122": "2021/22", "2223": "2022/23", "2324": "2023/24",
    "2425": "2024/25", "2526": "2025/26", "2627": "2026/27",
}
BRA_SEASONS = tuple(str(y) for y in range(2016, 2027))
BRA_LABEL = {s: s for s in BRA_SEASONS}

LEAGUES = (
    {
        "id": "tr", "name": "Süper Lig", "short": "TR", "flag": "🇹🇷",
        "fd": "T1", "fotmob": 71, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "superlig_2026_fixtures.json",
        "players": "players.json",
    },
    {
        "id": "epl", "name": "Premier League", "short": "EPL", "flag": "🇬🇧",
        "fd": "E0", "fotmob": 47, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "fixtures_epl.json",
        "players": "players_epl.json",
    },
    {
        "id": "laliga", "name": "La Liga", "short": "ES", "flag": "🇪🇸",
        "fd": "SP1", "fotmob": 87, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "fixtures_laliga.json",
        "players": "players_laliga.json",
    },
    {
        "id": "seriea", "name": "Serie A", "short": "IT", "flag": "🇮🇹",
        "fd": "I1", "fotmob": 55, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "fixtures_seriea.json",
        "players": "players_seriea.json",
    },
    {
        "id": "bundesliga", "name": "Bundesliga", "short": "DE", "flag": "🇩🇪",
        "fd": "D1", "fotmob": 54, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "fixtures_bundesliga.json",
        "players": "players_bundesliga.json",
    },
    {
        "id": "ligue1", "name": "Ligue 1", "short": "FR", "flag": "🇫🇷",
        "fd": "F1", "fotmob": 53, "kind": "euro",
        "seasons": EURO_SEASONS, "labels": EURO_LABEL, "current": "2627",
        "fix_json": "fixtures_ligue1.json",
        "players": "players_ligue1.json",
    },
    {
        "id": "bra", "name": "Brasileirão", "short": "BR", "flag": "🇧🇷",
        "fd": "BRA", "fotmob": 268, "kind": "bra",
        "seasons": BRA_SEASONS, "labels": BRA_LABEL, "current": "2026",
        "fix_json": "fixtures_bra.json",
        "players": "players_bra.json",
    },
)

_BY_ID = {x["id"]: x for x in LEAGUES}
_BY_FD = {x["fd"]: x["id"] for x in LEAGUES}
_LEAGUE: ContextVar[str] = ContextVar("bahis_league", default="tr")

# football-data / Fotmob kısa ad → ortak anahtar
EXTRA_ALIAS = {
    # EPL
    "mancity": "mancity", "manchestercity": "mancity",
    "manunited": "manunited", "manchesterunited": "manunited", "manutd": "manunited",
    "newcastle": "newcastle", "newcastleunited": "newcastle",
    "nottmforest": "nottforest", "nottinghamforest": "nottforest", "nottforest": "nottforest",
    "wolves": "wolves", "wolverhampton": "wolves", "wolverhamptonwanderers": "wolves",
    "spurs": "tottenham", "tottenham": "tottenham", "tottenhamhotspur": "tottenham",
    "westham": "westham", "westhamunited": "westham",
    "crystalpalace": "crystalpalace",
    "brighton": "brighton", "brightonandhovealbion": "brighton",
    "sheffieldunited": "sheffutd", "sheffutd": "sheffutd", "sheffieldutd": "sheffutd",
    "sheffieldwednesday": "sheffwed",
    "nottingham": "nottforest",
    "leicester": "leicester", "leicestercity": "leicester",
    "leeds": "leeds", "leedsunited": "leeds",
    "norwich": "norwich",
    "watford": "watford",
    "fulham": "fulham",
    "brentford": "brentford",
    "bournemouth": "bournemouth", "afcbournemouth": "bournemouth",
    "ipswich": "ipswich", "ipswichtown": "ipswich",
    "luton": "luton", "lutontown": "luton",
    "burnley": "burnley",
    "sunderland": "sunderland",
    "qpr": "qpr", "queensparkrangers": "qpr",
    "huddersfield": "huddersfield",
    "cardiff": "cardiff",
    "swansea": "swansea",
    "westbrom": "westbrom", "westbromwichalbion": "westbrom",
    "stoke": "stoke", "stokecity": "stoke",
    "middlesbrough": "middlesbrough",
    "hull": "hull", "hullcity": "hull",
    # La Liga
    "athmadrid": "atleticomadrid", "atleticomadrid": "atleticomadrid",
    "atletico": "atleticomadrid", "atlmadrid": "atleticomadrid",
    "athbilbao": "athletic", "athletic": "athletic", "athleticclub": "athletic",
    "athleticbilbao": "athletic",
    "espanol": "espanol", "espanyol": "espanol", "rcdespanyol": "espanol",
    "sociedad": "realsociedad", "realsociedad": "realsociedad",
    "betis": "betis", "realbetis": "betis",
    "celta": "celta", "celtavigo": "celta",
    "vallecano": "rayo", "rayovallecano": "rayo", "rayo": "rayo",
    "valladolid": "valladolid",
    "alaves": "alaves", "deportivoalaves": "alaves",
    "getafe": "getafe",
    "girona": "girona",
    "osasuna": "osasuna",
    "mallorca": "mallorca",
    "laspalmas": "laspalmas",
    "cadiz": "cadiz",
    "elche": "elche",
    "levante": "levante",
    "granada": "granada",
    "sevilla": "sevilla",
    "villarreal": "villarreal",
    "valencia": "valencia",
    "barcelona": "barcelona",
    "realmadrid": "realmadrid",
    "leganes": "leganes",
    "eibar": "eibar",
    "huesca": "huesca",
    "oviedo": "oviedo",
    # Serie A
    "inter": "inter", "internazionale": "inter", "intermilan": "inter",
    "acmilan": "milan", "milan": "milan",
    "roma": "roma", "asroma": "roma",
    "lazio": "lazio",
    "napoli": "napoli",
    "juventus": "juventus",
    "atalanta": "atalanta",
    "fiorentina": "fiorentina",
    "torino": "torino",
    "bologna": "bologna",
    "udinese": "udinese",
    "sassuolo": "sassuolo",
    "empoli": "empoli",
    "monza": "monza",
    "lecce": "lecce",
    "cagliari": "cagliari",
    "genoa": "genoa",
    "verona": "verona", "hellasverona": "verona",
    "parma": "parma",
    "como": "como",
    "venezia": "venezia",
    "frosinone": "frosinone",
    "salernitana": "salernitana",
    "spezia": "spezia",
    "cremonese": "cremonese",
    "pisa": "pisa",
    # Bundesliga
    "bayernmunich": "bayern", "bayern": "bayern", "fcbayern": "bayern",
    "fcbayernmunchen": "bayern", "bayernmunchen": "bayern",
    "dortmund": "dortmund", "borussiadortmund": "dortmund",
    "leverkusen": "leverkusen", "bayerleverkusen": "leverkusen",
    "leipzig": "leipzig", "rbleipzig": "leipzig",
    "frankfurt": "frankfurt", "eintrachtfrankfurt": "frankfurt",
    "gladbach": "gladbach", "mgladbach": "gladbach",
    "borussiamgladbach": "gladbach", "monchengladbach": "gladbach",
    "wolfsburg": "wolfsburg",
    "freiburg": "freiburg",
    "hoffenheim": "hoffenheim",
    "stuttgart": "stuttgart", "vfbstuttgart": "stuttgart",
    "unionberlin": "unionberlin",
    "mainz": "mainz", "mainz05": "mainz",
    "augsburg": "augsburg",
    "koln": "koln", "fckoln": "koln", "koeln": "koln",
    "werder": "werder", "werderbremen": "werder",
    "bochum": "bochum",
    "heidenheim": "heidenheim",
    "darmstadt": "darmstadt",
    "hamburg": "hamburg", "hamburgsv": "hamburg",
    "stpauli": "stpauli",
    "hertha": "hertha",
    "schalke": "schalke", "schalke04": "schalke",
    "bielefeld": "bielefeld",
    # Ligue 1
    "psg": "psg", "parissg": "psg", "parissaintgermain": "psg",
    "marseille": "marseille", "olympiquemarseille": "marseille",
    "lyon": "lyon", "olympiquelyon": "lyon",
    "monaco": "monaco", "asmonaco": "monaco",
    "lille": "lille",
    "nice": "nice",
    "rennes": "rennes", "staderennes": "rennes",
    "lens": "lens",
    "strasbourg": "strasbourg",
    "nantes": "nantes",
    "toulouse": "toulouse",
    "reims": "reims",
    "brest": "brest",
    "lorient": "lorient",
    "metz": "metz",
    "auxerre": "auxerre",
    "angers": "angers",
    "lehavre": "lehavre",
    "montpellier": "montpellier",
    "clermont": "clermont",
    "troyes": "troyes",
    "ajaccio": "ajaccio",
    "parisfc": "parisfc",
    # Brazil
    "saopaulo": "saopaulo",
    "palmeiras": "palmeiras",
    "flamengo": "flamengo",
    "fluminense": "fluminense",
    "corinthians": "corinthians",
    "santos": "santos",
    "gremio": "gremio",
    "internacional": "internacional",
    "atleticomg": "atleticomg", "atleticomineiro": "atleticomg", "atleminemiro": "atleticomg",
    "atleticogo": "atleticogo", "atleticogoianiense": "atleticogo",
    "atleticopr": "athletico", "athleticopr": "athletico", "athletico": "athletico",
    "cruzeiro": "cruzeiro",
    "botafogo": "botafogo", "botafogorj": "botafogo",
    "vasco": "vasco", "vascodagama": "vasco",
    "bahia": "bahia",
    "fortaleza": "fortaleza",
    "bragantino": "bragantino", "redbullbragantino": "bragantino",
    "cuiaba": "cuiaba",
    "goias": "goias",
    "coritiba": "coritiba",
    "criciuma": "criciuma",
    "juventude": "juventude",
    "vitoria": "vitoria",
    "mirassol": "mirassol",
    "sport": "sport", "sportrecife": "sport",
    "chapecoense": "chapecoense",
    "americamg": "americamg",
}


def get(league_id: str | None = None) -> dict:
    lid = (league_id or _LEAGUE.get() or "tr").strip().lower()
    if lid in _BY_FD:
        lid = _BY_FD[lid]
    if lid in ("en", "eng", "pl", "premier"):
        lid = "epl"
    if lid in ("es", "spain"):
        lid = "laliga"
    if lid in ("it", "italy"):
        lid = "seriea"
    if lid in ("de", "ger", "germany"):
        lid = "bundesliga"
    if lid in ("fr", "france"):
        lid = "ligue1"
    if lid in ("br", "brazil", "brasil"):
        lid = "bra"
    if lid in ("superlig", "t1", "turkiye"):
        lid = "tr"
    return _BY_ID.get(lid, _BY_ID["tr"])


def current_league() -> str:
    return get()["id"]


def set_league(league_id: str | None) -> str:
    lid = get(league_id or "tr")["id"]
    _LEAGUE.set(lid)
    return lid


def league_from_id(mid: str) -> str:
    head = (mid or "").split("-", 1)[0]
    if head in _BY_ID:
        return head
    return "tr"


def list_public() -> list[dict]:
    return [
        {
            "id": x["id"],
            "name": x["name"],
            "short": x["short"],
            "flag": x["flag"],
            "current": x["current"],
        }
        for x in LEAGUES
    ]


def season_label(league_id: str, season: str) -> str:
    lg = get(league_id)
    return (lg.get("labels") or {}).get(season, season)


def season_weights(league_id: str | None = None) -> dict[str, float]:
    seasons = get(league_id)["seasons"]
    return {s: 0.32 + i * 0.068 for i, s in enumerate(seasons)}
