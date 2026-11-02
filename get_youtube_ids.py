#!/usr/bin/env python3
"""
Add YouTube video ids to a show file, from an official public playlist.

Usage:
  python get_youtube_ids.py "<playlist url>" data/chronicle_of_life.json

It only READS the playlist's list of videos (ids + titles). Nothing is downloaded.
It matches each video to an episode number and writes "youtube_id" into the file,
printing the matches so you can check them by eye.
"""
import json, re, subprocess, sys, urllib.request


def playlist_id(s):
    m = re.search(r"list=([\w-]+)", s)
    return m.group(1) if m else s


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def initial_data(html):
    i = html.find("ytInitialData")
    j = html.find("{", i) if i >= 0 else -1
    if j < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(html[j:])[0]
    except ValueError:
        return {}


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def text_of(t):
    if isinstance(t, dict):
        if "runs" in t:
            return "".join(r.get("text", "") for r in t["runs"])
        return t.get("simpleText") or t.get("content") or ""
    return t or ""


def videos_from_page(data):
    """Handles YouTube's older (…VideoRenderer) and newer (lockupViewModel) layouts."""
    seen, out = set(), []

    def add(vid, title):
        if vid and vid not in seen:
            seen.add(vid)
            out.append((vid, title or ""))

    for node in walk(data):
        for key in ("playlistVideoRenderer", "playlistPanelVideoRenderer", "videoRenderer"):
            vr = node.get(key)
            if isinstance(vr, dict):
                add(vr.get("videoId"), text_of(vr.get("title")))
        lv = node.get("lockupViewModel")
        if isinstance(lv, dict) and str(lv.get("contentType", "")).endswith("_VIDEO"):
            meta = (lv.get("metadata") or {}).get("lockupMetadataViewModel") or {}
            add(lv.get("contentId"), text_of(meta.get("title")))
    return out


def videos_via_ytdlp(url):
    """Backup: yt-dlp in list-only mode (it is kept up to date with YouTube changes)."""
    try:
        r = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "-J",
                            "--no-warnings", url], capture_output=True, text=True, timeout=180)
    except Exception as e:
        print(f"  yt-dlp could not run: {e}")
        return []
    if r.returncode != 0:
        if "No module named" in r.stderr:
            print("  yt-dlp isn't installed. Run:  pip install yt-dlp   then run this command again.")
        else:
            print("  yt-dlp error:", r.stderr.strip()[-300:])
        return []
    entries = json.loads(r.stdout).get("entries", [])
    return [(e["id"], e.get("title") or "") for e in entries if e.get("id")]


def episode_number(title):
    m = re.search(r"(?:\bep(?:isode)?\.?\s*|\be)0*(\d{1,3})\b", title, re.I)
    return int(m.group(1)) if m else None


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    pl, path = sys.argv[1], sys.argv[2]
    url = f"https://www.youtube.com/playlist?list={playlist_id(pl)}"

    vids = []
    try:
        vids = videos_from_page(initial_data(fetch(url)))
    except Exception as e:
        print(f"Could not read the page: {e}")
    if not vids:
        print("Page reading found nothing (YouTube's layout probably changed). Trying yt-dlp...")
        vids = videos_via_ytdlp(url)
    if not vids:
        raise SystemExit("\nNo videos found, so nothing was changed. "
                         "Install the backup tool with:  pip install yt-dlp   and run this again.")

    print(f"Found {len(vids)} videos in the playlist")
    if len(vids) >= 100:
        print("! 100+ videos: only the first batch may have been read")

    nums = [episode_number(t) for _, t in vids]
    by_title = None not in nums and len(set(nums)) == len(nums)
    mapping = {}
    for pos, ((vid, title), n) in enumerate(zip(vids, nums), 1):
        ep = n if by_title else pos
        mapping[ep] = vid
        print(f"  episode {ep:>3} <- {vid}  {title[:70]}")
    print("Matched by the episode number in each title" if by_title
          else "! Titles had no clear episode numbers: matched by playlist ORDER. Check the list above.")

    with open(path, "r", encoding="utf-8") as f:
        show = json.load(f)
    hit = 0
    for e in show.get("episodes", []):
        if e["episode"] in mapping:
            e["youtube_id"] = mapping[e["episode"]]
            hit += 1
    show["youtube_playlist"] = playlist_id(pl)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(show, f, ensure_ascii=False, indent=2)
    total = len(show.get("episodes", []))
    print(f"\nSaved. {hit} of {total} episodes now have a YouTube id.")
    if hit != total:
        print("! Some episodes have no video. Check the list above.")


if __name__ == "__main__":
    main()
