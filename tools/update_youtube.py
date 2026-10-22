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

# Celebrity specials from KalliValli, shown in the Podcast section. Chosen by hand (most-viewed celebrity
# videos); titles, views and lengths are refreshed from the channel's "Popular" list on every run.
CELEBRITY_CHANNEL = "@kallivalli450"
CELEBRITY_SPECIALS = [
    "s7ls0j-ZLRI",  # Gangavva Bigg Boss Experience, full interview
    "lwZjFfBu-bQ",  # Feast with the Doctor: Dr. Vikrant Singh Thakur
    "d5UnrZoO3YU",  # Vishnupriya, Maanas daawath
    "YJloZZUrBLQ",  # Writer Padmabhushan team, Suhas
    "th6yhmLZJzQ",  # Hidimba team, Ashwin Babu
    "QgHbpr_ouU4",  # VJ Sunny
    "oY8UyuOf9T0",  # RK Naidu (Sagar)
    "ZS1Np_f-eH8",  # Bubble Gum movie team
    "IR1_4lP7j3k",  # Sagileti Katha team, Navadeep
    "hnzRM32nmW4",  # Nakka Srikanth
    "8pkp-lpMJP0",  # Spark movie team
    "OKDxE0Wtuys",  # Siddu Jonnalagadda
]
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


def count(text):
    # "5.1M views" -> 5100000, "834K views" -> 834000, "1,234 views" -> 1234
    m = re.search(r"([\d.,]+)\s*([KMB])?", text or "")
    if not m:
        return 0
    return int(float(m.group(1).replace(",", "")) * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2) or "", 1))


def popular_videos(handle, pages=6):
    # A channel's Videos tab sorted by "Popular", read through the same API the YouTube website uses.
    html = fetch(f"https://www.youtube.com/{handle}/videos").read().decode()
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html).group(1)
    version = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html).group(1)
    token = re.search(r'"chipViewModel":\{"text":"Popular".*?"token":"([^"]+)"', html).group(1)
    found = {}
    for _ in range(pages):
        body = json.dumps({"context": {"client": {"clientName": "WEB", "clientVersion": version, "hl": "en"}},
                           "continuation": token}).encode()
        req = urllib.request.Request(f"https://www.youtube.com/youtubei/v1/browse?key={key}", data=body,
                                     headers={**UA, "Content-Type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=20))
        for r in find_all(data, "lockupViewModel"):
            text = json.dumps(r, ensure_ascii=False)
            title = re.search(r'"title": \{"content": "((?:[^"\\]|\\.)+)"', text)
            meta = re.findall(r'"text": \{"content": "([^"]+)"', text)
            length = re.search(r'"text": "(\d+:\d+(?::\d+)?)"', text)
            if r.get("contentId") and title:
                found[r["contentId"]] = {
                    "id": r["contentId"],
                    "title": json.loads(f'"{title.group(1)}"'),
                    "views": count(next((m for m in meta if "view" in m), "")),
                    "published": approx_date(next((m for m in meta if "ago" in m), "")),
                    "seconds": to_seconds(length.group(1) if length else ""),
                }
        tokens = list(find_all(data, "continuationCommand"))
        if not tokens:
            break
        token = tokens[-1]["token"]
    return found


def celebrity_specials(channels):
    ch = next((c for c in channels if c["handle"] == CELEBRITY_CHANNEL), None)
    if not ch:
        return []
    previous = {v["id"]: v for v in previous_data().get("celebrity", [])}
    try:
        popular = popular_videos(CELEBRITY_CHANNEL)
    except Exception as e:
        print(f"  celebrity specials: popular list failed: {e}", file=sys.stderr)
        popular = {}
    out = []
    for vid in CELEBRITY_SPECIALS:
        v = popular.get(vid) or previous.get(vid)  # keep the last good numbers if this run missed it
        if v:
            out.append({**v, "channel": ch["title"], "channel_url": ch["url"]})
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
        celeb = celebrity_specials(channels)
        print(f"{len(celeb)} celebrity specials")
    except Exception as e:
        print(f"Celebrity specials failed: {e}", file=sys.stderr)
    if not celeb:
        celeb = previous_data().get("celebrity", [])

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
