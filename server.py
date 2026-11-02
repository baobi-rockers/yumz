#!/usr/bin/env python3
"""
Channel 8 catalog add-on (Stremio / Nuvio add-on format).

Serves:  /manifest.json   /catalog/...   /meta/...   /stream/...
Data:    shows.json (from the scraper, optional) + every file in data/*.json
         (files in data/ override shows.json for the same show).
Playback: opens the official mewatch page or official YouTube uploads.
          This server does not touch or proxy video.

Run:  python server.py          (needs only Python, nothing to install)
"""
import glob, json, os, socket, sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

PORT = int(os.environ.get("PORT", 7070))
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_SIZE = 100
MIN_CONFIDENCE = 0.9        # scraper matches below this are ignored (wrong-show risk)
ID_PREFIX = "mediacorp:"
# Experiment: also attach YouTube streams directly to each episode in the show page (meta).
# Set by run_server_ytmeta.bat. Off by default.
YT_IN_META = os.environ.get("EMBED_YT") == "1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(rec):
    """Accept a scraper record OR a hand-built show file. Returns a clean dict, or None."""
    mw = rec.get("mewatch") or {}
    code = str(mw.get("show_code") or mw.get("code") or "")
    if not code:
        return None                                  # no mewatch page -> nothing to link to
    meta = rec.get("meta") or {}
    if meta and meta.get("confidence", 1.0) < MIN_CONFIDENCE:
        meta = {}
    return dict(
        id=f"{ID_PREFIX}{code}",
        name=rec.get("name") or rec.get("title") or "Untitled",
        name_zh=rec.get("name_zh") or rec.get("zh") or "",
        year=rec.get("year"),
        sitcom=bool(rec.get("sitcom")),
        url=mw.get("show_url") or mw.get("url") or "",
        seasons=rec.get("seasons") or meta.get("seasons") or [],
        cast=rec.get("cast") or meta.get("cast") or [],
        episodes=rec.get("episodes") or [],
    )


def load_shows():
    paths = []
    if os.path.exists(os.path.join(HERE, "shows.json")):
        paths.append(os.path.join(HERE, "shows.json"))
    paths += sorted(glob.glob(os.path.join(HERE, "data", "*.json")))
    shows, skipped = {}, 0
    for path in paths:
        try:
            data = load_json(path)
        except Exception as e:
            print(f"  ! could not read {os.path.basename(path)}: {e}")
            continue
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict) and "mewatch" in data:
            records = [data]
        elif isinstance(data, dict):
            records = list(data.values())
        else:
            records = []
        for rec in records:
            show = normalize(rec) if isinstance(rec, dict) else None
            if show:
                shows[show["id"]] = show
            else:
                skipped += 1
    return shows, skipped


SHOWS, SKIPPED = load_shows()


# ------------------------------------------------------------------ builders
def genres_for(s):
    g = ["Sitcom" if s["sitcom"] else "Drama"]
    if s["year"]:
        g.append(f"{s['year'] // 10 * 10}s")
    return g


def describe(s):
    bits = [s["name_zh"], "Mediacorp Channel 8"]
    n_seasons = len(s["seasons"])
    n_eps = sum((x.get("episodes") or x.get("episode_count") or 0) for x in s["seasons"])
    if n_eps:
        bits.append(f"{n_seasons} season(s), {n_eps} episodes")
    return " | ".join(b for b in bits if b)


def preview(s):
    return dict(id=s["id"], type="series", name=s["name"],
                releaseInfo=str(s["year"] or ""), description=describe(s),
                genres=genres_for(s))


