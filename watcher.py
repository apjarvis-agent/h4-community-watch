"""H4 community-report watcher. No official portal access or booking."""
import argparse
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import getpass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import threading
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UTC = timezone.utc
URLS = {
    'checkvisaslots': 'https://checkvisaslots.com/latest-us-visa-availability/h-4-regular/',
    'visaslots': 'https://visaslots.info/class/h-4/',
}
CITIES = ('CHENNAI', 'HYDERABAD', 'KOLKATA', 'MUMBAI', 'NEW DELHI')
UA = 'H4CommunityWatcher/0.1 (personal community-report monitor)'

@dataclass
class Report:
    source: str
    city: str
    kind: str
    appointment: str
    slots: int
    seen: datetime
    url: str

    def key(self):
        value = f'{self.source}|{self.city}|{self.kind}|{self.appointment}|{self.seen.isoformat()}'
        return hashlib.sha256(value.encode()).hexdigest()


def parse_time(text, source):
    # Site labels EST/ET inconsistently. UTC-4 is the EARLIER instant
    # among Eastern standard/daylight interpretations, so age is conservative.
    if source == 'checkvisaslots':
        return datetime.strptime(text, '%d %b %Y, %I:%M %p').replace(tzinfo=timezone(timedelta(hours=-4))).astimezone(UTC)
    return datetime.strptime(text, '%d %b %Y %I:%M:%S %p UTC').replace(tzinfo=UTC)


def relative_seen(text, now):
    if 'ago' not in text.lower():
        return None
    parts = re.findall(r'(\d+)\s*(secs?|seconds?|mins?|minutes?|hrs?|hours?|days?|wks?|weeks?)', text.lower())
    if not parts:
        return None
    seconds = sum(int(n) * (604800 if u.startswith(('wk', 'week')) else
                  86400 if u.startswith('day') else 3600 if u.startswith(('hr', 'hour')) else
                  60 if u.startswith(('min',)) else 1) for n, u in parts)
    return now - timedelta(seconds=seconds)


def parse_tracker(html, source, now=None):
    now = now or datetime.now(UTC)
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    recognized = False
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        headers = [c.get_text(' ', strip=True).lower() for c in rows[0].find_all(['th', 'td'])]
        needed = ['visa location', 'visa type', 'earliest date', 'slots on earliest date', 'last seen at', 'relative time'] if source == 'checkvisaslots' else ['location', 'updated', 'earliest', 'slots']
        if not all(h in headers for h in needed):
            continue
        recognized = True
        for row in rows[1:]:
            cells = [c.get_text(' ', strip=True) for c in row.find_all(['th', 'td'])]
            if len(cells) != len(headers):
                raise ValueError('Table row shape changed; not a zero-slot result')
            data = dict(zip(headers, cells))
            if source == 'checkvisaslots' and data['visa type'].lower() != 'h-4 (regular)':
                continue
            location = data.get('visa location', data.get('location', '')).upper()
            city = next((c for c in CITIES if location in (c, c + ' VAC', c + ' CONSULAR')), None)
            if not city:
                continue
            kind = 'VAC' if location.endswith('VAC') else 'interview'
            date_text = data.get('earliest date', data.get('earliest', ''))
            count = data.get('slots on earliest date', data.get('slots', ''))
            if count in ('N/A', '-', '') or date_text in ('N/A', '-', ''):
                continue
            if not count.isdigit():
                raise ValueError('Unknown slot count; refusing to guess')
            if int(count) <= 0:
                continue
            seen = parse_time(data['last seen at'], source) if source == 'checkvisaslots' else parse_time(data['updated'], source)
            if source == 'checkvisaslots':
                relative = relative_seen(data['relative time'], now)
                if relative is None:
                    raise ValueError('Cannot determine report age')
                seen = min(seen, relative)
            if seen is None:
                raise ValueError('Cannot determine report age')
            fmt = '%d %b, %y' if source == 'checkvisaslots' else None
            if fmt:
                appointment = datetime.strptime(date_text, fmt).date().isoformat()
            else:
                # Accept only tested date shapes. Unknown formats fail loudly.
                appointment = None
                for fmt in ('%d %b %Y', '%Y-%m-%d', '%d %b, %y'):
                    try:
                        appointment = datetime.strptime(date_text, fmt).date().isoformat()
                        break
                    except ValueError:
                        pass
                if appointment is None:
                    raise ValueError('Unknown appointment date format')
            result.append(Report(source, city, kind, appointment, int(count), seen, URLS[source]))
    if not recognized:
        raise ValueError('Availability table missing; page changed or access challenged')
    return result


