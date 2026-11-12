from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from storage import SQLiteStore
from study import assignment, load_dataset

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


def test_preview_never_writes_study_store(monkeypatch, tmp_path):
    db = tmp_path / 'absent.db'
    monkeypatch.setenv('ASS3_MODE', 'local')
    monkeypatch.setenv('ASS3_DB', str(db))
    at = AppTest.from_file(str(BASE / 'app.py'))
    at.query_params['preview'] = 'assisted'
    at.run()
    pass_attention(at)
    assert len(at.metric) == 2 and not db.exists()
    # Changing conditions clears preview state, never real assignments.
    at.query_params['preview'] = 'baseline'
    at.run()
    pass_attention(at)
    assert not at.metric and not db.exists()


def test_production_requires_backend(monkeypatch):
    monkeypatch.setenv('ASS3_MODE', 'study')
    at = AppTest.from_file(str(BASE / 'app.py'))
    at.secrets['study'] = {'mode': 'study'}
    at.run()
    assert not at.exception and not at.text_input
    assert any('not open yet' in i.value for i in at.info)
