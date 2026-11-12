from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from storage import SQLiteStore
from study import assignment, load_dataset, event, ai_snapshot, response_payload, condition_events, condition_event, find

BASE = Path(__file__).resolve().parents[1]


def button(at, label):
    return next(b for b in at.button if b.label == label)


def login(at, name):
    at.text_input[0].input(name)
    at.checkbox[0].check()
    button(at, 'Continue').click().run()
    assert not at.exception


def pass_attention(at):
    at.radio(key='attention_answer').set_value('Whether it is real or a scam')
    button(at, 'Check & begin').click().run()
    assert not at.exception


@pytest.mark.parametrize('condition', ['baseline', 'assisted'])
def test_full_workflow_and_resume(monkeypatch, tmp_path, condition):
    db = tmp_path / 'test.db'
    monkeypatch.setenv('ASS3_MODE', 'local')
    monkeypatch.setenv('ASS3_DB', str(db))
    bank, digest = load_dataset(BASE / 'study_with_ai.csv')
    pid = next(f'student{i}' for i in range(100) if assignment(f'student{i}', bank, 'local-testing-only', digest)['condition'] == condition)
    at = AppTest.from_file(str(BASE / 'app.py')).run()
    login(at, pid)
    # A failed check does not terminate the participant.
    at.radio(key='attention_answer').set_value('Whether I would apply')
    button(at, 'Check & begin').click().run()
    assert at.error
    pass_attention(at)
    assert len(at.metric) == (2 if condition == 'assisted' else 0)
    button(at, 'Submit & Next').click().run()
    assert at.error
    assert not [e for e in SQLiteStore(db).read(pid) if e['kind'] == 'response']
    # Submit first response, then restart the browser session.
    for i in range(5):
        if i == 1:
            at = AppTest.from_file(str(BASE / 'app.py')).run()
            login(at, pid)
        assert not at.exception
        if condition == 'baseline':
            assert not at.metric
            assert not any(s.value == 'AI assistance' for s in at.subheader)
        at.radio[0].set_value('Real')
        at.radio[1].set_value(4)
        button(at, 'Submit & Next').click().run()
    assert at.radio(key='effort').value is None
    button(at, 'Finish study').click().run()
    assert at.error
    at.radio(key='effort').set_value(3)
    button(at, 'Finish study').click().run()
    assert at.success and not at.exception
    events = SQLiteStore(db).read(pid)
    responses = [e for e in events if e['kind'] == 'response']
    assert len(responses) == 5
    assert sum(e['kind'] == 'attention_attempt' for e in events) == 2
    assert all((e['payload']['ai_shown'] is not None) == (condition == 'assisted') for e in responses)
    at = AppTest.from_file(str(BASE / 'app.py')).run()
    login(at, pid)
    assert at.success and not at.radio


@pytest.mark.parametrize('parameter', ['condition', 'preview'])
@pytest.mark.parametrize('condition', ['baseline', 'assisted'])
def test_condition_links_require_sign_in_and_save_all_responses(monkeypatch, tmp_path, parameter, condition):
    db = tmp_path / 'condition.db'
    monkeypatch.setenv('ASS3_MODE', 'local')
    monkeypatch.setenv('ASS3_DB', str(db))
    at = AppTest.from_file(str(BASE / 'app.py'))
    at.query_params[parameter] = condition
    at.run()
    assert len(at.text_input) == 1 and not at.radio
    assert not SQLiteStore(db).read()
    login(at, 'linktester')
    pass_attention(at)
    for i in range(5):
        assert len(at.metric) == (2 if condition == 'assisted' else 0)
        at.radio[0].set_value('Real')
        at.radio[1].set_value(4)
        button(at, 'Submit & Next').click().run()
        assert not at.exception
        assert len([e for e in SQLiteStore(db).read('linktester') if e['kind'] == 'response']) == i + 1
    at.radio(key='effort').set_value(3)
    button(at, 'Finish study').click().run()
    assert at.success
    assert len([e for e in SQLiteStore(db).read('linktester') if e['kind'] == 'questionnaire']) == 1
    # Opening the other condition creates a separate run without resetting the first.
    at.query_params[parameter] = 'baseline' if condition == 'assisted' else 'assisted'
    at.run()
    assert not at.success and not at.text_input
    assert at.radio(key='attention_answer').value is None
    saved = [e for e in SQLiteStore(db).read('linktester') if e['kind'] == 'session']
    assert {e['payload']['condition'] for e in saved} == {'baseline', 'assisted'}
    assert len(condition_events(SQLiteStore(db).read('linktester'), condition)) > 5



