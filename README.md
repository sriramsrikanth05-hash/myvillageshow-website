# myvillageshow.com

Static website for My Village Show — plain HTML/CSS/JS, no build step.

## Run locally

    python3 -m http.server 8080

Then open http://localhost:8080

## Refresh YouTube data (subscribers, latest videos, shorts)

    python3 tools/update_youtube.py

Once deployed, GitHub does this automatically every 3 hours (see below), so you rarely need to run it.
It rewrites `assets/data/youtube.js` and channel avatars. If YouTube can't be reached,
the old data is kept. If that file is ever missing, the site falls back to built-in data.
To add or remove a channel, edit the `CHANNELS` list at the top of the script.

## Edit content

- Text, team, HRDC, contact details: `index.html`
- Colours and layout: `assets/style.css`. All colours are set at the top of the file:
  the **palette** (raw brand colours), the **roles** that use them (`--bg`, `--fg`, `--accent-text`…),
  and the **themes** (hero photo, HRDC band) that re-map those roles. Change a colour there and it updates site-wide.
- Images: `assets/img/`

## Deploy (GitHub Pages)

The site is hosted free on GitHub Pages; the domain stays registered at GoDaddy.
`.github/workflows/deploy.yml` publishes the site on every push to `main`, and every 3 hours it
refreshes the YouTube data, commits it, and republishes — no computer needs to be on.
Run it by hand any time from the repo's **Actions** tab → *Update YouTube data & deploy* → *Run workflow*.

Only `index.html`, `assets/` and `CNAME` are published; `tools/` and this README are not.

### One-time setup

1. Push this folder to a GitHub repository (branch `main`).
2. Repo → **Settings → Pages** → *Build and deployment* → Source: **GitHub Actions**.
3. GoDaddy → **Domain → DNS** for myvillageshow.com:
   - Remove the existing `A` record(s) for `@` (they point to the GoDaddy Website Builder),
     and turn off domain forwarding if it is on.
   - Add four `A` records for `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - Set `CNAME` for `www` → `<your-github-username>.github.io`
4. Repo → **Settings → Pages** → Custom domain: `myvillageshow.com` → after the DNS check passes, tick **Enforce HTTPS**.
