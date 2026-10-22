#!/usr/bin/env python3
"""Refresh the site's YouTube data (channel stats, latest uploads and podcast episodes).

Run from anywhere:  python3 tools/update_youtube.py
Writes assets/data/youtube.js (loaded by index.html as window.MVS_YT) and caches channel avatars in assets/img/channels/.
If YouTube can't be reached, the existing JSON is kept untouched.
"""
import json, pathlib, re, sys, time, urllib.error, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets/data/youtube.js"
AVATARS = ROOT / "assets/img/channels"

# Main channel first. Edit this list to add/remove channels on the site.
CHANNELS = [
    "@MyVillageShow",
    "@MyVillageShowVlogs",
    "@kallivalli450",
    "@VillageShow-Mix",
    "@myvillageshowstream",
]
LATEST_VIDEOS = 9

# Podcast episodes are picked up from EVERY channel in CHANNELS: each channel's "podcast" search and newest
# uploads, plus the official podcast playlist (on the Vlogs channel), which isn't always kept up to date.
PODCAST_PLAYLIST = "PLqwv8aBwfwiq3aCGTua3nvi_FXfnRzx1g"
PODCAST_PLAYLIST_CHANNEL = "@MyVillageShowVlogs"
PODCAST_MIN_SECONDS = 20 * 60                 # full episodes only: skips trailers, clips and Shorts
PODCAST_EXCLUDE = ["anil geela", "అనిల్ జీల"]  # people no longer featured on the site
PODCAST_MAX = 16

# "Talk with Celebrity": celebrity, leader and official guests across all our channels, chosen by hand.
# Each entry: (video id, channel handle, words to find it in that channel's search, kind).
# Titles, views and lengths are refreshed from YouTube on every run.
CELEBRITY_TALKS = [
    ("6Q2cclAEZMc", "@kallivalli450", "Rana Daggubati", "celebrity"),
    ("xMTy77RJW8A", "@kallivalli450", "KTR", "leader"),
    ("gGvFturuhM4", "@kallivalli450", "Pradeep Machiraju", "celebrity"),
    ("cliqdtB329g", "@MyVillageShow", "Bithiri Sathi", "celebrity"),
    ("18Kft7GnyJg", "@MyVillageShow", "Dhethadi Harika", "celebrity"),
    ("QearANwPILA", "@MyVillageShow", "Nagarjuna", "celebrity"),
    ("rNj9aGesxFs", "@MyVillageShow", "Sadhguru", "celebrity"),
    ("p2b7mij_vOc", "@MyVillageShowVlogs", "Sarileru Neekevvaru", "celebrity"),
    ("s7ls0j-ZLRI", "@kallivalli450", "Gangavva Biggboss Experience", "celebrity"),
    ("lwZjFfBu-bQ", "@kallivalli450", "Feast with the Doctor", "celebrity"),
    ("cRhy9pour1M", "@VillageShow-Mix", "Suma Kanakala", "celebrity"),
    ("mQok9TRado0", "@MyVillageShow", "Nithin Rangde", "celebrity"),
    ("MfiwzVKWZU4", "@VillageShow-Mix", "Nithya Menon", "celebrity"),
    ("WOpmeEwrhR0", "@MyVillageShow", "Kajal Ashta Chamma", "celebrity"),
    ("aRAVE0_WYEE", "@MyVillageShow", "Dj Tillu", "celebrity"),
    ("d5UnrZoO3YU", "@kallivalli450", "Vishnupriya Maanas", "celebrity"),
    ("YJloZZUrBLQ", "@kallivalli450", "Writer Padmabhushan", "celebrity"),
    ("th6yhmLZJzQ", "@kallivalli450", "Ashwin Babu", "celebrity"),
    ("QgHbpr_ouU4", "@kallivalli450", "VJ Sunny", "celebrity"),
    ("oY8UyuOf9T0", "@kallivalli450", "RK Naidu", "celebrity"),
    ("ZS1Np_f-eH8", "@kallivalli450", "Bubble Gum team", "celebrity"),
    ("IR1_4lP7j3k", "@kallivalli450", "Navadeep", "celebrity"),
    ("297s4lIpW5I", "@VillageShow-Mix", "Sohel Mukku Avinash", "celebrity"),
    ("hnzRM32nmW4", "@kallivalli450", "Nakka Srikanth", "celebrity"),
    ("lA024OD8TSQ", "@MyVillageShowVlogs", "Bandi Saroj Kumar", "celebrity"),
    ("8pkp-lpMJP0", "@kallivalli450", "Spark Movie team", "celebrity"),
    ("OAv6SQ8Yz68", "@VillageShow-Mix", "Chaitanya Rao", "celebrity"),
    ("dHBA1Z0tOmg", "@kallivalli450", "Municipal commissioner Karimnagar", "official"),
    ("4K3Fsi0uxZA", "@MyVillageShowVlogs", "Woman Achiever Award", "official"),
    ("OKDxE0Wtuys", "@kallivalli450", "Siddu Jonnalagadda", "celebrity"),
    ("B6CA7OtzeZo", "@VillageShow-Mix", "Hero srikanth", "celebrity"),
]
# New uploads are added automatically when the title marks a guest: "ft.", "feat", "@name", "interview",
# "movie team", "chatting with", "muchatlu", or a title such as Dr./Hero/Director/Minister/MLA/Collector.
CELEBRITY_MARKERS = re.compile(
    r"\bft\b|\bfeat\b|@[A-Za-z]|interview|movie team|chatting with|muchatlu|ముచ్చట్లు|"
    r"\b(dr|hero|heroine|actor|actress|director|minister|mla|mp|collector|commissioner|governor|ktr)\b",
    re.I)
