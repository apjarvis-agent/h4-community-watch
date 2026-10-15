# H4 Community Watch

A small, self-run Python watcher for H-4 appointment **community reports** in India. Optional Telegram support uses the Telegram API through Telethon, with your own login, on your machine. No cloud model, no official appointment-portal login, no booking, no account creation, no CAPTCHA bypass.

**Status: prototype, not a verified production monitor.** Ten offline tests pass (rerun October 14, 2026). A direct HTTP smoke test on October 13, 2026 was denied: CheckVisaSlots returned 429 and VisaSlots.info returned 403. The program stops checking a denied source for that run. These adapters are not proven to work from your network. Do not try to evade access controls. Telegram end-to-end login/listening has not been tested with a real account.

## What it does

- Checks the two supported public HTML trackers at most once per hour, including robots.txt. No undocumented API or paid dashboard.
- Reports only matching positive rows that are at most 60 minutes old by default. All five cities by default. Interview-only by default; VAC is a separate opt-in.
- Treats missing tables, unknown dates, unknown ages, and access denials as errors, never "no slots".
- Optional Telegram listener receives new text and edited messages in explicitly configured groups/channels you already joined. No history sweep, joining, messages sent, media downloads, or screenshots/OCR.
- Telegram keyword matches require H4, a configured city, and availability language. Negatives/questions are suppressed. Explicit VAC/OFC/biometrics mentions are skipped unless `include_vac` is enabled; unlabeled messages can still be ambiguous. This can miss shorthand, mixed-language, image-only and ambiguous updates, and can still produce false positives.
- Alerts go to your local terminal and ring its bell. No WhatsApp, email, remote forwarding, webhook, or guaranteed desktop/push notification. Keep the process running and the machine awake. Closing the terminal stops it.
- Persists only report hashes/timestamps for seven-day duplicate suppression, not group message bodies. A tracker city/type/date alerts once per seven days; reopening that same date can be suppressed. Independent sources remain independent; disagreement is not resolved into confirmed inventory.

**A VAC report is not a consular interview, and neither proves a complete appointment can be booked.** Every alert is unverified. Check the official scheduling portal manually before acting or making travel plans.

## Setup (Python 3.10+)

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp config.example.json config.json
python3 -m unittest -v
python3 watcher.py --once
```

On Windows use `py` instead of `python3`, `.venv\Scripts\activate` and `copy config.example.json config.json`.

Edit `config.json` to choose cities, freshness window, `include_vac`, and tracker names. Cities: `CHENNAI`, `HYDERABAD`, `KOLKATA`, `MUMBAI`, `NEW DELHI`. `poll_minutes` cannot be below 60. Set `trackers` to `[]` for Telegram-only mode.

```sh
python3 watcher.py
```

Watch the terminal for source errors. A running process is not proof that any source is working. No startup inventory dump or stale-report alert is promised. Public snapshots can already be old when read; hourly polling can miss short-lived openings. CheckVisaSlots labels its times EST/ET inconsistently. To avoid false freshness, the parser takes the older age from the relative text and the earliest absolute instant under Eastern standard/daylight interpretations. This can suppress valid reports for an extra hour in standard time. Unknown timestamps fail closed; cached relative-age text cannot turn an old absolute timestamp into a fresh report.

## Optional Telegram setup, entirely on your computer

Telegram messages are handled as updates arrive while connected, rather than hourly polling. This is near-real-time detection of matching **community posts**, not instant access to official slots. Network delays, missing reports and keyword filtering still apply. The default terminal bell may be silent on your system; test it locally. No phone push alerts are included.

1. Read [Telegram API terms](https://core.telegram.org/api/terms). Respect each group's rules and member privacy. This is an unofficial client using the Telegram API, not endorsed by Telegram.
2. Follow [Telegram's API-id instructions](https://core.telegram.org/api/obtaining_api_id): sign in to `my.telegram.org`, open API development tools, obtain your own `api_id` and `api_hash`.
3. Run `python3 watcher.py --list-groups`. Enter the API id/hash at the **local terminal prompts**, then your Telegram phone/code and optional two-step password. Never paste credentials in a chat, repo, issue, screenshot or support log. The hash and two-step password prompts are hidden.
4. Copy the integer IDs of the groups you want from that local list into `telegram_group_ids` in `config.json`, for example `[-1001234567890]`. Only groups/channels in your own joined-dialog list are accepted. The script does not resolve invite links or join anything.
5. Run `python3 watcher.py --telegram`. With `trackers: []`, it only listens to Telegram. Otherwise both run.

No Telegram account or bot is supplied. Bots cannot generally read arbitrary groups unless added with suitable access. Without a login, only some **public channel web previews** can be read; private groups and join-only links cannot. Web-preview monitoring is **not implemented** in this release.

If Telegram returns a flood wait, the listener stops and prints the wait length. Do not restart before that period ends. Unofficial API clients can be restricted even with cautious use. No account-ban guarantee is possible. Do not use this on an account whose restriction you cannot tolerate.

## Privacy and session security

Local processing is **not offline**: tracker checks contact their websites, and Telegram connects to Telegram servers. No data goes to a cloud model or a monitoring service through this program.

The Telegram session is a login credential. It can give access to your account, not merely selected groups. Telethon's default session database also caches dialog/entity information. Keep `~/.local/share/h4-slot-watch/` private and off shared/cloud-synced folders. The script creates it with restrictive POSIX permissions; Windows users should check their user-directory ACLs. Never upload `.session` files. Run one process per session. Revoke the session in your Telegram app's Devices settings if compromised, then remove local session files. Stopping the program does not revoke the login.

`config.json`, sessions and virtual environments are ignored by Git. Keep your group IDs private too. No private messages or real-account fixtures are in this repository. Alerts identify group/message IDs rather than echoing group bodies. Open your Telegram app to inspect the report.

## Access and limitations

robots.txt is checked before tracker requests; it is not a license or a guarantee that scraping is allowed. Review each site's current terms before enabling automation and use the operator's own alerts if required. The watcher stops on 401/403/429, robots denial, or a table/layout error. Do not lower the cadence, rotate identities, use proxies to evade restrictions, or automate the official visa portal. No appointment or visa-policy advice is generated.

Public-page layouts can change. VisaSlots.info positive-date formats are conservatively accepted only if recognized; a positive-date live row has not been verified. Tests use synthetic fixtures, not private Telegram data. Source adapters fail closed but all-zero known tables do parse as zero positive rows.

## Source references

- https://checkvisaslots.com/latest-us-visa-availability/h-4-regular/ (crowdsourced last-seen reports)
- https://checkvisaslots.com/robots.txt
- https://visaslots.info/class/h-4/ (VAC and consular sections)
- https://visaslots.info/robots.txt
- https://core.telegram.org/api/terms
- https://core.telegram.org/api/obtaining_api_id
- https://docs.telethon.dev/en/stable/basic/updates.html
- https://docs.telethon.dev/en/stable/concepts/sessions.html
- https://docs.telethon.dev/en/stable/quick-references/faq.html

No claim of official inventory or endorsement. This project does not replace the official appointment portal.
