#!/usr/bin/env python3
"""Assemble data/videos.json and data/videos_meta.json from the resolved channel data in /tmp/yt."""
import csv, json, re, sys, datetime, collections

YT = "/tmp/yt"
OUT = "/home/claude/election-dashboard/data/videos.json"
META = "/home/claude/election-dashboard/data/videos_meta.json"
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------- load resolved channels ----------
res = {}
for fn in ("results.tsv", "results2.tsv", "results3.tsv"):
    for row in csv.reader(open(f"{YT}/{fn}", encoding="utf-8"), delimiter="\t"):
        if len(row) < 8 or not row[1].startswith("UC"):
            continue
        key, cid, title, live, upc, nst, last, code = row[:8]
        res[key] = dict(id=cid, title=re.sub(r"&#39;", "'", title).replace("&amp;", "&"),
                        live_now=int(live or 0) > 0, n_streams=int(nst or 0), last_streamed=last or None)

def ch(key):
    if key not in res:
        raise SystemExit(f"missing resolved key {key}")
    return res[key]

# ---------- curated picks ----------
# (result_key, outlet, city, county_fips, city_slug, group, tier, note)
# Order within each state = rank order. city=None -> no city entry.
NATIONAL = [
    ("PBSNewsHour", "PBS NewsHour", "pbs", "Free full-length election special; most reliable free stream."),
    ("CSPAN", "C-SPAN", "cspan", "Free, uninterrupted election-night coverage, no commentary."),
    ("ABCNews", "ABC News", "abc", "ABC News Live streams 24/7 on YouTube; dedicated election stream scheduled."),
    ("NBCNews", "NBC News", "nbc", "NBC News NOW streams 24/7; dedicated results stream scheduled."),
    ("CBSNews", "CBS News", "cbs", "CBS News 24/7 streams on YouTube; dedicated results stream scheduled."),
    ("AssociatedPress", "Associated Press", "ap", "AP race calls and maps stream scheduled."),
    ("CNN", "CNN", "cnn", "Candidate HQ feeds and Q&A streams scheduled; CNN Headlines 24/7."),
    ("FoxNews", "Fox News", "fox", "Midterm results stream scheduled."),
    ("Reuters", "Reuters", "reuters", "Raw live feeds; election live stream active."),
    ("NewsNation", "NewsNation", "nexstar", "Streams frequently; election night coverage expected."),
    ("ScrippsNews", "Scripps News", "scripps", "Daily 24/7 stream (Nov. 3 stream live)."),
    ("LiveNOWfromFOX", "LiveNOW from FOX", "fox", "24/7 raw live feeds; streams page not enumerated by scraper."),
    ("BloombergTV", "Bloomberg Television", "bloomberg", "Bloomberg Business News Live 24/7."),
    ("TheHill", "The Hill", "nexstar", "Decision Desk '26 election night stream scheduled."),
    ("USATODAY", "USA TODAY", "gannett", "Election Day live stream active."),
    ("MSNOW", "MS NOW (formerly MSNBC)", "msnow", "VelshiCast election night stream scheduled."),
    ("Newsmax", "Newsmax", "newsmax", "Election night coverage scheduled; NEWSMAX2 live."),
    ("POLITICO", "POLITICO", "politico", "POLITICO Elections Live scheduled."),
    ("ForbesBreakingNews", "Forbes Breaking News", "forbes", "Raw political live feeds."),
    ("WashingtonPost", "The Washington Post", "wapo", "Rarely streams on YouTube; link card fallback."),
    ("CNBC", "CNBC Television", "cnbc", "Occasional streams."),
    ("FoxBusiness", "Fox Business", "fox", "Frequent streams."),
    ("NPR", "NPR", "npr", "Occasional streams."),
    ("Telemundo", "Telemundo", "nbcu", "Spanish-language; frequent streams."),
    ("PBS", "PBS", "pbs", "Rarely streams; NewsHour channel preferred."),
    ("NYTimes", "The New York Times", "nyt", "Rarely streams on YouTube."),
]
NATIONAL_OFFICIAL = [
    ("CISAgov", "CISA (Cybersecurity and Infrastructure Security Agency)", "gov", "Occasional streams; not an election-results source."),
]

# National kind:video entries (videoId, result_key, title, status)
NATIONAL_VIDEOS = [
    ("QRK30J9ouaU", "PBSNewsHour", "WATCH LIVE: Election 2026 PBS News special coverage", "upcoming"),
    ("DXiZio2O9RI", "CSPAN", "C-SPAN Election Night Coverage (Part 1)", "upcoming"),
    ("wF8X-K_l5kY", "ABCNews", "LIVE: Election Day in America: Vote 2026 | ABC News", "live"),
    ("yifzmO4ueG8", "NBCNews", "WATCH LIVE: 2026 Midterm Election Results and Analysis | NBC News", "upcoming"),
    ("zHlI3KJIWMA", "CBSNews", "Watch Live: 2026 midterm election results, news and analysis | CBS News", "upcoming"),
    ("tbAbicAzFU4", "AssociatedPress", "Elections results 2026: LIVE AP race calls and Senate and House maps", "upcoming"),
    ("P0XeDwPCJs0", "CNN", "Live: Midterm candidate HQ feeds & speeches as election results come in", "upcoming"),
    ("GvWSyescLv8", "FoxNews", "WATCH LIVE: 2026 Midterm Election Results", "upcoming"),
    ("MTsZwFVKRfA", "NBCNews", "LIVE: Decision 2026 Election Day Coverage | NBC News NOW - Nov. 3", "live"),
    ("LokrBxbKST8", "Reuters", "LIVE: US citizens vote in the midterm elections", "live"),
    ("Z2TKdIjaPjc", "TheHill", "LIVE: The Hill's Decision Desk '26 - Election Night In America", "upcoming"),
    ("HtDWCGGUQPo", "ScrippsNews", "LIVE: Nov. 3 - Breaking News & Top Headlines", "live"),
    ("30PZySj5NOg", "USATODAY", "Election Day live: Voters cast their ballots in 2026 midterms", "live"),
    ("KQhNZQ_Uag8", "ABCNews", "LIVE: ABC News Live - 24/7 news, context and analysis", "live"),
    ("74WjpIH4jeE", "CBSNews", "LIVE: Breaking News and Top Stories on CBS News 24/7", "live"),
    ("psO-rZpWp7I", "CBSNews", "LIVE: Tracking the 2026 midterm races that will decide the control of Congress", "upcoming"),
    ("GotlA1KKWoo", "CNN", "CNN Headlines: 24/7 Live News", "live"),
    ("MPtBOhQ_ckw", "CNN", "Midterm Election Night Live: Berman, Enten & Political Experts Answer Your Qs", "upcoming"),
    ("b043z24ErQk", "NBCNews", "WATCH: Steve Kornacki Analyzes 2026 Midterm Election Results | Kornacki Cam", "upcoming"),
    ("QreQXPsApEE", "CSPAN", "C-SPAN Election Night Coverage (Part 2)", "upcoming"),
    ("3ABLwTR8Iqg", "PBSNewsHour", "WATCH LIVE: Election 2026 PBS News special coverage with ASL interpretation", "upcoming"),
    ("QB5BNdBFujE", "BloombergTV", "Bloomberg Business News Live", "live"),
    ("9TJCzGGDI9o", "MSNOW", "WATCH LIVE! VelshiCast on Election Night 2026 | MS NOW", "upcoming"),
    ("SUwgHUYZN6w", "Newsmax", "LIVE: NEWSMAX Vote For America 2026 Midterm Election Night Coverage", "upcoming"),
    ("MXosVElBUJQ", "Newsmax", "NEWSMAX2 LIVE | Vote For America Midterm Election Coverage", "live"),
    ("ifR76aR6Xq4", "POLITICO", "POLITICO Elections Live", "upcoming"),
]

