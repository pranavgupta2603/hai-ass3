"""Append-only storage. Never update a whole sheet or overwrite another participant."""
import json
import sqlite3
import threading
from pathlib import Path
from study import first_events

HEADERS = ['event_id', 'participant_id', 'kind', 'recorded_at', 'payload_json']
LOCK = threading.RLock()


class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, participant_id TEXT, data TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def read(self, pid=None):
        with self.connect() as con:
            sql = 'SELECT data FROM events' + (' WHERE participant_id=?' if pid else '') + ' ORDER BY rowid'
            return [json.loads(r[0]) for r in con.execute(sql, (pid,) if pid else ())]

    def put(self, item):
        with self.connect() as con:
            con.execute('INSERT OR IGNORE INTO events VALUES (?, ?, ?)',
                        (item['event_id'], item['participant_id'], json.dumps(item)))
        return first_events(self.read(item['participant_id']))[item['event_id']]


class MemoryStore:
    """Session-only reviewer preview: never writes study data."""
    def __init__(self):
        self.events = {}

    def read(self, pid=None):
        return [v for v in self.events.values() if pid is None or v['participant_id'] == pid]

    def put(self, item):
        return self.events.setdefault(item['event_id'], item)


class SheetsStore:
    def __init__(self, config):
        import gspread
        from google.oauth2.service_account import Credentials
        credentials = Credentials.from_service_account_info(
            dict(config['service_account']),
            scopes=['https://www.googleapis.com/auth/spreadsheets'])
        client = gspread.authorize(credentials)
        self.sheet = client.open_by_key(config['spreadsheet_id']).worksheet(config.get('worksheet', 'events'))
        self._rows()

    def _rows(self):
        # Clearing pilot responses sometimes clears the header as well. Recreate only
        # an entirely empty worksheet. Never overwrite a nonempty, unrecognized sheet.
        with LOCK:
            rows = self.sheet.get_all_values()
            if not any(any(cell for cell in row) for row in rows):
                self.sheet.update(range_name='A1:E1', values=[HEADERS], value_input_option='RAW')
                return [HEADERS]
            if rows[0] != HEADERS:
                raise ValueError('Study sheet headers changed; existing data was not modified.')
            return rows

    def read(self, pid=None):
        rows = self._rows()
        events = []
        for row in rows[1:]:
            if not any(row):
                continue
            if len(row) != len(HEADERS):
                raise ValueError('Incomplete event row; ask the study owner to check storage.')
            if pid is None or row[1] == pid:
                events.append(dict(event_id=row[0], participant_id=row[1], kind=row[2],
                                   recorded_at=row[3], payload=json.loads(row[4])))
        return list(first_events(events).values())

    def put(self, item):
        with LOCK:
            existing = first_events(self.read(item['participant_id']))
            if item['event_id'] in existing:
                return existing[item['event_id']]
            self.sheet.append_row([item['event_id'], item['participant_id'], item['kind'],
                                   item['recorded_at'], json.dumps(item['payload'], ensure_ascii=False)],
                                  value_input_option='RAW')
            # A concurrent tab/worker may have appended the same logical event first.
            return first_events(self.read(item['participant_id']))[item['event_id']]