def eligible(report, cfg, now):
    age = (now - report.seen).total_seconds()
    return (report.city in cfg['cities'] and (cfg.get('include_vac', False) or report.kind == 'interview')
            and 0 <= age <= cfg['max_report_age_minutes'] * 60
            and report.appointment >= now.date().isoformat())


def clean(text):
    # Remove ANSI/control sequences from untrusted text. Never run message text.
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)


def alert(text):
    print(clean(text), flush=True)
    print('\a', end='', flush=True)


class State:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.entries = json.loads(path.read_text()) if path.exists() else {}

    def fresh(self, key):
        with self.lock:
            now = time.time()
            self.entries = {k: v for k, v in self.entries.items() if v > now - 7 * 86400}
            if key in self.entries:
                return False
            self.entries[key] = now
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.entries))
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)
            return True


def fetch(source):
    url = URLS[source]
    origin = url.split('/')[0] + '//' + url.split('/')[2]
    response = requests.get(origin + '/robots.txt', headers={'User-Agent': UA}, timeout=20)
    response.raise_for_status()
    rp = RobotFileParser()
    rp.parse(response.text.splitlines())
    if not rp.can_fetch(UA, url):
        raise RuntimeError('robots.txt disallows this page')
    response = requests.get(url, headers={'User-Agent': UA}, timeout=20)
    response.raise_for_status()
    if 'text/html' not in response.headers.get('Content-Type', ''):
        raise RuntimeError('Expected HTML')
    return response.text


def tracker_cycle(cfg, state, disabled):
    for source in cfg['trackers']:
        if source in disabled:
            continue
        try:
            now = datetime.now(UTC)
            reports = parse_tracker(fetch(source), source, now)
            print(f'[{now.isoformat()}] {source}: parsed {len(reports)} positive rows; stale/filtered rows do not alert.', flush=True)
            for r in reports:
                if eligible(r, cfg, now):
                    # Relative-time rounding must not make identical reports new every poll.
                    key = hashlib.sha256(f'{r.source}|{r.city}|{r.kind}|{r.appointment}'.encode()).hexdigest()
                    if state.fresh(key):
                        alert(f'COMMUNITY REPORT, NOT CONFIRMED INVENTORY: {r.city} {r.kind}, {r.appointment}, {r.slots} slots; report about {int((now-r.seen).total_seconds()/60)} min old.\n{r.url}\nVerify manually in the official scheduling portal. VAC is not an interview or a complete booking.')
        except requests.HTTPError as e:
            status = e.response.status_code
            if status in (401, 403, 429):
                disabled.add(source)
                print(f'{source}: HTTP {status}; disabled for this run. No bypass/retry. Review access/terms manually.', file=sys.stderr)
            else:
                print(f'{source}: HTTP {status}; no availability inferred.', file=sys.stderr)
        except (requests.RequestException, ValueError, RuntimeError) as e:
            print(f'{source}: {type(e).__name__}: {e}; no availability inferred.', file=sys.stderr)
            # Challenge/layout/robots failures are not repeatedly hammered.
            if not isinstance(e, requests.RequestException):
                disabled.add(source)


def telegram_match(text, cities, include_vac=False):
    text = text.lower()
    if not include_vac and re.search(r'\b(vac|ofc|biometrics?)\b', text):
        return False
    category = bool(re.search(r'\bh\s*[- ]?\s*4\b', text))
    city = any(c.lower() in text or (c == 'NEW DELHI' and re.search(r'\bdelhi\b', text)) for c in cities)
    positive = bool(re.search(r'\b(available|opened?|released?|slots?\s+open|slots?\s+found)\b', text))
    negative = bool(re.search(r'\b(no|not|zero|unavailable|closed|gone|nothing|any|when|looking|need|waiting)\b|\?', text))
    return category and city and positive and not negative