# Per-state picks: fips -> (postal, [(result_key, outlet, city, county_fips, city_slug, group, tier, note), ...])
S = {}
S["01"] = ("AL", [
    ("ABC3340", "ABC 33/40 (WBMA)", "Birmingham", "01073", "birmingham", "sinclair", "regional_outlet", ""),
    ("WVTM13__1", "WVTM 13", "Birmingham", "01073", "birmingham", "hearst", "regional_outlet", ""),
    ("WBRC__1", "WBRC FOX6 News", "Birmingham", "01073", "birmingham", "gray", "regional_outlet", ""),
    ("WSFA__1", "WSFA 12 News", "Montgomery", "01101", "montgomery", "gray", "regional_outlet", ""),
    ("WAFF__1", "WAFF 48 News", "Huntsville", "01089", "huntsville", "gray", "regional_outlet", ""),
    ("ALSOS__1", "Alabama Secretary of State", None, None, None, "gov", "official", "No streams on record."),
])
S["02"] = ("AK", [
    ("AlaskasNewsSource", "Alaska's News Source (KTUU/KYES)", "Anchorage", "02020", "anchorage", "gray", "regional_outlet", "'Alaska Decides' live stream active."),
    ("AlaskaPublic", "Alaska Public Media", "Anchorage", "02020", "anchorage", "public", "regional_outlet", "'Election Night Live 2026' scheduled."),
    ("KTOO", "KTOO 360TV", "Juneau", "02110", "juneau", "public", "regional_outlet", ""),
])
S["04"] = ("AZ", [
    ("FOX10Phoenix", "FOX 10 Phoenix", "Phoenix", "04013", "phoenix", "fox_oo", "regional_outlet", "FOX LOCAL Phoenix 24/7 stream; Election Day special scheduled."),
    ("12News", "12News (KPNX)", "Phoenix", "04013", "phoenix", "tegna", "regional_outlet", ""),
    ("ABC15", "ABC15 Arizona", "Phoenix", "04013", "phoenix", "scripps", "regional_outlet", "24/7 stream."),
    ("AZFamily", "Arizona's Family (3TV/CBS 5)", "Phoenix", "04013", "phoenix", "gray", "regional_outlet", ""),
    ("KGUN", "KGUN 9", "Tucson", "04019", "tucson", "scripps", "regional_outlet", ""),
    ("MaricopaVote", "Maricopa County Elections Department", "Phoenix", "04013", "phoenix", "gov", "official", "Streams tabulation center regularly."),
    ("AZSOS__3", "Arizona Secretary of State (Adrian Fontes)", "Phoenix", "04013", "phoenix", "gov", "official", "Active streamer; canvass stream scheduled."),
])
S["05"] = ("AR", [
    ("THV11", "THV11 (KTHV)", "Little Rock", "05119", "little-rock", "tegna", "regional_outlet", ""),
    ("KATV__r3_1", "KATV Channel 7", "Little Rock", "05119", "little-rock", "sinclair", "regional_outlet", ""),
    ("FOX16__2", "FOX 16 News (KLRT)", "Little Rock", "05119", "little-rock", "nexstar", "regional_outlet", "No streams on record."),
    ("4029", "40/29 News (KHBS/KHOG)", "Fort Smith", "05131", "fort-smith", "hearst", "regional_outlet", ""),
    ("ARSOS__1", "Arkansas Secretary of State", None, None, None, "gov", "official", "Rarely streams."),
])
S["06"] = ("CA", [
    ("KCRA", "KCRA 3", "Sacramento", "06067", "sacramento", "hearst", "regional_outlet", "'KCRA 3 Election Night in California' scheduled."),
    ("FOXLA", "FOX 11 Los Angeles", "Los Angeles", "06037", "los-angeles", "fox_oo", "regional_outlet", "FOX LOCAL LA 24/7 stream."),
    ("ABC7LA", "ABC7 Los Angeles (KABC)", "Los Angeles", "06037", "los-angeles", "abc_oo", "regional_outlet", "24/7 stream."),
    ("ABC7News", "ABC7 News Bay Area (KGO)", "San Francisco", "06075", "san-francisco", "abc_oo", "regional_outlet", "Many simultaneous live cams; channel_live may resolve to a webcam."),
    ("KTVU", "KTVU FOX 2", "San Francisco", "06075", "san-francisco", "fox_oo", "regional_outlet", "FOX LOCAL SF 24/7 stream."),
    ("CBSLA", "CBS Los Angeles (KCAL/KCBS)", "Los Angeles", "06037", "los-angeles", "cbs_oo", "regional_outlet", ""),
    ("KTLA", "KTLA 5", "Los Angeles", "06037", "los-angeles", "nexstar", "regional_outlet", ""),
    ("ABC10", "ABC10 (KXTV)", "Sacramento", "06067", "sacramento", "tegna", "regional_outlet", ""),
    ("KRON4__1", "KRON4", "San Francisco", "06075", "san-francisco", "nexstar", "regional_outlet", ""),
    ("NBCBayArea", "NBC Bay Area", "San Francisco", "06075", "san-francisco", "nbc_oo", "regional_outlet", ""),
    ("CBS8", "CBS 8 San Diego", "San Diego", "06073", "san-diego", "tegna", "regional_outlet", ""),
    ("NBCSanDiego", "NBC 7 San Diego", "San Diego", "06073", "san-diego", "nbc_oo", "regional_outlet", ""),
    ("10News__r3_1", "ABC 10News San Diego (KGTV)", "San Diego", "06073", "san-diego", "scripps", "regional_outlet", ""),
    ("CBSSacramento", "CBS News Sacramento", "Sacramento", "06067", "sacramento", "cbs_oo", "regional_outlet", ""),
    ("NBCLA", "NBC Los Angeles", "Los Angeles", "06037", "los-angeles", "nbc_oo", "regional_outlet", "No streams on record."),
    ("CASOS__1", "California Secretary of State", "Sacramento", "06067", "sacramento", "gov", "official", "Occasional streams."),
])
S["08"] = ("CO", [
    ("9NEWS", "9NEWS (KUSA)", "Denver", "08031", "denver", "tegna", "regional_outlet", "'9NEWS Live Election Night' scheduled."),
    ("Denver7", "Denver7 (KMGH)", "Denver", "08031", "denver", "scripps", "regional_outlet", "24/7 stream."),
    ("CBSColorado", "CBS Colorado (KCNC)", "Denver", "08031", "denver", "cbs_oo", "regional_outlet", ""),
    ("KDVR__1", "FOX31 Denver (KDVR)", "Denver", "08031", "denver", "nexstar", "regional_outlet", "No streams on record."),
    ("COSOS__1", "Colorado Secretary of State", "Denver", "08031", "denver", "gov", "official", "No streams on record."),
])
S["09"] = ("CT", [
    ("NBCConnecticut", "NBC Connecticut", "Hartford", "09003", "hartford", "nbc_oo", "regional_outlet", "'Connecticut Election Night 2026' live stream active."),
    ("WFSB", "WFSB Channel 3", "Hartford", "09003", "hartford", "gray", "regional_outlet", "No streams on record."),
    ("FOX61", "FOX61 (WTIC)", "Hartford", "09003", "hartford", "tegna", "regional_outlet", "No streams on record."),
    ("CTPublic__1", "Connecticut Public", "Hartford", "09003", "hartford", "public", "regional_outlet", ""),
    ("CTSOTS", "Connecticut Secretary of the State", "Hartford", "09003", "hartford", "gov", "official", "No streams on record."),
])
S["10"] = ("DE", [
    ("WBOC", "WBOC (Salisbury, MD / Delmarva)", None, None, None, "indep", "regional_outlet", "Delmarva station covering Delaware; no streams on record."),
    ("WMDT__1", "47 ABC WMDT (Delmarva)", None, None, None, "marquee", "regional_outlet", ""),
    ("6abc__1", "6abc Philadelphia", None, None, None, "abc_oo", "regional_outlet", "Philadelphia market covers Delaware."),
    ("NBC10", "NBC10 Philadelphia", None, None, None, "nbc_oo", "regional_outlet", "Philadelphia market covers Delaware; 24/7 stream."),
    ("DelawarePublic", "Delaware Public Media", None, None, None, "public", "regional_outlet", "No streams on record."),
    ("WDEL", "WDEL", "Wilmington", "10003", "wilmington", "indep", "regional_outlet", "No streams on record."),
    ("DEELECT__1", "Delaware Department of Elections", None, None, None, "gov", "official", "No streams on record."),
])
S["12"] = ("FL", [
    ("WKMG", "News 6 WKMG", "Orlando", "12095", "orlando", "graham", "regional_outlet", "'Election Day 2026 | Tracking Results in Florida' scheduled."),
    ("FOX13Tampa__1", "FOX 13 Tampa Bay", "Tampa", "12057", "tampa", "fox_oo", "regional_outlet", "FOX LOCAL Tampa Bay 24/7 stream."),
    ("WPLG", "WPLG Local 10", "Miami", "12086", "miami", "graham", "regional_outlet", "24/7 stream."),
    ("FOX35__1", "FOX 35 Orlando", "Orlando", "12095", "orlando", "fox_oo", "regional_outlet", "FOX LOCAL Orlando 24/7 stream."),
    ("WESH", "WESH 2", "Orlando", "12095", "orlando", "hearst", "regional_outlet", ""),
    ("WFLA__1", "WFLA News Channel 8", "Tampa", "12057", "tampa", "nexstar", "regional_outlet", ""),
    ("ABCActionNews__1", "Tampa Bay 28 (WFTS, formerly ABC Action News)", "Tampa", "12057", "tampa", "scripps", "regional_outlet", "24/7 stream."),
    ("News4JAX", "News4JAX (WJXT)", "Jacksonville", "12031", "jacksonville", "graham", "regional_outlet", ""),
    ("ActionNewsJax__1", "Action News Jax (WJAX/WFOX)", "Jacksonville", "12031", "jacksonville", "cox", "regional_outlet", ""),
    ("FirstCoastNews", "First Coast News (WTLV/WJXX)", "Jacksonville", "12031", "jacksonville", "tegna", "regional_outlet", ""),
    ("NBC6__1", "NBC 6 South Florida", "Miami", "12086", "miami", "nbc_oo", "regional_outlet", ""),
    ("10TampaBay", "10 Tampa Bay (WTSP)", "Tampa", "12057", "tampa", "tegna", "regional_outlet", "No streams on record."),
    ("CBSMiami", "CBS Miami", "Miami", "12086", "miami", "cbs_oo", "regional_outlet", "Last stream a year ago."),
    ("WSVN", "WSVN 7News", "Miami", "12086", "miami", "sunbeam", "regional_outlet", "No streams on record."),
    ("FLDOS__1", "Florida Department of State", None, None, None, "gov", "official", "No streams on record."),
])
S["13"] = ("GA", [
    ("FOX5Atlanta", "FOX 5 Atlanta", "Atlanta", "13121", "atlanta", "fox_oo", "regional_outlet", "Election Day live stream active; FOX LOCAL Atlanta 24/7."),
    ("11Alive", "11Alive (WXIA)", "Atlanta", "13121", "atlanta", "tegna", "regional_outlet", ""),
    ("WSBTV", "WSB-TV", "Atlanta", "13121", "atlanta", "cox", "regional_outlet", ""),
    ("AtlantaNewsFirst", "Atlanta News First (WANF)", "Atlanta", "13121", "atlanta", "gray", "regional_outlet", ""),
    ("GPB", "Georgia Public Broadcasting", "Atlanta", "13121", "atlanta", "public", "regional_outlet", ""),
])
S["15"] = ("HI", [
    ("HawaiiNewsNow__1", "Hawaii News Now", "Honolulu", "15003", "honolulu", "gray", "regional_outlet", ""),
    ("KHON2_alt", "KHON2", "Honolulu", "15003", "honolulu", "nexstar", "regional_outlet", "No streams on record."),
    ("KITV_alt", "KITV4 Island News", "Honolulu", "15003", "honolulu", "allen", "regional_outlet", "Last stream a year ago."),
    ("HIELECT__1", "State of Hawaii Office of Elections", "Honolulu", "15003", "honolulu", "gov", "official", "Streams regularly."),
])
S["16"] = ("ID", [
    ("KTVB__1", "KTVB", "Boise", "16001", "boise", "tegna", "regional_outlet", ""),
    ("IdahoNews6__1", "Idaho News 6 (KIVI)", "Boise", "16001", "boise", "scripps", "regional_outlet", "24/7 stream."),
    ("CBS2Idaho__1", "Idaho News on Demand (KBOI)", "Boise", "16001", "boise", "sinclair", "regional_outlet", ""),
    ("IdahoPTV", "Idaho Public Television", "Boise", "16001", "boise", "public", "regional_outlet", ""),
])
S["17"] = ("IL", [
    ("FOX32", "FOX 32 Chicago", "Chicago", "17031", "chicago", "fox_oo", "regional_outlet", "'Illinois 2026 midterm election results' scheduled; FOX LOCAL Chicago 24/7."),
    ("ABC7Chicago", "ABC 7 Chicago", "Chicago", "17031", "chicago", "abc_oo", "regional_outlet", "Election Day live stream active."),
    ("WGN_alt", "WGN News", "Chicago", "17031", "chicago", "nexstar", "regional_outlet", ""),
    ("CBSChicago", "CBS Chicago", "Chicago", "17031", "chicago", "cbs_oo", "regional_outlet", ""),
    ("NBCChicago", "NBC Chicago", "Chicago", "17031", "chicago", "nbc_oo", "regional_outlet", ""),
    ("WTTW", "WTTW News", "Chicago", "17031", "chicago", "public", "regional_outlet", ""),
    ("ILSBE", "Illinois State Board of Elections", None, None, None, "gov", "official", "Streams board meetings."),
])
S["18"] = ("IN", [
    ("WISHTV__1", "WISH-TV", "Indianapolis", "18097", "indianapolis", "circle_city", "regional_outlet", ""),
    ("WRTV__1", "WRTV", "Indianapolis", "18097", "indianapolis", "scripps", "regional_outlet", ""),
    ("WTHR", "WTHR 13News", "Indianapolis", "18097", "indianapolis", "tegna", "regional_outlet", "No streams on record."),
])
S["19"] = ("IA", [
    ("KCCI", "KCCI 8", "Des Moines", "19153", "des-moines", "hearst", "regional_outlet", ""),
    ("WOI__1", "Local 5 (WOI)", "Des Moines", "19153", "des-moines", "tegna", "regional_outlet", ""),
    ("KCRG", "KCRG-TV9", "Cedar Rapids", "19113", "cedar-rapids", "gray", "regional_outlet", ""),
    ("WHO13_alt", "WHO 13", "Des Moines", "19153", "des-moines", "nexstar", "regional_outlet", "No streams on record."),
    ("IowaPBS", "Iowa PBS", None, None, None, "public", "regional_outlet", ""),
    ("IASOS_alt", "Iowa Secretary of State", "Des Moines", "19153", "des-moines", "gov", "official", "No streams on record."),
])
S["20"] = ("KS", [
    ("KWCH__1", "KWCH 12 News", "Wichita", "20173", "wichita", "gray", "regional_outlet", ""),
    ("KSN_alt", "KSN News", "Wichita", "20173", "wichita", "nexstar", "regional_outlet", ""),
    ("KAKE__1", "KAKE News", "Wichita", "20173", "wichita", "lockwood", "regional_outlet", ""),
    ("WIBW", "WIBW 13 News", "Topeka", "20177", "topeka", "gray", "regional_outlet", ""),
    ("KCTV", "KCTV5 (Kansas City)", None, None, None, "gray", "regional_outlet", "Kansas City market; 2026 live election coverage active."),
    ("KMBC", "KMBC 9 (Kansas City)", None, None, None, "hearst", "regional_outlet", "Kansas City market."),
    ("KSSOS__1", "Kansas Secretary of State", "Topeka", "20177", "topeka", "gov", "official", "Rarely streams."),
])
S["21"] = ("KY", [
    ("WLKY", "WLKY", "Louisville", "21111", "louisville", "hearst", "regional_outlet", ""),
    ("WHAS11__2", "WHAS11", "Louisville", "21111", "louisville", "tegna", "regional_outlet", ""),
    ("WAVE__1", "WDRB + WAVE", "Louisville", "21111", "louisville", "block", "regional_outlet", "Joint WDRB/WAVE channel."),
    ("LEX18__1", "LEX 18", "Lexington", "21067", "lexington", "scripps", "regional_outlet", "24/7 stream."),
])
S["22"] = ("LA", [
    ("WWLTV", "WWL-TV", "New Orleans", "22071", "new-orleans", "tegna", "regional_outlet", ""),
    ("WDSU", "WDSU", "New Orleans", "22071", "new-orleans", "hearst", "regional_outlet", ""),
    ("FOX8NOLA", "FOX 8 New Orleans (WVUE)", "New Orleans", "22071", "new-orleans", "gray", "regional_outlet", ""),
    ("WAFB", "WAFB 9", "Baton Rouge", "22033", "baton-rouge", "gray", "regional_outlet", ""),
    ("WBRZ", "WBRZ", "Baton Rouge", "22033", "baton-rouge", "manship", "regional_outlet", ""),
    ("LASOS", "Louisiana Secretary of State", "Baton Rouge", "22033", "baton-rouge", "gov", "official", "Rarely streams."),
])
S["23"] = ("ME", [
    ("NEWSCENTERMaine", "NEWS CENTER Maine (WCSH/WLBZ)", "Portland", "23005", "portland", "tegna", "regional_outlet", ""),
    ("WMTW", "WMTW", "Portland", "23005", "portland", "hearst", "regional_outlet", ""),
    ("WGME__1", "WGME CBS 13", "Portland", "23005", "portland", "sinclair", "regional_outlet", ""),
    ("MainePublic", "Maine Public", "Portland", "23005", "portland", "public", "regional_outlet", ""),
])
S["24"] = ("MD", [
    ("WBAL", "WBAL-TV 11", "Baltimore", "24510", "baltimore", "hearst", "regional_outlet", ""),
    ("WMAR", "WMAR 2 News", "Baltimore", "24510", "baltimore", "scripps", "regional_outlet", "24/7 stream."),
    ("FOX45__1", "FOX45 Baltimore (WBFF)", "Baltimore", "24510", "baltimore", "sinclair", "regional_outlet", ""),
    ("WUSA9__1", "WUSA9 (Washington)", None, None, None, "tegna", "regional_outlet", "DC market covers MD suburbs; 'Mapping the Midterms' live."),
    ("FOX5DC", "FOX 5 Washington DC", None, None, None, "fox_oo", "regional_outlet", "DC market; 'Midterm Elections 2026 in DC, Maryland and Virginia' scheduled."),
    ("WJLA__1", "7News DC (WJLA)", None, None, None, "sinclair", "regional_outlet", "DC market."),
    ("CBSBaltimore__1", "WJZ CBS Baltimore", "Baltimore", "24510", "baltimore", "cbs_oo", "regional_outlet", "Last stream years ago."),
    ("NBCWashington", "NBC4 Washington", None, None, None, "nbc_oo", "regional_outlet", "Rarely streams."),
    ("MPT", "Maryland Public Television", None, None, None, "public", "regional_outlet", ""),
    ("MDSBE__r3_1", "Maryland State Board of Elections", None, None, None, "gov", "official", "No streams on record."),
])
S["25"] = ("MA", [
    ("WCVB", "WCVB Channel 5", "Boston", "25025", "boston", "hearst", "regional_outlet", ""),
    ("CBSBoston", "CBS Boston (WBZ)", "Boston", "25025", "boston", "cbs_oo", "regional_outlet", ""),
    ("Boston25", "Boston 25 News", "Boston", "25025", "boston", "cox", "regional_outlet", ""),
    ("NBCBoston", "NBC10 Boston", "Boston", "25025", "boston", "nbc_oo", "regional_outlet", "Rarely streams."),
    ("GBH", "GBH", "Boston", "25025", "boston", "public", "regional_outlet", ""),
])
S["26"] = ("MI", [
    ("FOX2Detroit", "FOX 2 Detroit", "Detroit", "26163", "detroit", "fox_oo", "regional_outlet", "'Live: Election results' scheduled; FOX LOCAL Detroit 24/7."),
    ("CBSDetroit", "CBS Detroit", "Detroit", "26163", "detroit", "cbs_oo", "regional_outlet", "'Tracking Michigan's 2026 midterm election results' scheduled."),
    ("WXYZ__1", "WXYZ-TV Detroit", "Detroit", "26163", "detroit", "scripps", "regional_outlet", "24/7 stream."),
    ("WOODTV__1", "WOOD TV8", "Grand Rapids", "26081", "grand-rapids", "nexstar", "regional_outlet", "'Election Night in Michigan' scheduled."),
    ("WZZM__1", "13 ON YOUR SIDE (WZZM)", "Grand Rapids", "26081", "grand-rapids", "tegna", "regional_outlet", ""),
    ("WDIV__2", "WDIV Local 4", "Detroit", "26163", "detroit", "graham", "regional_outlet", "No streams on record."),
])
S["27"] = ("MN", [
    ("FOX9", "FOX 9 Minneapolis-St. Paul", "Minneapolis", "27053", "minneapolis", "fox_oo", "regional_outlet", "'Minnesota election coverage' live; FOX LOCAL Minnesota 24/7."),
    ("CBSMinnesota_alt", "WCCO - CBS Minnesota", "Minneapolis", "27053", "minneapolis", "cbs_oo", "regional_outlet", "'Midterm Election Special' scheduled."),
    ("KARE11", "KARE 11", "Minneapolis", "27053", "minneapolis", "tegna", "regional_outlet", ""),
    ("KSTP__1", "KSTP 5 Eyewitness News", "Minneapolis", "27053", "minneapolis", "hubbard", "regional_outlet", "Streaming channel 24/7."),
    ("MNSOS__1", "Minnesota Secretary of State", None, None, None, "gov", "official", "Streams occasionally (last 1 day ago)."),
])
S["28"] = ("MS", [
    ("WLBT__1", "WLBT 3 On Your Side", "Jackson", "28049", "jackson", "gray", "regional_outlet", ""),
    ("WAPT__1", "16 WAPT News", "Jackson", "28049", "jackson", "hearst", "regional_outlet", ""),
    ("WTVA__1", "WTVA 9 News", "Tupelo", "28081", "tupelo", "allen", "regional_outlet", ""),
    ("WJTV", "WJTV 12", "Jackson", "28049", "jackson", "nexstar", "regional_outlet", "No streams on record."),
])
S["29"] = ("MO", [
    ("KCTV", "KCTV5 News", "Kansas City", "29095", "kansas-city", "gray", "regional_outlet", "'2026 Live Election Coverage' active."),
    ("KMBC", "KMBC 9", "Kansas City", "29095", "kansas-city", "hearst", "regional_outlet", ""),
    ("KSDK_alt", "KSDK 5 On Your Side", "St. Louis", "29510", "st-louis", "tegna", "regional_outlet", ""),
    ("FOX2Now__2", "FOX 2 St. Louis (KTVI)", "St. Louis", "29510", "st-louis", "nexstar", "regional_outlet", "Multiple live cams; channel_live may resolve to a webcam."),
    ("FOX4KC", "FOX4 Kansas City (WDAF)", "Kansas City", "29095", "kansas-city", "nexstar", "regional_outlet", ""),
    ("KMOV__1", "First Alert 4 (KMOV)", "St. Louis", "29510", "st-louis", "gray", "regional_outlet", "Last stream years ago."),
])
S["30"] = ("MT", [
    ("NBCMontana", "NBC Montana (KECI/KCFW/KTVM)", "Missoula", "30063", "missoula", "sinclair", "regional_outlet", ""),
    ("KTVQ__1", "KTVQ Q2 News", "Billings", "30111", "billings", "scripps", "regional_outlet", "24/7 stream."),
    ("KULR8__1", "NonStop Local (KULR-8 Montana)", "Billings", "30111", "billings", "cowles", "regional_outlet", "Shared NonStop Local channel (MT + WA); 24/7 Montana stream."),
    ("MontanaPBS", "Montana PBS", None, None, None, "public", "regional_outlet", "Last stream years ago."),
])
S["31"] = ("NE", [
    ("KETV", "KETV NewsWatch 7", "Omaha", "31055", "omaha", "hearst", "regional_outlet", ""),
    ("WOWT__1", "First Alert 6 (WOWT)", "Omaha", "31055", "omaha", "gray", "regional_outlet", ""),
    ("KMTV__1", "KMTV 3 News Now", "Omaha", "31055", "omaha", "scripps", "regional_outlet", "24/7 stream."),
    ("1011Now__1", "10/11 NOW (KOLN)", "Lincoln", "31109", "lincoln", "gray", "regional_outlet", ""),
    ("NebraskaPublicMedia", "Nebraska Public Media", "Lincoln", "31109", "lincoln", "public", "regional_outlet", ""),
    ("NESOS__1", "Nebraska Secretary of State", "Lincoln", "31109", "lincoln", "gov", "official", "Rarely streams."),
])
S["32"] = ("NV", [
    ("KTNV", "KTNV 13 Action News", "Las Vegas", "32003", "las-vegas", "scripps", "regional_outlet", "24/7 stream."),
    ("News3LV__1", "News 3 Las Vegas (KSNV)", "Las Vegas", "32003", "las-vegas", "sinclair", "regional_outlet", ""),
    ("FOX5Vegas__1", "FOX5 Las Vegas (KVVU)", "Las Vegas", "32003", "las-vegas", "gray", "regional_outlet", ""),
    ("8NewsNow", "8 News Now (KLAS)", "Las Vegas", "32003", "las-vegas", "nexstar", "regional_outlet", "No recent streams on this channel."),
    ("KOLO__1", "KOLO 8 News Now", "Reno", "32031", "reno", "gray", "regional_outlet", "No streams on record."),
    ("ClarkCountyNV", "Clark County, Nevada", "Las Vegas", "32003", "las-vegas", "gov", "official", "County live stream active."),
    ("NVSOS", "Nevada Secretary of State", None, None, None, "gov", "official", "No streams on record."),
])
S["33"] = ("NH", [
    ("WMUR_alt", "WMUR-TV", "Manchester", "33011", "manchester", "hearst", "regional_outlet", ""),
    ("NHPR", "New Hampshire Public Radio", "Concord", "33013", "concord", "public", "regional_outlet", ""),
    ("NHPBS", "New Hampshire PBS", None, None, None, "public", "regional_outlet", "Last stream a year ago."),
    ("WCVB", "WCVB Channel 5 (Boston)", None, None, None, "hearst", "regional_outlet", "Boston market covers southern NH."),
])
S["34"] = ("NJ", [
    ("FOX5NY", "FOX 5 New York", None, None, None, "fox_oo", "regional_outlet", "'Election Night 2026 in NYC & NJ' scheduled."),
    ("News12", "News 12 (NY/NJ/CT)", None, None, None, "altice", "regional_outlet", "24/7 stream."),
    ("NJSpotlight", "NJ Spotlight News (NJ PBS)", "Newark", "34013", "newark", "public", "regional_outlet", ""),
    ("PIX11", "PIX11 News", None, None, None, "nexstar", "regional_outlet", ""),
    ("ABC7NY", "Eyewitness News ABC7NY", None, None, None, "abc_oo", "regional_outlet", "24/7 stream."),
    ("CBSNewYork", "CBS New York", None, None, None, "cbs_oo", "regional_outlet", "'New York Election Night 2026' scheduled."),
    ("6abc__1", "6abc Philadelphia", None, None, None, "abc_oo", "regional_outlet", "Philadelphia market covers South Jersey."),
])
S["35"] = ("NM", [
    ("KOB4", "KOB 4", "Albuquerque", "35001", "albuquerque", "hubbard", "regional_outlet", ""),
    ("KOAT", "KOAT Action 7 News", "Albuquerque", "35001", "albuquerque", "hearst", "regional_outlet", ""),
    ("KRQE__1", "KRQE News 13", "Albuquerque", "35001", "albuquerque", "nexstar", "regional_outlet", ""),
    ("NMPBS_alt", "New Mexico PBS", "Albuquerque", "35001", "albuquerque", "public", "regional_outlet", "Last stream years ago."),
])
S["36"] = ("NY", [
    ("CBSNewYork", "CBS New York", "New York", "36061", "new-york", "cbs_oo", "regional_outlet", "'New York Election Night 2026 team coverage' scheduled."),
    ("FOX5NY", "FOX 5 New York", "New York", "36061", "new-york", "fox_oo", "regional_outlet", "'Election Night 2026 in NYC & NJ' scheduled; FOX LOCAL NY 24/7."),
    ("NY1_alt", "Spectrum News NY1", "New York", "36061", "new-york", "spectrum", "regional_outlet", "'New York Election Coverage on NY1' live."),
    ("ABC7NY", "Eyewitness News ABC7NY", "New York", "36061", "new-york", "abc_oo", "regional_outlet", "24/7 stream."),
    ("PIX11", "PIX11 News", "New York", "36061", "new-york", "nexstar", "regional_outlet", ""),
    ("NBCNewYork", "NBC New York", "New York", "36061", "new-york", "nbc_oo", "regional_outlet", "No streams on record."),
    ("WGRZ__1", "WGRZ 2 On Your Side", "Buffalo", "36029", "buffalo", "tegna", "regional_outlet", ""),
    ("WHAM__1", "13WHAM", "Rochester", "36055", "rochester", "sinclair", "regional_outlet", ""),
    ("WRGB__1", "CBS6 Albany (WRGB)", "Albany", "36001", "albany", "sinclair", "regional_outlet", ""),
    ("NYSBOE", "New York State Board of Elections", "Albany", "36001", "albany", "gov", "official", "No streams on record."),
])
S["37"] = ("NC", [
    ("CBS17", "CBS 17 (WNCN)", "Raleigh", "37183", "raleigh", "nexstar", "regional_outlet", "'2026 Midterm Election Live Coverage' scheduled."),
    ("ABC11__1", "ABC11 (WTVD)", "Raleigh", "37183", "raleigh", "abc_oo", "regional_outlet", "24/7 stream."),
    ("WRAL__1", "WRAL", "Raleigh", "37183", "raleigh", "cbc", "regional_outlet", "24/7 stream."),
    ("WCNC", "WCNC Charlotte", "Charlotte", "37119", "charlotte", "tegna", "regional_outlet", ""),
    ("WSOC__1", "WSOC-TV", "Charlotte", "37119", "charlotte", "cox", "regional_outlet", ""),
    ("PBSNC__1", "PBS North Carolina", None, None, None, "public", "regional_outlet", "Streams NC State Board of Elections meetings live."),
    ("WFMY", "WFMY News 2", "Greensboro", "37081", "greensboro", "tegna", "regional_outlet", ""),
    ("WXII__1", "WXII 12 News", "Winston-Salem", "37067", "winston-salem", "hearst", "regional_outlet", ""),
    ("WBTV__r3_2", "WBTV News - Charlotte", "Charlotte", "37119", "charlotte", "gray", "regional_outlet", "Last stream a year ago."),
    ("NCSBE__1", "North Carolina State Board of Elections", "Raleigh", "37183", "raleigh", "gov", "official", "No streams on own channel; meetings streamed via PBS NC."),
])
S["38"] = ("ND", [
    ("KFYR__1", "KFYR-TV (KFYR+)", "Bismarck", "38015", "bismarck", "gray", "regional_outlet", "No streams on record."),
    ("ValleyNewsLive", "Valley News Live (KVLY)", "Fargo", "38017", "fargo", "gray", "regional_outlet", "No streams on record."),
    ("KVRR__1", "KVRR News", "Fargo", "38017", "fargo", "red_river", "regional_outlet", "No streams on record."),
    ("KXNews", "KX News (KXMB)", "Bismarck", "38015", "bismarck", "nexstar", "regional_outlet", "No streams on record."),
    ("PrairiePublic", "Prairie Public", "Fargo", "38017", "fargo", "public", "regional_outlet", "No streams on record."),
    ("NDSOS__1", "North Dakota Secretary of State", "Bismarck", "38015", "bismarck", "gov", "official", "No streams on record."),
])
S["39"] = ("OH", [
    ("WKYC__1", "WKYC Channel 3", "Cleveland", "39035", "cleveland", "tegna", "regional_outlet", ""),
    ("Cleveland19", "19 News (WOIO)", "Cleveland", "39035", "cleveland", "gray", "regional_outlet", ""),
    ("WCPO", "WCPO 9", "Cincinnati", "39061", "cincinnati", "scripps", "regional_outlet", "24/7 stream."),
    ("News5Cleveland", "News 5 Cleveland (WEWS)", "Cleveland", "39035", "cleveland", "scripps", "regional_outlet", ""),
    ("WLWT", "WLWT News 5", "Cincinnati", "39061", "cincinnati", "hearst", "regional_outlet", ""),
    ("Local12__r3_1", "Local 12 (WKRC)", "Cincinnati", "39061", "cincinnati", "sinclair", "regional_outlet", ""),
    ("10TV__3", "10TV (WBNS)", "Columbus", "39049", "columbus", "tegna", "regional_outlet", "No streams on record."),
    ("NBC4", "NBC4 Columbus (WCMH)", "Columbus", "39049", "columbus", "nexstar", "regional_outlet", "No streams on record."),
    ("OhioChannel__1", "The Ohio Channel", "Columbus", "39049", "columbus", "public", "official", "State public-affairs network."),
    ("OHSOS_alt", "Ohio Secretary of State", "Columbus", "39049", "columbus", "gov", "official", "No streams on record."),
])
S["40"] = ("OK", [
    ("News9__1", "Oklahoma's Own (News 9 / News On 6)", "Oklahoma City", "40109", "oklahoma-city", "griffin", "regional_outlet", "Joint channel; News 9 and News On 6 24/7 streams."),
    ("KOCO", "KOCO 5 News", "Oklahoma City", "40109", "oklahoma-city", "hearst", "regional_outlet", ""),
    ("KFOR__3", "KFOR Oklahoma's News 4", "Oklahoma City", "40109", "oklahoma-city", "nexstar", "regional_outlet", ""),
    ("OKCFOX__1", "KOKH FOX 25", "Oklahoma City", "40109", "oklahoma-city", "sinclair", "regional_outlet", ""),
    ("KJRH__1", "KJRH 2 News Oklahoma", "Tulsa", "40143", "tulsa", "scripps", "regional_outlet", "24/7 stream."),
    ("KTUL__1", "KTUL (Tulsa's News Pulse)", "Tulsa", "40143", "tulsa", "sinclair", "regional_outlet", ""),
    ("OKSEB__1", "Oklahoma State Election Board", "Oklahoma City", "40109", "oklahoma-city", "gov", "official", "Rarely streams."),
])
S["41"] = ("OR", [
    ("KGW__1", "KGW News", "Portland", "41051", "portland", "tegna", "regional_outlet", ""),
    ("KATU_alt", "KATU News", "Portland", "41051", "portland", "sinclair", "regional_outlet", ""),
    ("FOX12", "KPTV FOX 12 Oregon", "Portland", "41051", "portland", "gray", "regional_outlet", ""),
    ("KOIN", "KOIN 6", "Portland", "41051", "portland", "nexstar", "regional_outlet", "No streams on record."),
    ("OPB", "Oregon Public Broadcasting", "Portland", "41051", "portland", "public", "regional_outlet", ""),
    ("ORSOS", "Oregon Secretary of State", "Salem", "41047", "salem", "gov", "official", "Streamed 1 hour before scrape; active."),
])
S["42"] = ("PA", [
    ("FOX29", "FOX 29 Philadelphia", "Philadelphia", "42101", "philadelphia", "fox_oo", "regional_outlet", "FOX LOCAL Philadelphia 24/7 stream."),
    ("6abc__1", "6abc Philadelphia", "Philadelphia", "42101", "philadelphia", "abc_oo", "regional_outlet", "24/7 stream."),
    ("CBSPhiladelphia", "CBS Philadelphia", "Philadelphia", "42101", "philadelphia", "cbs_oo", "regional_outlet", ""),
    ("NBC10", "NBC10 Philadelphia", "Philadelphia", "42101", "philadelphia", "nbc_oo", "regional_outlet", "24/7 streaming channel."),
    ("WTAE", "WTAE-TV Pittsburgh", "Pittsburgh", "42003", "pittsburgh", "hearst", "regional_outlet", ""),
    ("CBSPittsburgh", "CBS Pittsburgh (KDKA)", "Pittsburgh", "42003", "pittsburgh", "cbs_oo", "regional_outlet", ""),
    ("WPXI__1", "WPXI-TV", "Pittsburgh", "42003", "pittsburgh", "cox", "regional_outlet", ""),
    ("WGAL", "WGAL", "Lancaster", "42071", "lancaster", "hearst", "regional_outlet", ""),
    ("FOX43", "FOX43 (WPMT)", "York", "42133", "york", "tegna", "regional_outlet", ""),
    ("PCN__1", "Pennsylvania Cable Network (PCN)", "Harrisburg", "42043", "harrisburg", "public", "regional_outlet", "Statewide public-affairs network."),
    ("abc27", "abc27 (WHTM)", "Harrisburg", "42043", "harrisburg", "nexstar", "regional_outlet", "No streams on record."),
    ("PhillyVotes_alt", "Philadelphia City Commissioners", "Philadelphia", "42101", "philadelphia", "gov", "official", "Streams election warehouse/tabulation live."),
    ("PADOS", "Pennsylvania Department of State", "Harrisburg", "42043", "harrisburg", "gov", "official", "No streams on record."),
])
S["44"] = ("RI", [
    ("WPRI__1", "WPRI 12", "Providence", "44007", "providence", "nexstar", "regional_outlet", ""),
    ("WJAR__1", "NBC 10 WJAR", "Providence", "44007", "providence", "sinclair", "regional_outlet", ""),
    ("ABC6RI__1", "Coastal ABC (WLNE ABC6)", "Providence", "44007", "providence", "standard", "regional_outlet", ""),
    ("RIPBS__1", "Ocean State Media (Rhode Island PBS)", "Providence", "44007", "providence", "public", "regional_outlet", "No streams on record."),
])
S["45"] = ("SC", [
    ("WIS__1", "WIS News 10", "Columbia", "45079", "columbia", "gray", "regional_outlet", "'South Carolina Election Night 2026: Live Results' scheduled."),
    ("WLTX__r4", "News 19 WLTX", "Columbia", "45079", "columbia", "tegna", "regional_outlet", ""),
    ("WYFF__1", "WYFF News 4", "Greenville", "45045", "greenville", "hearst", "regional_outlet", ""),
    ("ABCNews4__1", "ABC News 4 (WCIV)", "Charleston", "45019", "charleston", "sinclair", "regional_outlet", ""),
    ("FOXCarolina__1", "FOX Carolina", "Greenville", "45045", "greenville", "gray", "regional_outlet", ""),
    ("Live5__2", "Live 5 News (WCSC)", "Charleston", "45019", "charleston", "gray", "regional_outlet", "No streams on record."),
])
S["46"] = ("SD", [
    ("KELO__r3_2", "KELOLAND News", "Sioux Falls", "46099", "sioux-falls", "nexstar", "regional_outlet", ""),
    ("DakotaNewsNow__1", "Dakota News Now (KSFY/KDLT)", "Sioux Falls", "46099", "sioux-falls", "gray", "regional_outlet", ""),
    ("NewsCenter1", "NewsCenter1 (KNBN)", "Rapid City", "46103", "rapid-city", "indep", "regional_outlet", "Many live webcams; channel_live may resolve to a cam."),
    ("SDSOS__1", "South Dakota Secretary of State", "Pierre", "46065", "pierre", "gov", "official", "No streams on record."),
])
S["47"] = ("TN", [
    ("WSMV", "WSMV 4", "Nashville", "47037", "nashville", "gray", "regional_outlet", "Many live cams; channel_live may resolve to a cam."),
    ("FOX17__3", "FOX 17 Nashville (WZTV)", "Nashville", "47037", "nashville", "sinclair", "regional_outlet", ""),
    ("NewsChannel5__1", "NewsChannel 5 (WTVF)", "Nashville", "47037", "nashville", "scripps", "regional_outlet", "24/7 stream."),
    ("ActionNews5", "Action News 5 (WMC)", "Memphis", "47157", "memphis", "gray", "regional_outlet", ""),
    ("WBIR__3", "WBIR Channel 10", "Knoxville", "47093", "knoxville", "tegna", "regional_outlet", ""),
    ("WATE__1", "WATE 6 On Your Side", "Knoxville", "47093", "knoxville", "nexstar", "regional_outlet", ""),
    ("WVLT__1", "WVLT News", "Knoxville", "47093", "knoxville", "gray", "regional_outlet", ""),
    ("WREG", "WREG News Channel 3", "Memphis", "47157", "memphis", "nexstar", "regional_outlet", "No streams on record."),
    ("WKRN__1", "WKRN News 2", "Nashville", "47037", "nashville", "nexstar", "regional_outlet", "No streams on record."),
    ("TNSOS", "Tennessee Secretary of State", "Nashville", "47037", "nashville", "gov", "official", "Rarely streams."),
])
S["48"] = ("TX", [
    ("FOX4", "FOX 4 Dallas-Fort Worth", "Dallas", "48113", "dallas", "fox_oo", "regional_outlet", "'Texas 2026 Midterm Election' live; FOX LOCAL Dallas 24/7."),
    ("CBSTexas", "CBS News Texas (KTVT)", "Dallas", "48113", "dallas", "cbs_oo", "regional_outlet", "'Texas 2026 midterm election coverage' scheduled."),
    ("KHOU", "KHOU 11", "Houston", "48201", "houston", "tegna", "regional_outlet", ""),
    ("ABC13", "ABC13 Houston", "Houston", "48201", "houston", "abc_oo", "regional_outlet", "24/7 stream plus webcams."),
    ("FOX26", "FOX 26 Houston", "Houston", "48201", "houston", "fox_oo", "regional_outlet", "'Election Night Unfiltered' scheduled; FOX LOCAL Houston 24/7."),
    ("WFAA_alt", "WFAA", "Dallas", "48113", "dallas", "tegna", "regional_outlet", "Midterm election updates live."),
    ("KPRC", "KPRC 2 Click2Houston", "Houston", "48201", "houston", "graham", "regional_outlet", ""),
    ("FOX7Austin", "FOX 7 Austin", "Austin", "48453", "austin", "fox_oo", "regional_outlet", "FOX LOCAL Austin 24/7."),
    ("KVUE__1", "KVUE", "Austin", "48453", "austin", "tegna", "regional_outlet", ""),
    ("KXAN__2", "KXAN", "Austin", "48453", "austin", "nexstar", "regional_outlet", ""),
    ("KSAT__1", "KSAT 12", "San Antonio", "48029", "san-antonio", "graham", "regional_outlet", "'KSAT's election night coverage' scheduled."),
    ("KENS5", "KENS 5", "San Antonio", "48029", "san-antonio", "tegna", "regional_outlet", ""),
    ("TexasTribune", "The Texas Tribune", "Austin", "48453", "austin", "nonprofit", "regional_outlet", ""),
    ("NBCDFW", "NBC 5 Dallas-Fort Worth", "Dallas", "48113", "dallas", "nbc_oo", "regional_outlet", "Rarely streams."),
    ("News4SA", "News 4 San Antonio (WOAI)", "San Antonio", "48029", "san-antonio", "sinclair", "regional_outlet", "No streams on record."),
    ("TXSOS__1", "Texas Secretary of State", "Austin", "48453", "austin", "gov", "official", "No streams on record."),
])
S["49"] = ("UT", [
    ("KSL_alt", "KSL 5 TV", "Salt Lake City", "49035", "salt-lake-city", "bonneville", "regional_outlet", "'Decision 2026 - Midterms Election Coverage' live."),
    ("KUTV", "KUTV 2News", "Salt Lake City", "49035", "salt-lake-city", "sinclair", "regional_outlet", ""),
    ("FOX13Utah__1", "FOX 13 News Utah", "Salt Lake City", "49035", "salt-lake-city", "scripps", "regional_outlet", "24/7 stream."),
    ("ABC4Utah", "ABC4 Utah", "Salt Lake City", "49035", "salt-lake-city", "nexstar", "regional_outlet", ""),
    ("PBSUtah", "PBS Utah", "Salt Lake City", "49035", "salt-lake-city", "public", "regional_outlet", ""),
    ("UTELECT", "Elections Utah (Lt. Governor's Office)", "Salt Lake City", "49035", "salt-lake-city", "gov", "official", "No streams on record."),
])
S["50"] = ("VT", [
    ("WCAX__1", "WCAX Channel 3 News", "Burlington", "50007", "burlington", "gray", "regional_outlet", "Many live cams; channel_live may resolve to a cam."),
    ("NBC5__1", "NBC5 (WPTZ)", None, None, None, "hearst", "regional_outlet", "Plattsburgh NY based; covers Vermont."),
    ("VermontPublic", "Vermont Public", None, None, None, "public", "regional_outlet", ""),
    ("VTDigger", "VTDigger", "Montpelier", "50023", "montpelier", "nonprofit", "regional_outlet", ""),
    ("VTSOS__1", "Vermont Secretary of State", "Montpelier", "50023", "montpelier", "gov", "official", "No streams on record."),
])
S["51"] = ("VA", [
    ("WTVR__1", "WTVR CBS 6", "Richmond", "51760", "richmond", "scripps", "regional_outlet", "24/7 stream."),
    ("NBC12__1", "NBC12 (WWBT)", "Richmond", "51760", "richmond", "gray", "regional_outlet", ""),
    ("WRIC__3", "WRIC ABC 8News", "Richmond", "51760", "richmond", "nexstar", "regional_outlet", ""),
    ("WTKR", "WTKR News 3", "Norfolk", "51710", "norfolk", "scripps", "regional_outlet", "24/7 stream."),
    ("WAVY", "WAVY TV 10", "Portsmouth", "51740", "portsmouth", "nexstar", "regional_outlet", ""),
    ("13NewsNow__r3_2", "13News Now (WVEC)", "Norfolk", "51710", "norfolk", "tegna", "regional_outlet", ""),
    ("WUSA9__1", "WUSA9 (Washington)", None, None, None, "tegna", "regional_outlet", "DC market covers Northern Virginia; 'Mapping the Midterms' live."),
    ("FOX5DC", "FOX 5 Washington DC", None, None, None, "fox_oo", "regional_outlet", "DC market; DC/MD/VA midterm stream scheduled."),
    ("WJLA__1", "7News DC (WJLA)", None, None, None, "sinclair", "regional_outlet", "DC market (WJLA is licensed to Arlington, VA)."),
    ("VPM", "VPM", "Richmond", "51760", "richmond", "public", "regional_outlet", ""),
    ("VAELECT__1", "Virginia Department of Elections (ELECT)", "Richmond", "51760", "richmond", "gov", "official", "Occasional streams."),
])
S["53"] = ("WA", [
    ("KING5", "KING 5 Seattle", "Seattle", "53033", "seattle", "tegna", "regional_outlet", ""),
    ("KOMO", "KOMO News", "Seattle", "53033", "seattle", "sinclair", "regional_outlet", "24/7 stream."),
    ("FOX13Seattle", "FOX 13 Seattle", "Seattle", "53033", "seattle", "fox_oo", "regional_outlet", "FOX LOCAL Seattle 24/7."),
    ("KREM__1", "KREM 2 News", "Spokane", "53063", "spokane", "tegna", "regional_outlet", ""),
    ("KULR8__1", "NonStop Local (KHQ Spokane)", "Spokane", "53063", "spokane", "cowles", "regional_outlet", "Shared NonStop Local channel; KHQ election-day coverage live."),
    ("KXLY__1", "4 News Now (KXLY)", "Spokane", "53063", "spokane", "morgan_murphy", "regional_outlet", "Last stream years ago."),
    ("KIRO7", "KIRO 7 News", "Seattle", "53033", "seattle", "cox", "regional_outlet", "Last stream years ago."),
    ("TVW__1", "TVW (Washington State Public Affairs Network)", "Olympia", "53067", "olympia", "public", "official", "State public-affairs network; streams regularly."),
    ("WASOS__1", "Washington Secretary of State", "Olympia", "53067", "olympia", "gov", "official", "No streams on record."),
])
S["54"] = ("WV", [
    ("WVMetroNews__1", "MetroNews Television (WV MetroNews)", "Morgantown", "54061", "morgantown", "indep", "regional_outlet", "'Decision 26: West Virginia General Election' scheduled."),
    ("WCHS__1", "WCHS-TV Eyewitness News", "Charleston", "54039", "charleston", "sinclair", "regional_outlet", ""),
    ("WSAZ__1", "WSAZ NewsChannel 3", "Huntington", "54011", "huntington", "gray", "regional_outlet", ""),
    ("WVVA", "WVVA", "Bluefield", "54055", "bluefield", "quincy", "regional_outlet", "No streams on record."),
    ("WVPB", "West Virginia Public Broadcasting", "Charleston", "54039", "charleston", "public", "regional_outlet", "Last stream years ago."),
    ("WVSOS__1", "West Virginia Secretary of State", "Charleston", "54039", "charleston", "gov", "official", "Rarely streams."),
])
S["55"] = ("WI", [
    ("FOX6", "FOX6 News Milwaukee", "Milwaukee", "55079", "milwaukee", "fox_oo", "regional_outlet", "'Election Day 2026' live; FOX LOCAL Milwaukee 24/7."),
    ("WISN__1", "WISN 12 News", "Milwaukee", "55079", "milwaukee", "hearst", "regional_outlet", ""),
    ("TMJ4_alt", "TMJ4 News", "Milwaukee", "55079", "milwaukee", "scripps", "regional_outlet", "24/7 stream."),
    ("WISC_alt", "Channel 3000 / News 3 Now (WISC)", "Madison", "55025", "madison", "morgan_murphy", "regional_outlet", "Channel3000+ live."),
    ("NBC15__1", "WMTV NBC15", "Madison", "55025", "madison", "gray", "regional_outlet", "Last stream years ago."),
    ("CBS58__1", "CBS 58 (WDJT)", "Milwaukee", "55079", "milwaukee", "weigel", "regional_outlet", "No streams on record."),
    ("PBSWisconsin", "PBS Wisconsin", "Madison", "55025", "madison", "public", "regional_outlet", ""),
    ("WEC_alt", "Wisconsin Elections Commission", "Madison", "55025", "madison", "gov", "official", "Last stream years ago."),
    ("WisconsinEye__2", "WisconsinEye", "Madison", "55025", "madison", "public", "official", "Channel title 'Wiseye' only; unverified, no streams on record."),
])
S["56"] = ("WY", [
    ("CowboyStateDaily", "Cowboy State Daily", "Cheyenne", "56021", "cheyenne", "nonprofit", "regional_outlet", "Daily live show."),
    ("WyomingNewsNow", "Wyoming News Now (KGWN/KCWY)", "Cheyenne", "56021", "cheyenne", "gray", "regional_outlet", "No streams on record."),
    ("WyomingPBS", "Wyoming PBS", None, None, None, "public", "regional_outlet", ""),
    ("OilCityNews", "Oil City News", "Casper", "56025", "casper", "indep", "regional_outlet", ""),
    ("WYSOS", "Wyoming Secretary of State", "Cheyenne", "56021", "cheyenne", "gov", "official", "Occasional streams."),
])

