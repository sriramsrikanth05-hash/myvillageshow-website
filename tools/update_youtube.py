#!/usr/bin/env python3
"""Refresh the site's YouTube data (channel stats, latest uploads and podcast episodes).

Run from anywhere:  python3 tools/update_youtube.py
Writes assets/data/youtube.js (loaded by index.html as window.MVS_YT) and caches channel avatars in assets/img/channels/.
If YouTube can't be reached, the existing JSON is kept untouched.
"""
import json, pathlib, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone

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

# The podcast lives on the Vlogs channel. Its official playlist isn't always kept up to date, so episodes
# are also picked up from the channel's newest uploads and its "podcast" search.
PODCAST_CHANNEL = "@MyVillageShowVlogs"
PODCAST_PLAYLIST = "PLqwv8aBwfwiq3aCGTua3nvi_FXfnRzx1g"
PODCAST_MIN_SECONDS = 20 * 60                 # full episodes only: skips trailers, clips and Shorts
PODCAST_EXCLUDE = ["anil geela", "అనిల్ జీల"]  # people no longer featured on the site
PODCAST_MAX = 16
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def fetch(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    return urllib.request.urlopen(req, timeout=20)


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
        "avatar": "",
    }
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


def feed_titles(url):
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    for e in ET.fromstring(fetch(url).read()).findall("a:entry", ns):
        yield e.findtext("yt:videoId", namespaces=ns), e.findtext("a:title", namespaces=ns) or ""


def search_titles(handle, query):
    html = fetch(f"https://www.youtube.com/{handle}/search?query={urllib.parse.quote(query)}").read().decode()
    for r in find_all(initial_data(html), "videoRenderer"):
        yield r.get("videoId"), "".join(t.get("text", "") for t in r.get("title", {}).get("runs", []))


def video_details(video_id):
    html = fetch(f"https://www.youtube.com/watch?v={video_id}").read().decode()
    def first(pattern):
        m = re.search(pattern, html)
        return m.group(1) if m else ""
    return {
        "seconds": int(first(r'"lengthSeconds":"(\d+)"') or 0),
        "published": first(r'"uploadDate":"([^"]+)"'),
        "views": int(first(r'"viewCount":"(\d+)"') or 0),
    }


def podcasts(channel_id):
    found = {}  # video id -> title
    sources = [(f"https://www.youtube.com/feeds/videos.xml?playlist_id={PODCAST_PLAYLIST}", False)]
    if channel_id:
        sources.append((f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", True))
    for url, needs_word in sources:
        try:
            for vid, title in feed_titles(url):
                if vid and (not needs_word or "podcast" in title.lower()):
                    found.setdefault(vid, title)
        except Exception as e:
            print(f"  podcast feed failed: {e}", file=sys.stderr)
    try:
        for vid, title in search_titles(PODCAST_CHANNEL, "podcast"):
            if vid and "podcast" in title.lower():
                found.setdefault(vid, title)
    except Exception as e:
        print(f"  podcast search failed: {e}", file=sys.stderr)

    episodes = []
    for vid, title in list(found.items())[:40]:
        if any(word in title.lower() for word in PODCAST_EXCLUDE):
            continue
        try:
            d = video_details(vid)
        except Exception as e:
            print(f"  details failed for {vid}: {e}", file=sys.stderr)
            continue
        if d["seconds"] >= PODCAST_MIN_SECONDS:
            episodes.append({"id": vid, "title": title, **d})
    episodes.sort(key=lambda e: e["views"], reverse=True)
    return episodes[:PODCAST_MAX]


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
        vlogs = next((c for c in channels if c["handle"] == PODCAST_CHANNEL), {})
        pods = podcasts(vlogs.get("id", ""))
        print(f"{len(pods)} podcast episodes")
    except Exception as e:
        print(f"Podcast fetch failed: {e}", file=sys.stderr)
    if not pods:
        pods = previous_podcasts()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # A .js file (not .json) so the site also works when opened straight from disk.
    OUT.write_text("window.MVS_YT = " + json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": channels,
        "videos": [v for v in vids if not v["short"]][:LATEST_VIDEOS],
        "shorts": [v for v in vids if v["short"]][:LATEST_VIDEOS],
        "podcasts": pods,
    }, ensure_ascii=False, indent=2) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