async def telegram_watch(cfg, state, data, list_groups=False):
    from telethon import TelegramClient, events, errors, utils
    api_id = int(os.environ.get('TELEGRAM_API_ID') or input('API id (local only): '))
    api_hash = os.environ.get('TELEGRAM_API_HASH') or getpass.getpass('API hash (local only): ')
    client = TelegramClient(str(data / 'telegram'), api_id, api_hash, flood_sleep_threshold=0, sequential_updates=True)
    # Account/session information is sensitive even though it stays local.
    try:
        await client.start(password=lambda: getpass.getpass('Telegram 2FA password (local only): '))
        joined = {}
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                ident = utils.get_peer_id(dialog.entity)
                joined[ident] = dialog.entity
                if list_groups:
                    print(f'{ident}\t{clean(dialog.name)}')
        if list_groups:
            return
        ids = cfg.get('telegram_group_ids', [])
        if not ids:
            raise ValueError('No Telegram group IDs configured; use --list-groups first')
        if any(i not in joined for i in ids):
            raise ValueError('A configured group is not in your existing joined dialogs. No auto-join.')
        async def handler(event):
            now = datetime.now(UTC)
            age = (now - event.message.date).total_seconds()
            if not 0 <= age <= cfg['max_report_age_minutes'] * 60:
                return
            if telegram_match(event.raw_text or '', cfg['cities'], cfg.get('include_vac', False)):
                digest = hashlib.sha256((event.raw_text or '').encode()).hexdigest()
                key = f'tg:{event.chat_id}:{event.id}:{digest}'
                if state.fresh(key):
                    # Do not store bodies, forward to a server, reply, or download media.
                    alert(f'UNVERIFIED TELEGRAM COMMUNITY REPORT: group {event.chat_id}, message {event.id}, posted {event.message.date.isoformat()}. Open that group in your Telegram app to inspect.\nKeyword match only, not confirmed availability.')
        client.add_event_handler(handler, events.NewMessage(chats=ids, incoming=True))
        client.add_event_handler(handler, events.MessageEdited(chats=ids, incoming=True))
        print('Telegram: listening for NEW text/edited messages in configured joined groups. No history/media/OCR.', flush=True)
        await client.run_until_disconnected()
    except errors.FloodWaitError as e:
        raise RuntimeError(f'Telegram requested a {e.seconds}s flood wait. Stopped; do not retry before that wait expires.') from None
    finally:
        await client.disconnect()


async def run(cfg, args, data):
    state = State(data / 'seen.json')
    if args.list_groups:
        await telegram_watch(cfg, state, data, True)
        return
    async def trackers():
        disabled = set()
        while True:
            await asyncio.to_thread(tracker_cycle, cfg, state, disabled)
            if args.once:
                return
            await asyncio.sleep(cfg['poll_minutes'] * 60)
    jobs = []
    if cfg['trackers']:
        jobs.append(asyncio.create_task(trackers()))
    if args.telegram:
        jobs.append(asyncio.create_task(telegram_watch(cfg, state, data)))
    if not jobs:
        raise ValueError('No sources enabled')
    try:
        await asyncio.gather(*jobs)
    finally:
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--telegram', action='store_true')
    parser.add_argument('--list-groups', action='store_true')
    args = parser.parse_args()
    if args.once and args.telegram:
        parser.error('--once cannot be combined with --telegram')
    os.umask(0o077)
    cfg = json.loads(Path(args.config).read_text())
    if cfg['poll_minutes'] < 60:
        parser.error('Public page polling must be at least 60 minutes')
    if not cfg['cities'] or any(c not in CITIES for c in cfg['cities']):
        parser.error('cities must be a nonempty subset of the five supported cities')
    if any(s not in URLS for s in cfg['trackers']):
        parser.error('Unknown tracker')
    if cfg['max_report_age_minutes'] <= 0:
        parser.error('max_report_age_minutes must be positive')
    if any(not isinstance(i, int) for i in cfg.get('telegram_group_ids', [])):
        parser.error('telegram_group_ids must be integer dialog IDs')
    data = Path.home() / '.local' / 'share' / 'h4-slot-watch'
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(data, 0o700)
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run(cfg, args, data))
    except KeyboardInterrupt:
        pass
    except (ValueError, RuntimeError) as e:
        print(f'Stopped: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