# State-level kind:video entries: fips -> [(videoId, result_key, title, status, city_tuple_or_None)]
# city tuple = (city, county_fips, slug)
SV = collections.defaultdict(list)
def sv(fips, vid, key, title, status, city=None):
    SV[fips].append((vid, key, title, status, city))

sv("02", "VEXJglQIunc", "AlaskasNewsSource", "Alaska Decides", "live", ("Anchorage","02020","anchorage"))
sv("02", "CJowKhcH0W0", "AlaskaPublic", "Election Night Live 2026", "upcoming", ("Anchorage","02020","anchorage"))
sv("04", "WHGEW-lW72g", "FOX10Phoenix", "LIVE: Election Day special - what you need to know | FOX 10 Talks", "upcoming", ("Phoenix","04013","phoenix"))
sv("04", "qilQmQW8Dqg", "FOX10Phoenix", "LIVE NEWS: FOX LOCAL Phoenix 24/7 Live Stream", "live", ("Phoenix","04013","phoenix"))
sv("04", "aYkkvQioltg", "ABC15", "LIVE | ABC15 Arizona latest news, weather, investigations & more", "live", ("Phoenix","04013","phoenix"))
sv("04", "lsBwfXNXhpk", "KGUN", "KGUN News and Weather", "live", ("Tucson","04019","tucson"))
sv("06", "ZG06YQpZ7LE", "KCRA", "KCRA 3 Election Night in California", "upcoming", ("Sacramento","06067","sacramento"))
sv("06", "8u8pQ_uLGjo", "FOXLA", "LIVE NEWS: FOX LOCAL Los Angeles 24/7 Live Stream", "live", ("Los Angeles","06037","los-angeles"))
sv("06", "s3iVFJoxrYc", "ABC7LA", "LIVE: ABC7 Eyewitness News", "live", ("Los Angeles","06037","los-angeles"))
sv("06", "YUJl2vWNsWU", "ABC7News", "LIVE: ABC7 News (Bay Area)", "live", ("San Francisco","06075","san-francisco"))
sv("06", "rM8rkzxKZRs", "KTVU", "LIVE NEWS: FOX LOCAL San Francisco 24/7 Live Stream", "live", ("San Francisco","06075","san-francisco"))
sv("08", "B31ZJcPl_3Y", "9NEWS", "9NEWS Live Election Night | Results and analysis", "upcoming", ("Denver","08031","denver"))
sv("08", "7NRC9fsEqHk", "Denver7", "Denver 7 News and Weather", "live", ("Denver","08031","denver"))
sv("09", "WPq27RTEPUk", "NBCConnecticut", "LIVE: Connecticut Election Night 2026 | Results & Expert Analysis with NBC Connecticut", "live", ("Hartford","09003","hartford"))
sv("10", "sNi1KbGCJ3o", "6abc__1", "LIVE: 6abc Philadelphia", "live", None)
sv("10", "8uysx5cz8qI", "NBC10", "LIVE: NBC10 Philadelphia News 24/7 Streaming Channel", "live", None)
sv("12", "WsYs9oHzLLw", "WKMG", "LIVE: Election Day 2026 | Tracking Results in Florida", "upcoming", ("Orlando","12095","orlando"))
sv("12", "OY1dcr-zr6Q", "FOX13Tampa__1", "LIVE NEWS: FOX LOCAL Tampa Bay 24/7 Live Stream", "live", ("Tampa","12057","tampa"))
sv("12", "4ttPNncK6T0", "WPLG", "Local 10 News South Florida, Miami, Fort Lauderdale and the Keys", "live", ("Miami","12086","miami"))
sv("12", "8FOpii0O2mU", "FOX35__1", "LIVE NEWS: FOX LOCAL Orlando 24/7 Live Stream", "live", ("Orlando","12095","orlando"))
sv("12", "MJKuobL_VjM", "ABCActionNews__1", "LIVE | Tampa Bay 28+ News 24/7", "live", ("Tampa","12057","tampa"))
sv("13", "Fy4g8MZRHLs", "FOX5Atlanta", "LIVE | Election Day 2026: Polls open across Georgia in high-stakes races for Governor and Senate", "live", ("Atlanta","13121","atlanta"))
sv("13", "egVaFAi74cI", "FOX5Atlanta", "LIVE NEWS: FOX LOCAL Atlanta 24/7 Live Stream", "live", ("Atlanta","13121","atlanta"))
sv("16", "5lwJKPbVtVs", "IdahoNews6__1", "KIVI News and Weather", "live", ("Boise","16001","boise"))
sv("17", "KNOaxcgjx_M", "FOX32", "LIVE | Illinois 2026 midterm election results and analysis - Tuesday, Nov. 03, 2026", "upcoming", ("Chicago","17031","chicago"))
sv("17", "sj2cWegO1OU", "ABC7Chicago", "LIVE Updates for midterm Election Day 2026 across country, Chicago area", "live", ("Chicago","17031","chicago"))
sv("17", "E2gGh3BEhEA", "FOX32", "LIVE NEWS: FOX LOCAL Chicago 24/7 Live Stream", "live", ("Chicago","17031","chicago"))
sv("20", "KB2pUA7XZWY", "KCTV", "WATCH NOW: 2026 Live Election Coverage (KCTV5)", "live", None)
sv("20", "BtatPWA7duA", "WIBW", "Who are the candidates? (WIBW)", "live", ("Topeka","20177","topeka"))
sv("21", "uwxPRMhp7h8", "LEX18__1", "WLEX News and Weather", "live", ("Lexington","21067","lexington"))
sv("24", "bNSX9BadnF8", "FOX5DC", "LIVE: Midterm Elections 2026 in DC, Maryland and Virginia", "upcoming", None)
sv("24", "egVs_TuyhCs", "WUSA9__1", "Mapping the Midterms: 2026 Elections Special Coverage", "live", None)
sv("24", "QnMg1WqFhhg", "WMAR", "LIVE: WMAR 2 News | Local News, Weather & Breaking News", "live", ("Baltimore","24510","baltimore"))
sv("26", "OoxiETO1sc0", "FOX2Detroit", "Live: Election results (FOX 2 Detroit)", "upcoming", ("Detroit","26163","detroit"))
sv("26", "-IJAovYoED8", "CBSDetroit", "Tracking Michigan's 2026 midterm election results", "upcoming", ("Detroit","26163","detroit"))
sv("26", "riy2akaZ0wY", "WOODTV__1", "Election Night in Michigan (WOOD TV8)", "upcoming", ("Grand Rapids","26081","grand-rapids"))
sv("26", "_Yf-hAf3mvM", "FOX2Detroit", "LIVE NEWS: FOX LOCAL Detroit 24/7 Live Stream", "live", ("Detroit","26163","detroit"))
sv("26", "EkLtQBWkDsE", "WXYZ__1", "WXYZ Detroit News and Weather", "live", ("Detroit","26163","detroit"))
sv("27", "OoKsD4_T3fg", "FOX9", "LIVE | Minnesota election coverage", "live", ("Minneapolis","27053","minneapolis"))
sv("27", "xXSyunLBBuE", "CBSMinnesota_alt", "LIVE Midterm Election Special: Minnesota election results, analysis and more", "upcoming", ("Minneapolis","27053","minneapolis"))
sv("27", "_Lc6ZDjhHuo", "KSTP__1", "KSTP 5 Eyewitness News Streaming Channel", "live", ("Minneapolis","27053","minneapolis"))
sv("29", "KB2pUA7XZWY", "KCTV", "WATCH NOW: 2026 Live Election Coverage (KCTV5)", "live", ("Kansas City","29095","kansas-city"))
sv("30", "MUgKjtycTII", "KTVQ__1", "LIVE: KTVQ News | Local News, Weather & Breaking News", "live", ("Billings","30111","billings"))
sv("30", "Wp8F51EVoHI", "KULR8__1", "24/7 Montana News, Sports and Weather | NonStop Local", "live", ("Billings","30111","billings"))
sv("31", "tjk6v7DXmMo", "KMTV__1", "LIVE: KMTV 3 News Now", "live", ("Omaha","31055","omaha"))
sv("32", "3BY89abBH30", "ClarkCountyNV", "ClarkCountyNV Live Stream", "live", ("Las Vegas","32003","las-vegas"))
sv("32", "xliFgAuk4dU", "KTNV", "KTNV Las Vegas News And Weather", "live", ("Las Vegas","32003","las-vegas"))
sv("34", "ePc1sgl-o1c", "FOX5NY", "LIVE: Election Night 2026 in NYC & NJ", "upcoming", None)
sv("34", "7iHbVO8oAJM", "FOX5NY", "LIVE: NYC & NJ election results, full candidate speeches, analysis, more", "upcoming", None)
sv("34", "JEtvLd4B-AY", "News12", "LIVE: News 12 New York - Breaking News, Weather & Local Stories (NY, NJ, CT)", "live", None)
sv("36", "74gIffescgE", "CBSNewYork", "Watch Live: New York Election Night 2026 team coverage", "upcoming", ("New York","36061","new-york"))
sv("36", "ePc1sgl-o1c", "FOX5NY", "LIVE: Election Night 2026 in NYC & NJ", "upcoming", ("New York","36061","new-york"))
sv("36", "rfVMd_XrKJw", "NY1_alt", "New York Election Coverage on NY1 | Midterm Updates, Results & Speeches", "live", ("New York","36061","new-york"))
sv("36", "VrhYz4CL70I", "ABC7NY", "LIVE: ABC 7 New York Eyewitness News", "live", ("New York","36061","new-york"))
sv("36", "ADXWeM9wsDw", "FOX5NY", "LIVE NEWS: FOX LOCAL NY 24/7 Live Stream", "live", ("New York","36061","new-york"))
sv("37", "8RCiMfJuhNY", "CBS17", "2026 Midterm Election Live Coverage (CBS 17)", "upcoming", ("Raleigh","37183","raleigh"))
sv("37", "lchaLqnOWsg", "PBSNC__1", "11/03/2026: North Carolina State Board of Elections", "live", None)
sv("37", "ueregi3uBNQ", "ABC11__1", "LIVE: ABC11 Raleigh-Durham", "live", ("Raleigh","37183","raleigh"))
sv("37", "PeTHS4MivaE", "WRAL__1", "Local & National News Updates | North Carolina Forecast (WRAL)", "live", ("Raleigh","37183","raleigh"))
sv("39", "-7CZXVVCZnM", "WCPO", "LIVE: WCPO | Local News, Weather & Breaking News", "live", ("Cincinnati","39061","cincinnati"))
sv("40", "44nvRDCFob0", "News9__1", "News 9 | 24/7 Streaming", "live", ("Oklahoma City","40109","oklahoma-city"))
sv("40", "fRqYSbxV5YQ", "News9__1", "News On 6 | 24/7 Streaming", "live", ("Tulsa","40143","tulsa"))
sv("40", "h2VDPvmtgXI", "KJRH__1", "LIVE: KJRH 2 News Oklahoma", "live", ("Tulsa","40143","tulsa"))
sv("42", "k1RJgtwl0Mc", "PhillyVotes_alt", "2026 General Election Warehouse (Philadelphia City Commissioners)", "live", ("Philadelphia","42101","philadelphia"))
sv("42", "Yo5G6C9Qex8", "FOX29", "LIVE NEWS: FOX LOCAL Philadelphia 24/7 Live Stream", "live", ("Philadelphia","42101","philadelphia"))
sv("42", "sNi1KbGCJ3o", "6abc__1", "LIVE: 6abc Philadelphia", "live", ("Philadelphia","42101","philadelphia"))
sv("42", "8uysx5cz8qI", "NBC10", "LIVE: NBC10 Philadelphia News 24/7 Streaming Channel", "live", ("Philadelphia","42101","philadelphia"))
sv("45", "ttjj8aA4YJ0", "WIS__1", "South Carolina Election Night 2026: Live Results | WIS 10", "upcoming", ("Columbia","45079","columbia"))
sv("47", "hfhgKXErfno", "NewsChannel5__1", "WTVF News/Weather (NewsChannel 5)", "live", ("Nashville","47037","nashville"))
sv("48", "z_uTep0t11A", "FOX4", "LIVE: Texas 2026 Midterm Election | FOX 4 News", "live", ("Dallas","48113","dallas"))
sv("48", "8FukFv0MAkI", "CBSTexas", "Live: Texas 2026 midterm election coverage (CBS News Texas)", "upcoming", ("Dallas","48113","dallas"))
sv("48", "G9EfkbOHMXg", "FOX26", "LIVE: Election Night Unfiltered (FOX 26 Houston)", "upcoming", ("Houston","48201","houston"))
sv("48", "J68159WD_cg", "WFAA_alt", "LIVE: WFAA Midterm Election Update", "live", ("Dallas","48113","dallas"))
sv("48", "MyKb4VVqBKM", "KSAT__1", "WATCH LIVE: KSAT's election night coverage", "upcoming", ("San Antonio","48029","san-antonio"))
sv("48", "1fcNf0CnHb8", "ABC13", "ABC13 Houston | Live Local News and Weather", "live", ("Houston","48201","houston"))
sv("48", "og9_jHrGwQg", "FOX26", "LIVE NEWS: FOX LOCAL Houston 24/7 Live Stream", "live", ("Houston","48201","houston"))
sv("48", "HkfKsRa9qnE", "FOX4", "LIVE NEWS: FOX LOCAL Dallas 24/7 Live Stream", "live", ("Dallas","48113","dallas"))
sv("48", "4qiWy7ohNUI", "FOX7Austin", "LIVE NEWS: FOX LOCAL Austin 24/7 Live Stream", "live", ("Austin","48453","austin"))
sv("48", "5687mOKVa0U", "KENS5", "Bexar County Election Day update (KENS 5)", "upcoming", ("San Antonio","48029","san-antonio"))
sv("49", "rd2Y-ZvHiYg", "KSL_alt", "LIVE: Decision 2026 - Midterms Election Coverage (KSL)", "live", ("Salt Lake City","49035","salt-lake-city"))
sv("49", "d-3QveG_Ilg", "FOX13Utah__1", "FOX 13 News Live (Utah)", "live", ("Salt Lake City","49035","salt-lake-city"))
sv("51", "bNSX9BadnF8", "FOX5DC", "LIVE: Midterm Elections 2026 in DC, Maryland and Virginia", "upcoming", None)
sv("51", "egVs_TuyhCs", "WUSA9__1", "Mapping the Midterms: 2026 Elections Special Coverage", "live", None)
sv("51", "6UMOP-jWXjY", "WTVR__1", "LIVE: WTVR CBS 6 News", "live", ("Richmond","51760","richmond"))
sv("51", "itfdTuxFUFg", "WTKR", "LIVE: WTKR News 3", "live", ("Norfolk","51710","norfolk"))
sv("53", "PqMc7WOBVJs", "KOMO", "LIVE: KOMO 4 News", "live", ("Seattle","53033","seattle"))
sv("53", "BZ2eIuu0m_k", "FOX13Seattle", "LIVE NEWS: FOX LOCAL Seattle 24/7 Live Stream", "live", ("Seattle","53033","seattle"))
sv("53", "2jRdUpTDR1M", "KULR8__1", "LIVE Election Day Coverage with NonStop Local KHQ News Spokane", "live", ("Spokane","53063","spokane"))
sv("54", "H1sxZcCJKsc", "WVMetroNews__1", "Decision 26: West Virginia General Election | November 3, 2026", "upcoming", ("Morgantown","54061","morgantown"))
sv("55", "MD5gjfL7viI", "FOX6", "FOX6 NOW: Election Day 2026; everything you need to know", "live", ("Milwaukee","55079","milwaukee"))
sv("55", "DwrIZbw5oig", "FOX6", "LIVE NEWS: FOX LOCAL Milwaukee 24/7 Live Stream", "live", ("Milwaukee","55079","milwaukee"))
sv("55", "QtxCGe9J9fw", "TMJ4_alt", "TMJ 4 News and Weather", "live", ("Milwaukee","55079","milwaukee"))
sv("55", "ZkDH8J-QYUQ", "WISC_alt", "Watch Channel3000+", "live", ("Madison","55025","madison"))