CELEBRITY_OFFICIAL = re.compile(r"\b(minister|mla|mp|collector|commissioner|governor|ktr|cm)\b", re.I)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def fetch(url, method="GET", attempts=4):
    # YouTube occasionally answers 404/429/5xx for a few seconds (the RSS feed especially), so retry with backoff.
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=UA, method=method)
            return urllib.request.urlopen(req, timeout=20)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            code = getattr(e, "code", None)
            if i == attempts - 1 or (code is not None and code not in (404, 429) and code < 500):
                raise
            time.sleep(3 * (i + 1))


def initial_data(html):
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    return json.loads(m.group(1)) if m else {}


def find_all(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from find_all(v, key)
    elif isinstance(obj, list):
        for x in obj:
            yield from find_all(x, key)


def channel_info(handle):
    html = fetch(f"https://www.youtube.com/{handle}").read().decode()
    data = initial_data(html)
    meta = next(find_all(data, "channelMetadataRenderer"), {})
    # Subscriber/video counts live in the page header, not in featured-channel shelves.
    header = next(find_all(data, "pageHeaderViewModel"), {})
    parts = [p.get("text", {}).get("content", "") for p in find_all(header, "metadataParts") for p in p]
    subs = next((p.replace(" subscribers", "") for p in parts if "subscriber" in p), "")
    videos = next((p.replace(" videos", "") for p in parts if p.endswith("videos")), "")
    avatar = (meta.get("avatar", {}).get("thumbnails") or [{}])[0].get("url", "")
    info = {
        "id": meta.get("externalId", ""),
        "title": meta.get("title", handle),
        "handle": handle,
        "url": f"https://www.youtube.com/{handle}",
        "subscribers": subs,
        "videos": videos,
        "views": 0,
        "avatar": "",
    }
    # Total channel views are only on the About page
    try:
        about = fetch(f"https://www.youtube.com/{handle}/about").read().decode()
        m = re.search(r'"viewCountText":"([\d,]+) views"', about)
        info["views"] = int(m.group(1).replace(",", "")) if m else 0
    except Exception as e:
        print(f"  views failed for {handle}: {e}", file=sys.stderr)
    if avatar:
        dest = AVATARS / f"{handle.strip('@').lower()}.jpg"
        try:
            dest.write_bytes(fetch(re.sub(r"=s\d+.*$", "=s240", avatar)).read())
            info["avatar"] = str(dest.relative_to(ROOT))
        except Exception as e:
            print(f"  avatar failed for {handle}: {e}", file=sys.stderr)
    return info


def is_short(video_id):
    # /shorts/<id> serves 200 for Shorts and redirects to /watch for regular videos.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        req = urllib.request.Request(f"https://www.youtube.com/shorts/{video_id}", headers=UA, method="HEAD")
        return opener.open(req, timeout=15).status == 200
    except Exception:
        return False


def latest_videos(channel_id):
    xml = fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}").read()
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
    out = []
    for e in ET.fromstring(xml).findall("a:entry", ns):
        vid = e.findtext("yt:videoId", namespaces=ns)
        stats = e.find("media:group/media:community/media:statistics", ns)
        out.append({
            "id": vid,
            "title": e.findtext("a:title", namespaces=ns),
            "published": e.findtext("a:published", namespaces=ns),
            "views": int(stats.get("views", 0)) if stats is not None else 0,
            "short": is_short(vid),
        })
    return out


