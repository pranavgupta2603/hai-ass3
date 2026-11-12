import concurrent.futures
from pathlib import Path
import pytest
from study import assignment, clean, event, first_events, load_dataset, response_payload
from storage import SQLiteStore, SheetsStore, HEADERS
from export_results import export

BASE = Path(__file__).resolve().parents[1]
BANK, DIGEST = load_dataset(BASE / 'study_with_ai.csv')


def test_assignments_reproducible_balanced_varied():
    assignments = [assignment(f'person{i}', BANK, 'test-salt', DIGEST) for i in range(100)]
    for i, a in enumerate(assignments):
        b = assignment(f'person{i}', BANK, 'test-salt', DIGEST)
        assert a['trial_ids'] == b['trial_ids'] and a['condition'] == b['condition']
        assert len(set(a['trial_ids'])) == 5
        assert sum(BANK[t]['true_label'] == 'Scam' for t in a['trial_ids']) in (2, 3)
    assert {a['condition'] for a in assignments} == {'baseline', 'assisted'}
    assert len({tuple(a['trial_ids']) for a in assignments}) > 90


def test_concurrent_duplicate_and_cross_participant_writes(tmp_path):
    store = SQLiteStore(tmp_path / 'test.db')
    items = [event(f'user{i % 10}', 'response', {'answer': i}, '1') for i in range(100)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(store.put, items))
    assert len(store.read()) == 10
    previous = store.read('user1')[0]
    assert store.put(event('user1', 'response', {'answer': 'changed'}, '1')) == previous
    assert SQLiteStore(tmp_path / 'test.db').read('user1') == [previous]


def test_baseline_payload_and_elapsed_time():
    session = assignment('person', BANK, 'salt', DIGEST, 'baseline')
    row = BANK[session['trial_ids'][0]]
    exposed = event('person', 'exposure', {'ai_shown': None})
    exposed['recorded_at'] = '2026-11-11T12:00:00+00:00'
    result = response_payload(session, row, exposed, 'Real', 3, '2026-11-11T12:06:00+00:00')
    assert result['ai_shown'] is None and result['elapsed_seconds'] == 360 and result['long_trial']
    with pytest.raises(ValueError):
        response_payload(session, row, exposed, 'Real', None)


def test_text_does_not_execute_markup():
    assert clean('<p>Hello</p><script>alert(1)</script><li>World</li>') == 'Hello\n\n• World'


class FakeSheet:
    def __init__(self):
        self.rows = [HEADERS]
        self.fail_after_write = False
        self.header_updates = 0
    def update(self, *, range_name, values, value_input_option):
        assert range_name == "A1:E1" and value_input_option == "RAW"
        self.header_updates += 1
        self.rows = values + self.rows[1:]
    def get_all_values(self):
        return self.rows
    def append_row(self, row, **kwargs):
        assert kwargs['value_input_option'] == 'RAW'
        self.rows.append(row)
        if self.fail_after_write:
            self.fail_after_write = False
            raise TimeoutError('Connection lost after write')


def test_sheets_uncertain_write_recovery_and_deduplication():
    store = SheetsStore.__new__(SheetsStore)
    store.sheet = FakeSheet()
    item = event('person', 'response', {'answer': 'Real'}, '1')
    store.sheet.fail_after_write = True
    with pytest.raises(TimeoutError):
        store.put(item)
    assert store.put(item) == item
    assert len(store.sheet.rows) == 2
    store.sheet.rows.append(store.sheet.rows[-1])
    assert store.read('person') == [item]


def test_export_excludes_incomplete_from_summary(tmp_path):
    events = [event('person', 'session', assignment('person', BANK, 'salt', DIGEST))]
    result = export(events + events, tmp_path)
    assert all(v['completed_participants'] == 0 for v in result['conditions'].values())
    assert (tmp_path / 'participants.csv').read_text().count('person') == 1


@pytest.mark.parametrize('empty_rows', [[], [[]], [['', '', '', '', '']], [[], [], []]])
def test_sheets_restores_entirely_empty_sheet_before_sign_in(empty_rows):
    store = SheetsStore.__new__(SheetsStore)
    store.sheet = FakeSheet()
    store.sheet.rows = empty_rows
    session = event('participant', 'session', {'condition': 'baseline'})
    assert store.put(session) == session
    assert store.sheet.rows[0] == HEADERS
    assert store.sheet.header_updates == 1
    assert store.read('participant') == [session]


def test_sheets_recovers_if_cleared_after_connection():
    store = SheetsStore.__new__(SheetsStore)
    store.sheet = FakeSheet()
    assert store.read() == []
    store.sheet.rows = [[]]
    assert store.read() == []
    assert store.sheet.rows == [HEADERS]


def test_sheets_does_not_overwrite_nonempty_sheet_with_bad_headers():
    store = SheetsStore.__new__(SheetsStore)
    store.sheet = FakeSheet()
    store.sheet.rows = [[], ['existing', 'participant', 'data']]
    with pytest.raises(ValueError, match='existing data was not modified'):
        store.read()
    assert store.sheet.header_updates == 0
    assert store.sheet.rows[1] == ['existing', 'participant', 'data']
