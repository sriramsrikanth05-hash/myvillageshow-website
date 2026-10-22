#!/usr/bin/env python3
"""Refresh the site's YouTube data (channel stats + latest uploads).

Run from anywhere:  python3 tools/update_youtube.py
Writes assets/data/youtube.js (loaded by index.html as window.MVS_YT) and caches channel avatars in assets/img/channels/.
If YouTube can't be reached, the existing JSON is kept untouched.
"""
import json, pathlib, re, sys, urllib.request, xml.etree.ElementTree as ET
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # A .js file (not .json) so the site also works when opened straight from disk.
    OUT.write_text("window.MVS_YT = " + json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": channels,
        "videos": [v for v in vids if not v["short"]][:LATEST_VIDEOS],
        "shorts": [v for v in vids if v["short"]][:LATEST_VIDEOS],
    }, ensure_ascii=False, indent=2) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