def feed_entries(url):
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
    for e in ET.fromstring(fetch(url).read()).findall("a:entry", ns):
        stats = e.find("media:group/media:community/media:statistics", ns)
        yield {
            "id": e.findtext("yt:videoId", namespaces=ns),
            "title": e.findtext("a:title", namespaces=ns) or "",
            "published": e.findtext("a:published", namespaces=ns) or "",
            "views": int(stats.get("views", 0)) if stats is not None else 0,
        }


def to_seconds(text):
    # "1:35:10" -> 5710
    secs = 0
    for part in (text or "").split(":"):
        if not part.isdigit():
            return 0
        secs = secs * 60 + int(part)
    return secs


def approx_date(text):
    # Search results only say "2mo ago", "1y ago", "3 weeks ago"...
    m = re.search(r"(\d+)\s*(y|mo|w|d|h|mi)", text or "")
    days = int(m.group(1)) * {"y": 365, "mo": 30, "w": 7, "d": 1, "h": 0, "mi": 0}[m.group(2)] if m else 0
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def search_items(handle, query):
    # Works from cloud servers (unlike individual watch pages, which YouTube blocks there).
    html = fetch(f"https://www.youtube.com/{handle}/search?query={urllib.parse.quote(query)}").read().decode()
    for r in find_all(initial_data(html), "videoRenderer"):
        views = re.sub(r"\D", "", (r.get("viewCountText") or {}).get("simpleText", ""))
        yield {
            "id": r.get("videoId"),
            "title": "".join(t.get("text", "") for t in r.get("title", {}).get("runs", [])),
            "seconds": to_seconds((r.get("lengthText") or {}).get("simpleText", "")),
            "views": int(views or 0),
            "published": approx_date((r.get("publishedTimeText") or {}).get("simpleText", "")),
        }


def podcasts(channels):
    eps = {}
    def allowed(title):
        return not any(word in title.lower() for word in PODCAST_EXCLUDE)
    def tag(it, ch):
        return {**it, "channel": ch["title"], "channel_url": ch["url"]}

    for ch in channels:
        # 1. The channel's podcast search gives each episode's length, views and rough age.
        try:
            for it in search_items(ch["handle"], "podcast"):
                if it["id"] and "podcast" in it["title"].lower() and allowed(it["title"]):
                    eps.setdefault(it["id"], tag(it, ch))
        except Exception as e:
            print(f"  podcast search failed for {ch['handle']}: {e}", file=sys.stderr)

    # 2. The feeds give exact upload dates. The official playlist also lists episodes whose titles
    #    don't say "podcast"; each channel's uploads feed catches new episodes before search does.
    sources = []
    playlist_ch = next((c for c in channels if c["handle"] == PODCAST_PLAYLIST_CHANNEL), None)
    if playlist_ch:
        sources.append((f"https://www.youtube.com/feeds/videos.xml?playlist_id={PODCAST_PLAYLIST}", True, playlist_ch))
    sources += [(f"https://www.youtube.com/feeds/videos.xml?channel_id={c['id']}", False, c) for c in channels if c.get("id")]
    for url, from_playlist, ch in sources:
        try:
            for it in feed_entries(url):
                if not it["id"] or not allowed(it["title"]):
                    continue
                if it["id"] in eps:
                    eps[it["id"]].update(published=it["published"], views=max(it["views"], eps[it["id"]]["views"]))
                elif from_playlist or ("podcast" in it["title"].lower() and not is_short(it["id"])):
                    eps[it["id"]] = tag({**it, "seconds": 0}, ch)  # length unknown
        except Exception as e:
            print(f"  podcast feed failed for {ch['handle']}: {e}", file=sys.stderr)

    # Full episodes only: skips Shorts and short clips (a length of 0 means unknown, which is kept)
    episodes = [e for e in eps.values() if e["seconds"] == 0 or e["seconds"] >= PODCAST_MIN_SECONDS]
    episodes.sort(key=lambda e: e["views"], reverse=True)
    return episodes[:PODCAST_MAX]


