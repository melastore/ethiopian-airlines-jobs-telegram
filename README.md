# Ethiopian Airlines Jobs Telegram Notifier

Checks the Ethiopian Airlines careers website every hour and posts new local
vacancies and recruitment results to a Telegram channel, with the published candidate
name list attached. Runs 1:00 to 12:00 on the Ethiopian clock, Monday to Saturday, and
never posts the same item twice.

Not affiliated with or endorsed by Ethiopian Airlines. Always confirm details on the
official careers pages.

## Post format

```text
-------- Vacancies --------

Position: Driver I

Registration Date: July 13, 2026, to July 17, 2026

Location: Ethiopian Airlines Head Quarter, Ethiopian Airports Building (Recruitment & Placement Office)

Closing Date: July 17, 2026

URL: https://corporate.ethiopianairlines.com/AboutEthiopian/careers/vacancies#panel_0
```

Results carry the announcement text and the size of the name list:

```text
-------- Result --------

Position: Spa Therapist

Announcement: CALL FOR COMPETENCY BASED INTERVIEW

Location: Ethiopian Skylight Hotel

Details: Among those candidates who submitted their application for the position of
Spa Therapist, the following listed applicants are requested to come for Competency
Based Interview (CBI) on Friday, August 28, 2026 ...

Candidates listed: 11

URL: https://corporate.ethiopianairlines.com/AboutEthiopian/careers/results#panel_0
```

The `URL` points at the card itself rather than the top of the page. The site has no
permanent page per job, so the anchor is the card's position on the page and it moves
when the airline adds or removes a posting.

## Name lists

Every result card publishes the candidates who passed. The site does this in one of
two ways, and both are delivered as a file alongside the message.

* A linked PDF is downloaded and uploaded to Telegram as it is.
* An inline table is drawn into a landscape PDF, with the heading row repeated on every
  page. A list of ten thousand names takes about three seconds to build.

Both arrive as PDFs so they open straight in Telegram on any phone, with no other app
needed.

When the message is short enough it becomes the file's caption, so each posting is a
single item in the channel.

## How duplicates are avoided

Every card gets two keys.

* **Identity** is the kind, position and location, reduced to letters and digits.
  It answers "is this the same posting".
* **Content key** adds the dates or announcement text, the rest of the card and any
  attached file, also reduced to letters and digits. It answers "has anything changed".

Because both keys ignore spacing, commas and capitalisation, an editor fixing
`September 01 ,2026` into `September 01, 2026` does not cause a second post. A real
date change does.

Delivery uses a claim in SQLite:

1. The post is written as `pending` and committed.
2. The message is sent.
3. The row is marked `sent`.

If the send is rejected the claim is deleted and the post is offered again next hour.
If the process is killed between steps 2 and 3, the claim is settled as `sent` on the
next start, because Telegram has no way to tell us whether the message arrived and a
duplicate notice is worse than a missed one.

A file lock keeps two runs from overlapping.

## Requirements

* Linux with Python 3.11 or newer
* A Telegram bot token from [@BotFather](https://t.me/BotFather)
* A channel where that bot is an administrator with permission to post
* The channel username, for example `@my_jobs_channel`, or a numeric chat ID

## Commands

```bash
ethiopian-jobs check      # scrape and print, sends nothing, saves nothing
ethiopian-jobs schedule   # print the next eight run times
ethiopian-jobs prime      # mark everything on the site as already seen
ethiopian-jobs run        # one pass, sends what is new
ethiopian-jobs watch      # stay running and check on schedule
```

Run `prime` once before the first real run, otherwise the first `run` posts every
vacancy and result currently on the site.

## Configuration

Copy `.env.example` to `.env` and edit it.

| Variable | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | required | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | required | Channel username or numeric chat ID |
| `DATABASE_PATH` | `data/jobs.db` | SQLite delivery history |
| `SCHEDULE_TIMEZONE` | `Africa/Addis_Ababa` | Timezone the window is measured in |
| `ACTIVE_HOURS` | `7-18` | First and last hour, inclusive |
| `ACTIVE_DAYS` | `mon-sat` | Days to run, `mon-sat` or `mon,wed,fri` |
| `REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `SEND_GAP_SECONDS` | `3.5` | Gap between messages, keeps under Telegram's channel rate limit |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

## Install on a server

```bash
sudo useradd --system --home-dir /opt/ethiopian-jobs --shell /usr/sbin/nologin ethiopian-jobs
sudo mkdir -p /opt/ethiopian-jobs
sudo chown ethiopian-jobs:ethiopian-jobs /opt/ethiopian-jobs

sudo -u ethiopian-jobs git clone https://github.com/melastore/ethiopian-airlines-jobs-telegram.git /opt/ethiopian-jobs
cd /opt/ethiopian-jobs
sudo -u ethiopian-jobs python3 -m venv .venv
sudo -u ethiopian-jobs .venv/bin/pip install .

sudo -u ethiopian-jobs cp .env.example .env
sudo -u ethiopian-jobs nano .env
sudo -u ethiopian-jobs .venv/bin/ethiopian-jobs prime
```

### systemd timer

The timer is the recommended setup. Nothing stays running between checks.

```bash
sudo cp deploy/ethiopian-jobs.service deploy/ethiopian-jobs.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ethiopian-jobs.timer
systemctl list-timers ethiopian-jobs.timer
```

The timer is written in UTC. `04:00` to `15:00` UTC is `07:00` to `18:00` in Addis
Ababa. Ethiopia does not observe daylight saving, so the two never drift apart.

### Long running service

If you would rather keep one process alive, the schedule is enforced inside the
program as well.

```bash
sudo cp deploy/ethiopian-jobs-watch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ethiopian-jobs-watch
journalctl -u ethiopian-jobs-watch -f
```

### GitHub Actions

The repository can run the checks itself, with no server of your own.

1. Settings, Secrets and variables, Actions, then add `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID`.
2. Run the `check careers pages` workflow once by hand to seed the history.

The workflow keeps its delivery history on a `state` branch, so the schedule and the
history survive independently of the cache. A `concurrency` group stops two runs from
sending the same posting.

Scheduled runs on GitHub are best effort and can be late by several minutes. That does
not lose anything, because the next run still sees whatever has not been sent.

### cron

```cron
CRON_TZ=Africa/Addis_Ababa
0 7-18 * * 1-6 /opt/ethiopian-jobs/.venv/bin/ethiopian-jobs run >> /var/log/ethiopian-jobs.log 2>&1
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check src tests
```

## License

MIT. See [LICENSE](LICENSE).
