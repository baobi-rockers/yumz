# Channel 8 Catalog (Stremio / Nuvio Add-on)

Unofficial catalog of older **Mediacorp Channel 8** dramas and sitcoms (roughly 1995–2018).

It lists shows + episodes and points to:

- Official **mewatch.sg** pages
- Official **Mediacorp Classics** YouTube uploads (when available)

This add-on does **not** host, scrape, or proxy any video files.

## Features

- Separate catalogs for Dramas and Sitcoms
- Search + decade filters
- Episode-level links (mewatch + YouTube when available)
- In-app YouTube playback when the client supports `ytId`
- Fallback external links to official sites

## Requirements

- Python 3.7+ (nothing else to install)

## Quick Start

1. Put show JSON files inside the `data/` folder  
   (one file per show, see `data/chronicle_of_life.json` as example)

2. Run the server:

   **Windows**
   ```bat
   run_server.bat
   ```

   **or**
   ```bat
   python server.py
   ```

3. Install in Stremio / Nuvio:

   - Same computer: `http://localhost:7070/manifest.json`
   - Phone / TV (same Wi-Fi): `http://YOUR-PC-IP:7070/manifest.json`

Keep the server window open while using the add-on.

## Optional: Embed YouTube in Meta

```bat
run_server_ytmeta.bat
```

This attaches the YouTube stream directly to each episode in the meta response.  
Normal mode (`run_server.bat`) is usually more reliable.

## Adding YouTube IDs

If you have an official public playlist:

```bash
python get_youtube_ids.py "https://www.youtube.com/playlist?list=PLxxxxxx" data/your_show.json
```

It matches episode numbers from the video titles and writes `youtube_id` into the JSON.

## File Structure

```
channel8-catalog/
├── addon.json              # Manifest
├── server.py               # The add-on server
├── run_server.bat
├── run_server_ytmeta.bat
├── get_youtube_ids.py      # Helper to fill youtube_ids from a playlist
├── data/                   # Put one JSON file per show here
│   └── chronicle_of_life.json
└── README.md
```

## Notes

- This is an unofficial community project.
- Playback always goes to official Mediacorp sources.
- Works best when the client’s YouTube player supports long-form content.
- You can host the server on a VPS / Railway / Render later if you want it always online.

## License

Use at your own risk. Not affiliated with Mediacorp.