def celebrity_talks(channels):
    by_handle = {c["handle"]: c for c in channels}
    previous = {v["id"]: v for v in previous_data().get("celebrity", [])}
    out = []
    for vid, handle, query, kind in CELEBRITY_TALKS:
        ch = by_handle.get(handle)
        if not ch:
            continue
        found = None
        try:
            found = next((it for it in search_items(handle, query) if it["id"] == vid), None)
        except Exception as e:
            print(f"  celebrity search failed for {vid}: {e}", file=sys.stderr)
        v = found or previous.get(vid)  # keep the last good numbers if this run missed it
        if v:
            out.append({**v, "kind": kind, "channel": ch["title"], "channel_url": ch["url"]})
        else:
            print(f"  celebrity talk not found: {vid} ({query})", file=sys.stderr)

    # New talks: each channel's newest uploads whose titles mark a guest
    known = {v["id"] for v in out} | {t[0] for t in CELEBRITY_TALKS}
    for ch in channels:
        try:
            for it in feed_entries(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"):
                t = it["title"]
                if (it["id"] in known or not CELEBRITY_MARKERS.search(t) or "podcast" in t.lower()
                        or any(word in t.lower() for word in PODCAST_EXCLUDE) or is_short(it["id"])):
                    continue
                kind = "official" if CELEBRITY_OFFICIAL.search(t) else "celebrity"
                out.append({**it, "seconds": 0, "kind": kind, "channel": ch["title"], "channel_url": ch["url"], "auto": True})
                known.add(it["id"])
                print(f"  new celebrity talk: {it['id']} {t[:60]}")
        except Exception as e:
            print(f"  celebrity feed failed for {ch['handle']}: {e}", file=sys.stderr)

    out.sort(key=lambda v: v["views"], reverse=True)
    return out


def previous_data():
    try:
        text = OUT.read_text()
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception:
        return {}


def previous_podcasts():
    try:
        text = OUT.read_text()
        return json.loads(text[text.index("{"):text.rindex("}") + 1]).get("podcasts", [])
    except Exception:
        return []


def main():
    try:
        channels = []
        for h in CHANNELS:
            print(f"channel {h}")
            channels.append(channel_info(h))
        vids = latest_videos(channels[0]["id"])
        print(f"{len(vids)} videos in feed ({sum(v['short'] for v in vids)} shorts)")
    except Exception as e:
        print(f"YouTube fetch failed, keeping existing data: {e}", file=sys.stderr)
        sys.exit(1)

    # Podcasts are optional: if they can't be fetched, keep the episodes from the last good run.
    pods = []
    try:
        pods = podcasts(channels)
        print(f"{len(pods)} podcast episodes")
    except Exception as e:
        print(f"Podcast fetch failed: {e}", file=sys.stderr)
    if not pods:
        pods = previous_podcasts()

    celeb = []
    try:
        celeb = celebrity_talks(channels)
        print(f"{len(celeb)} celebrity talks")
    except Exception as e:
        print(f"Celebrity talks failed: {e}", file=sys.stderr)
    if not celeb:
        celeb = previous_data().get("celebrity", [])
    # Podcast and Talk with Celebrity never share a video: a podcast episode stays in Podcast only
    pod_ids = {p["id"] for p in pods}
    celeb = [c for c in celeb if c["id"] not in pod_ids]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # A .js file (not .json) so the site also works when opened straight from disk.
    OUT.write_text("window.MVS_YT = " + json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": channels,
        "videos": [v for v in vids if not v["short"]][:LATEST_VIDEOS],
        "shorts": [v for v in vids if v["short"]][:LATEST_VIDEOS],
        "podcasts": pods,
        "celebrity": celeb,
    }, ensure_ascii=False, indent=2) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