def build_videos(s):
    base = datetime(s["year"] or 2000, 1, 1, tzinfo=timezone.utc)
    pairs = []
    if s["episodes"]:
        pairs = sorted(((e.get("season", 1), e["episode"]) for e in s["episodes"]))
    elif s["seasons"]:
        for se in s["seasons"]:
            count = se.get("episodes") or se.get("episode_count") or 0
            pairs += [(se["season"], n) for n in range(1, count + 1)]
    if not pairs:
        pairs = [(1, 1)]                             # fallback: one 'open on mewatch' entry
    vids = []
    for i, (season, ep) in enumerate(pairs):
        released = (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        v = dict(id=f"{s['id']}:{season}:{ep}", title=f"Episode {ep}",
                 season=season, episode=ep, released=released)
        if YT_IN_META:
            e = find_episode(s, season, ep)
            if e and e.get("youtube_id"):
                v["streams"] = [{
                    "name": "YouTube",
                    "title": "Mediacorp Classics (in-app)",
                    "ytId": e["youtube_id"],
                    "behaviorHints": {"bingeGroup": "c8-youtube"}
                }]
        vids.append(v)
    return vids


def build_meta(s):
    m = preview(s)
    m["cast"] = [c["name"] for c in s["cast"]]
    m["videos"] = build_videos(s)
    if s["url"]:
        m["links"] = [dict(name="mewatch", category="Official", url=s["url"])]
    return m


def find_episode(s, season, ep):
    for e in s["episodes"]:
        if e.get("episode") == ep and e.get("season", 1) == season:
            return e
    return None


def resolve_url(s, season, ep):
    e = find_episode(s, season, ep)
    if e and e.get("mewatch_url"):
        return e["mewatch_url"], True
    return s["url"], False


def catalog_items(catalog_id, extra):
    want_sitcom = catalog_id == "c8_sitcoms"
    items = [s for s in SHOWS.values() if s["sitcom"] == want_sitcom]
    genre = extra.get("genre")
    if genre:
        items = [s for s in items if genre in genres_for(s)]
    q = extra.get("search", "").strip().lower()
    if q:
        items = [s for s in items if q in s["name"].lower() or q in s["name_zh"].lower()]
    items.sort(key=lambda s: (-(s["year"] or 0), s["name"]))
    try:
        skip = int(extra.get("skip", 0))
    except ValueError:
        skip = 0
    return [preview(s) for s in items[skip:skip + PAGE_SIZE]]


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parts = [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]
        if parts and parts[-1].endswith(".json"):
            parts[-1] = parts[-1][:-5]

        if not parts or parts == ["manifest"]:
            return self.send_json(load_json(os.path.join(HERE, "addon.json")))

        if len(parts) >= 3 and parts[0] == "catalog":
            extra = {}
            if len(parts) >= 4:
                for pair in parts[3].split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        extra[k] = v
            return self.send_json({"metas": catalog_items(parts[2], extra)})

        if len(parts) == 3 and parts[0] == "meta":
            s = SHOWS.get(":".join(parts[2].split(":")[:2]))
            return self.send_json({"meta": build_meta(s)} if s else {"meta": None},
                                  200 if s else 404)

        if len(parts) == 3 and parts[0] == "stream":
            bits = parts[2].split(":")                # mediacorp:<code>:<season>:<episode>
            s = SHOWS.get(":".join(bits[:2]))
            if not s or len(bits) != 4:
                return self.send_json({"streams": []})
            try:
                season, ep = int(bits[2]), int(bits[3])
            except ValueError:
                return self.send_json({"streams": []})

            streams = []
            e = find_episode(s, season, ep)
            yt = e.get("youtube_id") if e else None

            if yt:
                # Primary: in-app YouTube player
                streams.append({
                    "name": "YouTube",
                    "title": "Mediacorp Classics (in-app)",
                    "description": "Official full episode – plays inside the app",
                    "ytId": yt,
                    "behaviorHints": {
                        "bingeGroup": "c8-youtube"
                    }
                })

            # Official mewatch page (always available as fallback)
            url, exact = resolve_url(s, season, ep)
            if url:
                streams.append({
                    "name": "mewatch",
                    "title": ("Watch this episode on mewatch (official site)" if exact
                              else "Open show on mewatch (official site)"),
                    "externalUrl": url
                })

            # Extra: open the YouTube page in browser
            if yt:
                streams.append({
                    "name": "YouTube",
                    "title": "Open on YouTube website",
                    "externalUrl": f"https://www.youtube.com/watch?v={yt}"
                })

            return self.send_json({"streams": streams})

        self.send_json({"error": "not found"}, 404)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    linked = sum(1 for s in SHOWS.values() if s["episodes"])
    print(f"Loaded {len(SHOWS)} shows ({linked} with per-episode links, {SKIPPED} skipped: no mewatch code)")
    print(f"\nOn this computer:   http://localhost:{PORT}/manifest.json")
    print(f"On your phone/TV:  http://{lan_ip()}:{PORT}/manifest.json  (same wifi)")
    print("\nKeep this window open. Ctrl+C to stop.")
    try:
        ThreadingHTTPServer(("", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