# ---------- build ----------
videos = []
used_ids = set()
def embed_channel(cid): return f"https://www.youtube.com/embed/live_stream?channel={cid}&autoplay=1&mute=1&playsinline=1"
def link_channel(cid): return f"https://www.youtube.com/channel/{cid}/live"
def embed_video(v): return f"https://www.youtube.com/embed/{v}?autoplay=1&mute=1&playsinline=1"
def link_video(v): return f"https://www.youtube.com/watch?v={v}"

def add(entry):
    if entry["id"] in used_ids:
        raise SystemExit("dup id " + entry["id"])
    used_ids.add(entry["id"]); videos.append(entry)

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

counts = collections.Counter()
def mk(kind, scope_level, jkey, key, outlet, tier, group, note, loc_conf, rank, vid=None, vtitle=None, vstatus=None, state=None):
    c = ch(key)
    base_id = f"vid-{scope_level}-{jkey.replace(':','-')}-{slug(key)}" + (f"-{vid}" if vid else "")
    e = {
        "id": base_id,
        "platform": "youtube",
        "kind": kind,
        "youtube_channel_id": c["id"],
        "youtube_video_id": vid,
        "title": vtitle if vid else f"{outlet} live",
        "channel": c["title"],
        "outlet": outlet,
        "tier": tier,
        "live": None,
        "started_at": None,
        "scope": {"level": scope_level, "jkey": jkey},
        "state": state,
        "location_confidence": loc_conf,
        "embed_url": embed_video(vid) if vid else embed_channel(c["id"]),
        "link_url": link_video(vid) if vid else link_channel(c["id"]),
        "muted": True,
        "rank": rank,
        "evidence": {
            "owner_group": group,
            "live_at_scrape": (vstatus == "live") if vid else c["live_now"],
            "scheduled_at_scrape": (vstatus == "upcoming") if vid else None,
            "streams_listed": c["n_streams"],
            "last_streamed": c["last_streamed"],
            "note": note or None,
        },
    }
    counts[(scope_level, tier, kind)] += 1
    add(e)

