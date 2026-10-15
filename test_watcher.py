import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from watcher import parse_tracker, eligible, telegram_match, State, clean

NOW = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
CV = '''<table><tr><th>Visa Location</th><th>Visa Type</th><th>Earliest Date</th><th>Slots on Earliest Date</th><th>Last Seen At</th><th>Relative Time</th></tr><tr><td>CHENNAI</td><td>H-4 (Regular)</td><td>23 Oct, 26</td><td>3</td><td>13 Oct 2026, 12:50 PM</td><td>10 mins ago</td></tr><tr><td>CHENNAI VAC</td><td>H-4 (Regular)</td><td>24 Oct, 26</td><td>2</td><td>11 Oct 2026, 12:50 PM</td><td>2 days ago</td></tr></table>'''
VS = '''<table><tr><th>Location</th><th>Updated</th><th>Earliest</th><th>Slots</th></tr><tr><td>HYDERABAD CONSULAR</td><td>13 Oct 2026 04:35:55 PM UTC</td><td>29 Oct 2026</td><td>1</td></tr><tr><td>CHENNAI VAC</td><td>13 Oct 2026 04:35:55 PM UTC</td><td>N/A</td><td>0</td></tr></table>'''
CFG = dict(cities=['CHENNAI', 'HYDERABAD'], max_report_age_minutes=60, include_vac=False)

class Tests(unittest.TestCase):
    def test_cv_age_and_kind(self):
        reports = parse_tracker(CV, 'checkvisaslots', NOW)
        self.assertEqual(len(reports), 2)
        self.assertTrue(eligible(reports[0], CFG, NOW))
        self.assertFalse(eligible(reports[1], CFG, NOW))
        self.assertEqual(reports[1].kind, 'VAC')
    def test_cached_relative_is_not_fresh(self):
        cached = CV.replace('13 Oct 2026, 12:50 PM', '10 Oct 2026, 12:50 PM')
        self.assertFalse(eligible(parse_tracker(cached, 'checkvisaslots', NOW)[0], CFG, NOW))
    def test_vs(self):
        r = parse_tracker(VS, 'visaslots', NOW)[0]
        self.assertEqual(r.appointment, '2026-10-29')
        self.assertTrue(eligible(r, CFG, NOW))
    def test_missing_table_is_error(self):
        with self.assertRaises(ValueError):
            parse_tracker('<html>Verify you are human</html>', 'visaslots', NOW)
    def test_unknown_age_is_error(self):
        with self.assertRaises(ValueError):
            parse_tracker(CV.replace('10 mins ago', 'unknown'), 'checkvisaslots', NOW)
    def test_stale_future_and_past(self):
        r = parse_tracker(CV, 'checkvisaslots', NOW)[0]
        r.seen = NOW + timedelta(minutes=5)
        self.assertFalse(eligible(r, CFG, NOW))
        r.seen = NOW - timedelta(hours=2)
        self.assertFalse(eligible(r, CFG, NOW))
        r.seen = NOW
        r.appointment = '2026-10-01'
        self.assertFalse(eligible(r, CFG, NOW))
    def test_match(self):
        self.assertTrue(telegram_match('H-4 Chennai interview slots available Oct 23', CFG['cities']))
        for text in ['H4 Chennai no slots available', 'H4 Chennai slots available?', 'H1B Chennai available', 'H4 Delhi available', 'Looking for H4 Chennai available dates']:
            self.assertFalse(telegram_match(text, CFG['cities']), text)
    def test_telegram_vac_filter(self):
        text = 'H4 Chennai VAC slots available'
        self.assertFalse(telegram_match(text, CFG['cities']))
        self.assertTrue(telegram_match(text, CFG['cities'], include_vac=True))
    def test_dedup_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'state.json'
            s = State(p)
            self.assertTrue(s.fresh('x'))
            self.assertFalse(s.fresh('x'))
            self.assertFalse(State(p).fresh('x'))
    def test_terminal_escape(self):
        self.assertEqual(clean('\x1b[31mhello\x00'), 'hello')

if __name__ == '__main__':
    unittest.main()
