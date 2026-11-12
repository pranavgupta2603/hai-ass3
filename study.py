"""Study protocol; independent of Streamlit and storage providers."""
import csv
import hashlib
import hmac
import html
import json
import random
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

VERSION = 'ass3-v1'
N_TRIALS = 5
LABELS = ('Real', 'Scam')


def now():
    return datetime.now(timezone.utc).isoformat()


def seconds(start, end):
    return max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def participant_id(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9]{1,19}', value):
        raise ValueError('Enter your UMich uniqname only (letters and numbers, no @umich.edu).')
    return value


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'div', 'br', 'li', 'ul', 'ol'):
            self.parts.append('\n' + ('• ' if tag == 'li' else ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'li'):
            self.parts.append('\n')

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def clean(value):
    parser = PlainText()
    parser.feed(html.unescape(str(value or '')))
    text = ''.join(parser.parts).replace('\xa0', ' ')
    return re.sub(r'\n[ \t\n]*\n', '\n\n', text).strip()


def load_dataset(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    required = {'trial_id', 'title', 'description', 'true_label', 'ai_prediction',
                'ai_scam_probability', 'ai_confidence', 'ai_key_words', 'ai_signals',
                'company_profile', 'requirements', 'salary_range', 'has_company_logo'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('Study dataset is missing required columns.')
    bank = {}
    for row in rows:
        key = str(int(row['trial_id']))
        if key in bank or row['true_label'] not in LABELS or row['ai_prediction'] not in LABELS:
            raise ValueError('Invalid trial IDs or labels.')
        if not 0 <= int(row['ai_scam_probability']) <= 100 or not clean(row['description']):
            raise ValueError('Invalid probability or empty posting.')
        bank[key] = row
    if len(bank) != 200 or sum(r['true_label'] == 'Scam' for r in rows) != 100:
        raise ValueError('Expected the final balanced 200-trial Assignment 2 dataset.')
    return bank, digest


def assignment(pid, bank, salt, digest, condition=None):
    seed = hmac.new(salt.encode(), f'{VERSION}:{pid}'.encode(), hashlib.sha256).digest()
    rng = random.Random(int.from_bytes(seed, 'big'))
    assigned_condition = rng.choice(('baseline', 'assisted'))
    scam_count = rng.choice((2, 3))
    ids = rng.sample(sorted(k for k, r in bank.items() if r['true_label'] == 'Scam'), scam_count)
    ids += rng.sample(sorted(k for k, r in bank.items() if r['true_label'] == 'Real'), N_TRIALS - scam_count)
    rng.shuffle(ids)
    return {'condition': condition or assigned_condition, 'trial_ids': ids,
            'dataset_sha256': digest, 'version': VERSION, 'started_at': now()}


def first_events(events):
    """First confirmed append wins; collapse retries, including uncertain network writes."""
    result = {}
    for event in events:
        result.setdefault(event['event_id'], event)
    return result


def event(pid, kind, payload, suffix=''):
    return {'event_id': f'{VERSION}:{pid}:{kind}' + (f':{suffix}' if suffix else ''),
            'participant_id': pid, 'kind': kind, 'recorded_at': now(), 'payload': payload}


def find(events, kind, trial_id=None):
    return next((e for e in first_events(events).values() if e['kind'] == kind and
                 (trial_id is None or e['payload'].get('trial_id') == str(trial_id))), None)


def ai_snapshot(row):
    return {k: row[k] for k in ('ai_prediction', 'ai_scam_probability', 'ai_confidence',
                               'ai_key_words', 'ai_signals')}


def response_payload(session, row, exposure, answer, confidence, timestamp=None):
    if answer not in LABELS or confidence not in range(1, 6):
        raise ValueError('Choose a judgment and a confidence rating before submitting.')
    if row['trial_id'] not in session['trial_ids']:
        raise ValueError('Trial is not part of this participant assignment.')
    end = timestamp or now()
    elapsed = seconds(exposure['recorded_at'], end)
    return {'trial_id': row['trial_id'], 'condition': session['condition'],
            'position': session['trial_ids'].index(row['trial_id']) + 1,
            'answer': answer, 'confidence': confidence, 'true_label': row['true_label'],
            'human_correct': answer == row['true_label'], 'ai_prediction': row['ai_prediction'],
            'ai_correct': row['ai_prediction'] == row['true_label'],
            'agrees_with_ai': answer == row['ai_prediction'],
            'displayed_at': exposure['recorded_at'], 'submitted_at': end,
            'elapsed_seconds': round(elapsed, 3), 'long_trial': elapsed > 300,
            'ai_shown': exposure['payload']['ai_shown']}
