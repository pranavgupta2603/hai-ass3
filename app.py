"""Run: streamlit run app.py. See README.md for study and local modes."""
import html
import logging
import os
from pathlib import Path
import streamlit as st
from storage import MemoryStore, SheetsStore, SQLiteStore
from study import (VERSION, N_TRIALS, assignment, ai_snapshot, clean, event, find,
                   load_dataset, now, participant_id, response_payload, seconds)

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title='Job Posting Study', page_icon='🔎', layout='centered')
st.markdown('''<style>
.block-container {max-width: 920px; padding-top: 2.5rem; padding-bottom: 4rem;}
.posting-text {white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; margin-bottom: 1rem;}
.study-eyebrow {color: #517675; letter-spacing: .14em; font-size: .75rem; font-weight: 700;}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="study-eyebrow">HUMAN–AI INTERACTION · ASSIGNMENT 3</div>', unsafe_allow_html=True)
st.title('Real opportunity or scam?')


def safe(operation):
    try:
        return operation()
    except Exception:
        logging.exception('Study storage or configuration operation failed')
        st.error('We could not confirm your data was saved or loaded. Your progress will not advance. '
                 'Keep this page open and retry. If this continues, contact the study organizer.')
        if st.button('Retry connection', key='retry_connection'):
            st.rerun()
        st.stop()


def text(value):
    st.markdown('<div class="posting-text">' + html.escape(clean(value)) + '</div>', unsafe_allow_html=True)


@st.cache_data
def dataset():
    return load_dataset(BASE / 'study_with_ai.csv')


@st.cache_resource
def sheets_store(config):
    return SheetsStore(config)


@st.cache_resource
def local_store(path):
    return SQLiteStore(path)


try:
    config = st.secrets.to_dict()
except FileNotFoundError:
    config = {}
settings = config.get('study', {})
preview = st.query_params.get('preview', '')
if preview not in ('', 'baseline', 'assisted'):
    st.error('Unknown preview condition. Use ?preview=baseline or ?preview=assisted.')
    st.stop()
mode = os.environ.get('ASS3_MODE', settings.get('mode', 'study'))
context = f'{mode}:{preview}'
if st.session_state.get('context') != context:
    st.session_state.clear()
    st.session_state.context = context

bank, digest = safe(dataset)
if preview:
    st.warning('REVIEWER PREVIEW · Nothing here is saved to the study. Refresh to start over.')
    if 'preview_store' not in st.session_state:
        st.session_state.preview_store = MemoryStore()
    store = st.session_state.preview_store
    salt = 'preview-only'
    st.session_state.pid = 'reviewer'
elif mode == 'local':
    st.warning('LOCAL TEST MODE · Responses are stored on this computer, not in the study Google Sheet.')
    store = local_store(os.environ.get('ASS3_DB', str(BASE / 'data' / 'local.sqlite3')))
    salt = 'local-testing-only'
elif mode == 'study':
    salt = settings.get('assignment_salt', '')
    if len(salt) < 32 or 'google_sheets' not in config:
        st.info('The study is not open yet. The organizer is configuring response storage.')
        st.caption('Reviewer links: add ?preview=baseline or ?preview=assisted to this address.')
        st.stop()
    store = safe(lambda: sheets_store(config['google_sheets']))
else:
    st.error('Unknown application mode. The study cannot accept responses.')
    st.stop()

if 'pid' not in st.session_state:
    st.write('Read five job postings and decide whether each is real or a scam. '
             'Please allow about 8–9 minutes, including instructions and a short final question.')
    st.caption('We record your uniqname, answers, confidence, timing, instruction-check attempts, '
               'and final effort rating for a class study. Your uniqname links your responses and lets you resume. '
               'It is not a password; enter only your own uniqname.')
    with st.form('sign_in'):
        name = st.text_input('UMich uniqname', placeholder='e.g. jsmith', max_chars=20)
        acknowledged = st.checkbox('I understand what will be recorded and am ready to participate.')
        go = st.form_submit_button('Continue', type='primary')
    if go:
        try:
            pid = participant_id(name)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        if not acknowledged:
            st.error('Please confirm that you understand what will be recorded.')
            st.stop()
        # Save assignment before entering the task, even if the browser is refreshed.
        safe(lambda: store.put(event(pid, 'session', assignment(pid, bank, salt, digest))))
        st.session_state.pid = pid
        st.rerun()
    st.stop()

pid = st.session_state.pid
if preview:
    store.put(event(pid, 'session', assignment(pid, bank, salt, digest, condition=preview)))
events = safe(lambda: store.read(pid))
session_event = find(events, 'session')
if not session_event:
    st.error('No saved assignment was found. Please sign in again.')
    if st.button('Return to sign-in'):
        del st.session_state.pid
        st.rerun()
    st.stop()
session = session_event['payload']
if session['dataset_sha256'] != digest or session['version'] != VERSION:
    st.error('The study materials changed after you started. Please contact the organizer.')
    st.stop()

with st.sidebar:
    st.header('Your study')
    st.write('Reviewer' if preview else f'Signed in as **{pid}**')
    st.caption('Five postings · One final question')
    st.write('With AI assistance' if session['condition'] == 'assisted' else 'Independent judgment')
    st.caption('Submitted responses are saved and cannot be revised. If you leave, return using the same uniqname.')
    if not preview and st.button('Sign out'):
        st.session_state.clear()
        st.rerun()


def instructions():
    st.markdown('''
Read the available information and decide whether the posting describes a **real job** or a **scam**.
Use only the posting shown here; please do not search the web or use another AI tool.

- Consider the description, requirements, company information, and salary together.
- Missing information alone does not prove that a posting is a scam.
- Choose **Real** or **Scam**, then rate your confidence from **1 (not at all confident)** to **5 (very confident)**.
- Select **Submit & Next** to save. You cannot revise a submitted response.
- Correct answers will not be shown during the study. Make your best judgment if unsure.
''')
    if session['condition'] == 'assisted':
        st.info('Each posting includes an AI suggestion, estimated scam probability, confidence category, '
                'and supporting words or company signals. These are learned associations, not verified facts. '
                'The AI can be wrong, including when it is confident. You make the final decision.')

if not find(events, 'attention_pass'):
    st.subheader('Before you begin')
    instructions()
    st.divider()
    st.subheader('Quick instruction check')
    with st.form('attention'):
        choice = st.radio('What will you decide for each job posting?',
                          ['Whether it is real or a scam', 'Whether I would apply', 'Whether the salary is attractive'],
                          index=None, key='attention_answer')
        checked = st.form_submit_button('Check & begin', type='primary')
    if checked:
        if choice is None:
            st.error('Choose an answer to continue.')
        else:
            attempts = sum(e['kind'] == 'attention_attempt' for e in events)
            passed = choice == 'Whether it is real or a scam'
            safe(lambda: store.put(event(pid, 'attention_attempt', {'answer': choice, 'passed': passed}, str(attempts + 1))))
            if passed:
                safe(lambda: store.put(event(pid, 'attention_pass', {'passed': True})))
                st.rerun()
            else:
                st.error('Please reread the instructions: your task is to decide whether each posting is real or a scam. Try again.')
    st.stop()

answers = {e['payload']['trial_id']: e for e in events if e['kind'] == 'response'}
completed = find(events, 'questionnaire')
if completed:
    st.progress(1.0, text='Study complete')
    st.success('Thank you — all five responses and your final rating have been recorded.' if not preview
               else 'Preview complete. No study data was saved.')
    st.write('You can close this page. Please avoid discussing individual postings with classmates until data collection ends.')
    st.caption(f'Completion reference: {VERSION}-{pid}')
    st.stop()

st.progress(len(answers) / N_TRIALS, text=f'{len(answers)} of {N_TRIALS} postings submitted')
if len(answers) == N_TRIALS:
    st.subheader('One last question')
    with st.form('questionnaire'):
        effort = st.radio('How mentally demanding was this task?', list(range(1, 8)), index=None,
                          horizontal=True, key='effort', help='1 = Not at all demanding · 7 = Extremely demanding')
        st.caption('1 = Not at all demanding · 7 = Extremely demanding')
        finish = st.form_submit_button('Finish study', type='primary')
    if finish:
        if effort is None:
            st.error('Choose an effort rating before finishing.')
        else:
            end = now()
            safe(lambda: store.put(event(pid, 'questionnaire', {'effort': effort, 'completed_at': end,
                 'condition': session['condition'], 'total_elapsed_seconds': seconds(session['started_at'], end)})))
            st.rerun()
    st.stop()

trial_id = next(t for t in session['trial_ids'] if t not in answers)
row = bank[trial_id]
exposure = find(events, 'exposure', trial_id)
if not exposure:
    exposure = safe(lambda: store.put(event(pid, 'exposure', {
        'trial_id': trial_id, 'condition': session['condition'],
        'ai_shown': ai_snapshot(row) if session['condition'] == 'assisted' else None}, trial_id)))

st.caption(f'POSTING {len(answers) + 1} OF {N_TRIALS}')
with st.expander('Review the instructions'):
    instructions()
with st.container(border=True):
    st.subheader(clean(row['title']) or 'Untitled posting')
    st.caption('Company logo supplied' if row['has_company_logo'] == '1' else 'No company logo supplied')
    for field, label in [('salary_range', 'Salary'), ('company_profile', 'Company profile'),
                         ('description', 'Job description'), ('requirements', 'Requirements')]:
        st.markdown(f'**{label}**')
        text(row[field] or 'Not provided')

if session['condition'] == 'assisted':
    with st.container(border=True):
        st.subheader('AI assistance')
        ai = exposure['payload']['ai_shown']
        left, right = st.columns(2)
        left.metric('AI suggestion', ai['ai_prediction'])
        right.metric('Estimated scam probability', f"{ai['ai_scam_probability']}%")
        st.progress(int(ai['ai_scam_probability']) / 100)
        st.caption(f"AI confidence: {ai['ai_confidence']}")
        st.markdown('**Supporting keywords**')
        text(ai['ai_key_words'] or 'None supplied')
        st.markdown('**Company signals supporting this suggestion**')
        text(ai['ai_signals'] or 'None supplied')
        st.caption('The AI can be wrong. Keywords and signals describe learned patterns, not verified evidence.')

with st.form(f'trial_{trial_id}'):
    st.subheader('Your judgment')
    answer = st.radio('Is this posting real or a scam?', ['Real', 'Scam'], index=None, horizontal=True, key=f'answer_{trial_id}')
    confidence = st.radio('How confident are you in your answer?', list(range(1, 6)), index=None,
                          horizontal=True, key=f'confidence_{trial_id}')
    st.caption('1 = Not at all confident · 5 = Very confident')
    submitted = st.form_submit_button('Submit & Next', type='primary')
if submitted:
    if answer is None or confidence is None:
        st.error('Choose both a judgment and a confidence rating before submitting.')
    else:
        payload = response_payload(session, row, exposure, answer, confidence)
        safe(lambda: store.put(event(pid, 'response', payload, trial_id)))
        st.rerun()
