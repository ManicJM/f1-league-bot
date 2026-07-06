# 🚀 Deploying the bot to Hetzner (24/7 hosting)

This gets your bot running around the clock on a Hetzner Cloud server, with the
code stored on GitHub so future updates are one command. It's written to be
copy-paste friendly — you don't need prior server experience.

> **Which Hetzner product?** You need a **Hetzner Cloud server** (a VPS you can
> SSH into and run programs on). Hetzner's shared *Webhosting* product can't run
> a long-running bot — if that's what you have, create a Cloud server instead
> (the smallest/cheapest one, e.g. CX22, is plenty).

There are three stages: **A)** put the code on GitHub, **B)** create the server,
**C)** install and run the bot as a service.

---

## Stage A — Put the code on GitHub

1. On https://github.com, click **New repository**.
2. Name it e.g. `f1-league-bot`. **Set it to Private** (recommended). Do **not**
   tick "Add a README" (the project already has one). Click **Create repository**.
3. GitHub shows you the repo's URL, like
   `https://github.com/YOURNAME/f1-league-bot.git`. Keep that handy.

How you get the files into that repo depends on what's easiest for you — see the
two options your assistant will offer (either it pushes for you with a temporary
token, or you push from your own computer). Either way, once it's done, refresh
the GitHub page and you should see all the files **except** `.env` and `data/`
(those are correctly excluded by `.gitignore`).

---

## Stage B — Create the Hetzner Cloud server

1. In the Hetzner Cloud Console (https://console.hetzner.cloud), create a
   **New Project**, then **Add Server**.
2. Choose:
   - **Location**: closest to you.
   - **Image**: **Ubuntu 24.04**.
   - **Type**: the smallest shared vCPU (e.g. **CX22**) — this bot is very light.
   - **SSH key**: if you know how to add one, do; otherwise pick **password** and
     Hetzner will email you a root password.
3. Create the server and note its **IP address**.

**Connect to it** from your computer's terminal (Mac: Terminal app; Windows: use
PowerShell or install "Windows Terminal"):

```bash
ssh root@YOUR_SERVER_IP
```

Type `yes` if asked to trust it, then the password (or it logs in via your key).
You're now "on" the server — commands you type run there.

---

## Stage C — Install and run the bot

Run these on the server, in order. Lines starting with `#` are just comments.

**1. Update the system and install Python + git:**
```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git
```

**2. Create a dedicated user to run the bot (safer than running as root):**
```bash
adduser --disabled-password --gecos "" f1bot
```

**3. Switch to that user and download your code from GitHub:**
```bash
su - f1bot
git clone https://github.com/YOURNAME/f1-league-bot.git
cd f1-league-bot
```
> If the repo is **private**, GitHub will ask for a username and password. The
> "password" must be a **Personal Access Token**, not your account password —
> see "Cloning a private repo" at the bottom.

**4. Create a virtual environment and install the dependencies:**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**5. Create your `.env` file with your bot token:**
```bash
cp .env.example .env
nano .env
```
`nano` is a simple text editor. Fill in your `DISCORD_TOKEN` and `GUILD_ID`,
then press **Ctrl+O**, **Enter** to save, and **Ctrl+X** to exit.

**6. Test it runs** (you should see "Logged in as ..." then "Synced N commands"):
```bash
.venv/bin/python bot.py
```
Press **Ctrl+C** to stop the test. If it logged in, you're ready to make it
permanent.

**7. Install it as a service so it runs 24/7 and restarts on reboot/crash.**
Log back out to the root user (type `exit` once), then:
```bash
cp /home/f1bot/f1-league-bot/deploy/f1-league-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable f1-league-bot
systemctl start f1-league-bot
```

**8. Check it's alive:**
```bash
systemctl status f1-league-bot        # should say "active (running)"
journalctl -u f1-league-bot -f        # live logs; Ctrl+C to stop watching
```

That's it — your bot is now hosted and will keep running even after you close
your terminal or the server reboots.

---

## Updating the bot later

When you (or your assistant) push a change to GitHub, updating the server is:
```bash
su - f1bot
cd f1-league-bot
git pull
.venv/bin/pip install -r requirements.txt   # only needed if dependencies changed
exit
systemctl restart f1-league-bot
```
Your `.env` and your `data/league.db` are untouched by updates — they're not part
of the repo, so your token and league records are safe across every update.

## Backing up your data

Your entire league history is the single file `/home/f1bot/f1-league-bot/data/league.db`.
To back it up to your own computer, run this **from your computer** (not the server):
```bash
scp f1bot@YOUR_SERVER_IP:/home/f1bot/f1-league-bot/data/league.db ./league-backup.db
```
Do this every so often (especially before big updates).

---

## Handy commands

| Task | Command (as root) |
|------|-------------------|
| Start the bot | `systemctl start f1-league-bot` |
| Stop the bot | `systemctl stop f1-league-bot` |
| Restart the bot | `systemctl restart f1-league-bot` |
| See status | `systemctl status f1-league-bot` |
| Watch live logs | `journalctl -u f1-league-bot -f` |
| See recent logs | `journalctl -u f1-league-bot -n 100` |

## Cloning a private repo

If your GitHub repo is private, step C-3 needs a **Personal Access Token (PAT)**:
1. GitHub → your avatar → **Settings** → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Give it **read-only "Contents"** access to just this repository, and a short
   expiry.
3. When `git clone` asks for a username, enter your GitHub username; when it asks
   for a password, paste the **token**.

## Troubleshooting

- **`systemctl status` shows "failed"** — check the logs with
  `journalctl -u f1-league-bot -n 50`. Most often it's a missing/incorrect token
  in `.env`, or dependencies not installed in the venv.
- **Commands don't appear in Discord** — make sure `GUILD_ID` is set in `.env`
  and the bot was invited with the `applications.commands` scope (see README).
- **Bot was working, now offline** — `systemctl restart f1-league-bot`; if it
  won't stay up, read the logs.