# National
rank = 1
for vid, key, title, status in NATIONAL_VIDEOS:
    outlet = next(o for k, o, g, n in NATIONAL if k == key)
    group = next(g for k, o, g, n in NATIONAL if k == key)
    mk("video", "national", "US", key, outlet, "major_outlet", group, "Scheduled/live election-night stream found on channel page at scrape time.", "exact", rank, vid, title, status); rank += 1
for key, outlet, group, note in NATIONAL:
    mk("channel_live", "national", "US", key, outlet, "major_outlet", group, note, "exact", rank); rank += 1
for key, outlet, group, note in NATIONAL_OFFICIAL:
    mk("channel_live", "national", "US", key, outlet, "official", group, note, "exact", rank); rank += 1

# States
for fips, (postal, picks) in sorted(S.items()):
    rank = 1
    # videos first (election-specific/scheduled, then 24/7)
    seen_v = set()
    vids = SV.get(fips, [])
    vids_sorted = sorted(vids, key=lambda t: (0 if re.search(r"elect|midterm|decision|results|candidates|vote", t[2], re.I) else 1, 0 if t[3]=="upcoming" else 1))
    for vid, key, title, status, city in vids_sorted:
        if vid in seen_v: continue
        seen_v.add(vid)
        pk = next((p for p in picks if p[0] == key), None)
        outlet = pk[1] if pk else ch(key)["title"]; tier = pk[6] if pk else "regional_outlet"; group = pk[5] if pk else ""
        loc = "city" if city else ("inferred" if pk and pk[2] is None else "state")
        mk("video", "state", fips, key, outlet, tier, group, "Scheduled/live stream found on channel page at scrape time.", loc, rank, vid, title, status, postal); rank += 1
    for key, outlet, city, cfips, cslug, group, tier, note in picks:
        loc = "city" if city else "inferred"
        if city and cfips and cfips[:2] != fips: loc = "inferred"   # DC / out-of-state market stations
        mk("channel_live", "state", fips, key, outlet, tier, group, note, loc, rank, state=postal); rank += 1