@pytest.mark.parametrize('parameter', ['', 'condition', 'preview'])
def test_production_requires_backend(monkeypatch, parameter):
    monkeypatch.setenv('ASS3_MODE', 'study')
    at = AppTest.from_file(str(BASE / 'app.py'))
    if parameter:
        at.query_params[parameter] = 'baseline'
    at.secrets['study'] = {'mode': 'study'}
    at.run()
    assert not at.exception and not at.text_input
    assert any('not open yet' in i.value for i in at.info)


@pytest.mark.parametrize('legacy_format', [True, False])
@pytest.mark.parametrize('legacy_condition', ['baseline', 'assisted'])
def test_existing_complete_run_preserved_while_other_condition_completes(monkeypatch, tmp_path, legacy_condition, legacy_format):
    from export_results import export
    db = tmp_path / 'legacy.db'
    monkeypatch.setenv('ASS3_MODE', 'local')
    monkeypatch.setenv('ASS3_DB', str(db))
    store = SQLiteStore(db)
    bank, digest = load_dataset(BASE / 'study_with_ai.csv')
    pid = 'legacytester'
    session = assignment(pid, bank, 'local-testing-only', digest, legacy_condition)
    def make_event(kind, payload, suffix=''):
        return (event(pid, kind, payload, suffix) if legacy_format else
                condition_event(pid, legacy_condition, kind, payload, suffix))
    store.put(make_event('session', session))
    store.put(make_event('attention_pass', {'passed': True}))
    for tid in session['trial_ids']:
        row = bank[tid]
        exposure = store.put(make_event('exposure', {'trial_id': tid, 'condition': legacy_condition,
                    'ai_shown': ai_snapshot(row) if legacy_condition == 'assisted' else None}, tid))
        store.put(make_event('response', response_payload(session, row, exposure, row['true_label'], 4), tid))
    store.put(make_event('questionnaire', {'condition': legacy_condition, 'effort': 3}))
    original = store.read(pid)
    other = 'assisted' if legacy_condition == 'baseline' else 'baseline'
    at = AppTest.from_file(str(BASE / 'app.py'))
    at.query_params['condition'] = other
    at.run(); login(at, pid); pass_attention(at)
    for _ in range(5):
        assert len(at.metric) == (2 if other == 'assisted' else 0)
        at.radio[0].set_value('Real'); at.radio[1].set_value(3)
        button(at, 'Submit & Next').click().run()
        assert not at.exception
    at.radio(key='effort').set_value(4)
    button(at, 'Finish study').click().run()
    assert at.success
    all_events = store.read(pid)
    assert all_events[:len(original)] == original  # No migration or editing of old rows.
    assert len([e for e in all_events if e['kind'] == 'response']) == 10
    assert len([e for e in all_events if e['kind'] == 'questionnaire']) == 2
    second = find(condition_events(all_events, other), 'session')['payload']
    assert not set(session['trial_ids']) & set(second['trial_ids'])
    at.query_params['condition'] = legacy_condition
    at.run()
    assert at.success and not at.radio
    summary = export(all_events, tmp_path / 'exports')
    for cond in ['baseline', 'assisted']:
        assert summary['conditions'][cond]['completed_participants'] == 1
        assert summary['conditions'][cond]['trial_responses'] == 5


def test_incomplete_legacy_run_resumes_after_switch(monkeypatch, tmp_path):
    db = tmp_path / 'partial.db'
    monkeypatch.setenv('ASS3_MODE', 'local'); monkeypatch.setenv('ASS3_DB', str(db))
    store = SQLiteStore(db)
    bank, digest = load_dataset(BASE / 'study_with_ai.csv')
    pid = 'partialtester'
    session = assignment(pid, bank, 'local-testing-only', digest, 'baseline')
    original = store.put(event(pid, 'session', session))
    store.put(event(pid, 'attention_pass', {'passed': True}))
    at = AppTest.from_file(str(BASE / 'app.py'))
    at.query_params['condition'] = 'assisted'
    at.run(); login(at, pid); pass_attention(at)
    at.radio[0].set_value('Scam'); at.radio[1].set_value(2)
    button(at, 'Submit & Next').click().run()
    button(at, 'Switch to baseline study').click().run()
    assert not at.exception and not at.metric
    at.radio[0].set_value('Real'); at.radio[1].set_value(4)
    button(at, 'Submit & Next').click().run()
    events = store.read(pid)
    assert find(condition_events(events, 'baseline'), 'session') == original
    old_response = find(condition_events(events, 'baseline'), 'response')
    assert old_response['event_id'].startswith(f'ass3-v1:{pid}:response:')
    assert len([e for e in condition_events(events, 'assisted') if e['kind'] == 'response']) == 1
