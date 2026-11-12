"""Owner-only CLI: export clean participant/trial/questionnaire tables and summaries."""
import argparse
import csv
import json
import statistics
import tomllib
from pathlib import Path
from storage import SheetsStore, SQLiteStore
from study import first_events, find


def csv_file(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            # Protect exported spreadsheets from formula execution.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v)
                             for k, v in row.items() if k in fields})


def export(events, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    events = list(first_events(events).values())
    participants, trials, questionnaires = [], [], []
    for pid in sorted({e['participant_id'] for e in events}):
        own = [e for e in events if e['participant_id'] == pid]
        session = find(own, 'session')
        if not session:
            continue
        payload = session['payload']
        answers = [e for e in own if e['kind'] == 'response']
        questionnaire = find(own, 'questionnaire')
        participants.append({'participant_id': pid, **payload,
                             'trial_ids': ','.join(payload['trial_ids']),
                             'attention_attempts': sum(e['kind'] == 'attention_attempt' for e in own),
                             'attention_passed': bool(find(own, 'attention_pass')),
                             'responses': len(answers), 'completed': bool(questionnaire),
                             'accuracy': statistics.mean(e['payload']['human_correct'] for e in answers) if answers else '',
                             'mean_seconds': statistics.mean(e['payload']['elapsed_seconds'] for e in answers) if answers else '',
                             'mean_confidence': statistics.mean(e['payload']['confidence'] for e in answers) if answers else ''})
        for answer in answers:
            row = {'participant_id': pid, **answer['payload']}
            row['ai_shown'] = json.dumps(row['ai_shown'])
            trials.append(row)
        if questionnaire:
            questionnaires.append({'participant_id': pid, **questionnaire['payload']})
    csv_file(output / 'participants.csv', participants,
             ['participant_id', 'condition', 'assignment_method', 'version', 'dataset_sha256', 'started_at', 'trial_ids',
              'attention_attempts', 'attention_passed', 'responses', 'completed', 'accuracy', 'mean_seconds', 'mean_confidence'])
    csv_file(output / 'trials.csv', trials,
             ['participant_id', 'trial_id', 'condition', 'position', 'answer', 'confidence', 'true_label',
              'human_correct', 'ai_prediction', 'ai_correct', 'agrees_with_ai', 'displayed_at', 'submitted_at',
              'elapsed_seconds', 'long_trial', 'ai_shown'])
    csv_file(output / 'questionnaires.csv', questionnaires,
             ['participant_id', 'condition', 'effort', 'completed_at', 'total_elapsed_seconds'])
    summary = {'note': 'Descriptive summaries of completed participants only; no significance or causal claims. '
                        'AI accuracy is weighted by actual trial exposures, not unique posting IDs.', 'conditions': {}}
    for condition in ('baseline', 'assisted'):
        people = [p for p in participants if p['completed'] and p['condition'] == condition]
        ids = {p['participant_id'] for p in people}
        observed = [r for r in trials if r['participant_id'] in ids]
        q = [r for r in questionnaires if r['participant_id'] in ids]
        summary['conditions'][condition] = {
            'completed_participants': len(people), 'trial_responses': len(observed),
            'mean_participant_accuracy': statistics.mean(p['accuracy'] for p in people) if people else None,
            'ai_accuracy_on_received_trials': statistics.mean(r['ai_correct'] for r in observed) if observed else None,
            'mean_participant_seconds': statistics.mean(p['mean_seconds'] for p in people) if people else None,
            'mean_participant_confidence': statistics.mean(p['mean_confidence'] for p in people) if people else None,
            'mean_effort': statistics.mean(r['effort'] for r in q) if q else None,
            'long_trials_over_300s': sum(r['long_trial'] for r in observed),
        }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['local', 'sheets'], required=True)
    parser.add_argument('--db', default='data/local.sqlite3')
    parser.add_argument('--secrets', default='.streamlit/secrets.toml')
    parser.add_argument('--output', default='exports')
    args = parser.parse_args()
    if args.source == 'sheets':
        with open(args.secrets, 'rb') as f:
            store = SheetsStore(tomllib.load(f)['google_sheets'])
    else:
        if not Path(args.db).exists():
            parser.error('Local database does not exist.')
        store = SQLiteStore(args.db)
    summary = export(store.read(), args.output)
    print(json.dumps(summary, indent=2))
    print('Exported participant, trial, and questionnaire CSVs to', args.output)


if __name__ == '__main__':
    main()