# City entries (second entry for stations clearly based in a city)
city_rank = collections.Counter()
for fips, (postal, picks) in sorted(S.items()):
    # videos with city
    for vid, key, title, status, city in SV.get(fips, []):
        if not city: continue
        cname, cfips, cslug = city
        jkey = f"{cfips}:{cslug}"
        pk = next((p for p in picks if p[0] == key), None)
        outlet = pk[1] if pk else ch(key)["title"]; tier = pk[6] if pk else "regional_outlet"; group = pk[5] if pk else ""
        city_rank[jkey] += 1
        eid_check = f"vid-city-{jkey.replace(':','-')}-{slug(key)}-{vid}"
        if eid_check in used_ids: continue
        mk("video", "city", jkey, key, outlet, tier, group, "Scheduled/live stream found on channel page at scrape time.", "city", city_rank[jkey], vid, title, status, postal)
    for key, outlet, city, cfips, cslug, group, tier, note in picks:
        if not city or not cfips: continue
        jkey = f"{cfips}:{cslug}"
        eid_check = f"vid-city-{jkey.replace(':','-')}-{slug(key)}"
        if eid_check in used_ids: continue
        city_rank[jkey] += 1
        mk("channel_live", "city", jkey, key, outlet, tier, group, note, "city", city_rank[jkey], state=postal)

json.dump(videos, open(OUT, "w"), indent=1)

# ---------- meta ----------
by_level = collections.Counter(v["scope"]["level"] for v in videos)
by_tier = collections.Counter((v["scope"]["level"], v["tier"]) for v in videos)
by_kind = collections.Counter((v["scope"]["level"], v["kind"]) for v in videos)
states_covered = sorted({v["scope"]["jkey"] for v in videos if v["scope"]["level"] == "state"})
cities_covered = sorted({v["scope"]["jkey"] for v in videos if v["scope"]["level"] == "city"})
meta = {
    "generated_at": NOW,
    "schema": "videos block, CONTRACT.md v1.0 (extra fields: outlet, state, evidence)",
    "method": [
        "Candidate handles per outlet were fetched from youtube.com/@handle/streams (plain curl, redirects followed); channel id taken from \"externalId\" in page HTML.",
        "Where a handle 404'd or resolved to an unrelated channel, the station's own website was scraped for its youtube.com link, and that link was resolved the same way.",
        "Each channel's /streams tab was parsed (ytInitialData lockupViewModel) to count listed streams, the most recent 'Streamed X ago' text, live badges, and scheduled streams; election-night streams found there are emitted as kind:'video' entries with the real videoId.",
        "channel_live entries use https://www.youtube.com/embed/live_stream?channel=<id>; note YouTube resolves this to ONE current live stream, so channels running several simultaneous streams (24/7 feed + webcams) may resolve to the wrong one - prefer the kind:'video' entry when present.",
        "Streaming evidence ('streams_listed', 'last_streamed', 'live_at_scrape') is from the scrape on " + NOW + " and is a proxy for whether the channel will stream election night.",
    ],
    "counts": {
        "total": len(videos),
        "by_level": dict(by_level),
        "by_level_tier": {f"{l}/{t}": n for (l, t), n in sorted(by_tier.items())},
        "by_level_kind": {f"{l}/{k}": n for (l, k), n in sorted(by_kind.items())},
        "states_with_entries": len(states_covered),
        "state_fips_covered": states_covered,
        "cities_covered": len(cities_covered),
    },
    "jkey_notes": [
        "Connecticut city entries use legacy county FIPS 09003 (Hartford) / 09009 (New Haven); CT switched to planning-region FIPS (091xx) in 2022 - remap if the TopoJSON uses the new codes.",
        "Virginia independent cities use their own FIPS (51760 Richmond, 51710 Norfolk, 51740 Portsmouth).",
        "DC-market stations (WUSA9, FOX 5 DC, WJLA, NBC4) appear under MD (24) and VA (51) with location_confidence 'inferred'; no DC jkey exists in the contract.",
        "Kansas City stations appear under both KS (20, inferred) and MO (29, city 29095:kansas-city).",
    ],
    "unresolved": {
        "no_channel_found_or_wrong_channel": [
            "KSHB 41 Kansas City (handle guesses hit unrelated channels; kshb.com has no YouTube link)",
            "WCBD News 2 Charleston SC (counton2.com rate-limited 429; handles 404)",
            "WSPA 7News Spartanburg (wspa.com 429; handles 404)",
            "WOWK 13 Charleston WV (wowktv.com 429; handles 404)",
            "KARK 4 Little Rock (kark.com 429; handles 404)",
            "WDAY Fargo (inforum.com has no link; handles 404)",
            "WTNH News 8 New Haven (wtnh.com 429; handles 404)",
            "FOX59 Indianapolis (fox59.com 429; handles 404)",
            "KOTA Rapid City (resolved to 'kotaTV' with no streams; unverified, omitted)",
            "SDPB (resolved to 'SDPBTV' with no streams; unverified, omitted)",
            "WOSU Columbus, ABC 6 Columbus (handles 404 / wrong channel)",
            "Univision Noticias (@uninoticias resolved to 'Uni News', 1 old stream; omitted as unverified)",
            "Decision Desk HQ (handle 404)",
            "EAC (U.S. Election Assistance Commission) (@EACgov 404)",
        ],
        "official_offices_not_found": [
            "Georgia Secretary of State (site 403; handles 404)",
            "Michigan Department of State (site 403; handles 404/wrong)",
            "Maine SOS", "New Hampshire SOS (handle resolves to unrelated 'XZ')", "Missouri SOS", "Mississippi SOS (unverified 'Ms. Sos' omitted)",
            "Rhode Island SOS (unrelated channel)", "Kentucky SOS (unverified 'kysos' omitted)", "Idaho SOS", "Montana SOS",
            "New Jersey Division of Elections", "Indiana SOS", "New Mexico SOS (unverified 'N M' omitted)", "Massachusetts Secretary of the Commonwealth",
            "South Carolina Election Commission", "Alaska Division of Elections", "Fulton County GA",
            "Arizona SOS institutional channel 'ArizonaSOS' (UC8e3Y7maTuKTerh4X_7A8jw) has no streams; the Secretary's own channel (Adrian Fontes) is used instead",
        ],
        "included_but_low_confidence": [
            "WisconsinEye -> channel titled only 'Wiseye' (UC7TTKDMD6Oqn311TWpLqhPg), no streams listed",
            "LiveNOW from FOX -> streams tab not enumerable by scraper (0 streams listed) though the channel streams constantly",
            "Stations marked 'No streams on record' have a valid channel id but no /streams history; they will likely render as a link card",
        ],
        "sites_rate_limited_429_nexstar": ["kark.com","fox16.com","kron4.com","wtnh.com","wfla.com","kdvr.com","khon2.com","fox59.com","who13.com","ksn.com","woodtv.com","fox2now.com","8newsnow.com","krqe.com","qcnews.com","kxnet.com","nbc4i.com","fox8.com","kfor.com","koin.com","phl17.com","abc27.com","wpri.com","wcbd/counton2.com","wspa.com","keloland.com","wkrn.com","wreg.com","fox13memphis.com","wate.com","kxan.com","mychamplainvalley.com","wric.com","wowktv.com"],
    },
    "sources": {
        "resolution_tables": ["/tmp/yt/results.tsv", "/tmp/yt/results2.tsv", "/tmp/yt/results3.tsv", "/tmp/yt/sitelinks.tsv", "/tmp/yt/allvideos.tsv"],
        "candidate_list": "/home/claude/election-dashboard/tools/candidates.tsv",
        "builder": "/home/claude/election-dashboard/tools/build_videos.py",
    },
}
json.dump(meta, open(META, "w"), indent=1)
print(json.dumps(meta["counts"], indent=1))
