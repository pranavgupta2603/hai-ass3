# Assignment 3 — Job Posting Study

Live study: https://gpranav-job-study.streamlit.app/

Condition links: [baseline](https://gpranav-job-study.streamlit.app/?condition=baseline) · [AI-assisted](https://gpranav-job-study.streamlit.app/?condition=assisted). Both require sign-in and save responses. Old `?preview=` links now behave identically. There is no anonymous, unsaved public preview.

Source: https://github.com/pranavgupta2603/hai-ass3 (public, as requested; includes the study dataset and answer labels, but no credentials or participant records).

One Streamlit app implements baseline and AI-assisted conditions for the final Assignment 2 dataset. The deployed study uses a private Google Sheet; SQLite is an explicit local testing option. Every public entry point requires sign-in and uses the configured persistent backend.

## Run locally (Python 3.11+)

From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ASS3_MODE=local streamlit run app.py
```

Open the printed localhost URL. Local responses go to ignored `data/local.sqlite3`. Use invented test uniqnames. Do not deploy with `ASS3_MODE=local`: hosted local files are not reliable durable storage.

Condition URLs (both require sign-in and save):

- `http://localhost:8501/?condition=baseline`
- `http://localhost:8501/?condition=assisted`

Use these suffixes on the deployed app for condition-specific collection. The base URL randomly assigns a condition. Existing participants always resume their saved condition; changing links does not reassign them. Old `?preview=baseline` and `?preview=assisted` links are compatibility aliases that now require sign-in and save too. Do not use any hosted link for disposable testing: use explicit local mode or a separate pilot Sheet.

## Configure the private Google Sheet

1. Create a **new private Ass3 Google Sheet**, separate from Ass1. Keep it private; share it as Editor only with the Google service-account email used by the application and appropriate study organizers.
2. Enable the Google Sheets API in the service account's Google Cloud project. You may reuse the Ass1 service account, but use a new spreadsheet.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Fill in the spreadsheet ID and service-account fields. Generate an assignment salt with `python -c "import secrets; print(secrets.token_hex(32))"`. Never commit real secrets.
4. Run `python setup_sheet.py` once. It creates the `events` tab and header if missing and refuses to overwrite unrelated data.
5. Run `streamlit run app.py` without `ASS3_MODE=local`. Without valid configuration, the real study refuses to accept participants.

The sheet contains an append-only event log: `event_id`, `participant_id`, `kind`, `recorded_at`, `payload_json`. It records session, attention-check attempt/pass, first trial exposure, submitted response, and final questionnaire events. JSON preserves the exact AI output displayed without expanding the sheet into dozens of mostly empty columns. Use the exporter below for analysis-ready tables.

## Deploy on Streamlit Community Cloud

1. Put this folder's source and `study_with_ai.csv` in a GitHub repository. Exclude `.streamlit/secrets.toml`, `data/`, `exports/`, local environments, and test participant records.
2. In Streamlit Community Cloud, create an app from that repository, selecting `app.py` (or `Ass3/app.py` if it is a subfolder), and Python 3.11 or later.
3. Paste the real secrets TOML into the app's **Advanced settings → Secrets**. Never put credentials into repository files. Leave `study.mode = "study"`.
4. Deploy. Verify a complete flow against a separate pilot Google Sheet, including refresh, retry, and final questionnaire. Set the final empty study sheet before collecting classmate responses.
5. Share the base URL with participants. The two condition URLs also collect real responses; use local mode or a separate pilot Sheet for demonstrations.

Official instructions: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

The source package supports deployment using these steps. Live hosting status is recorded in the delivery notes; credentials are configured privately and are never included in the repository or ZIP.

## Study protocol

- Participants enter their own UMich uniqname, acknowledge recorded data, read instructions, and pass an easy instruction question. Incorrect attempts receive corrective feedback and may be retried.
- A secret-seeded pseudorandom assignment fixes the condition and five trial IDs for each participant. Conditions are approximately balanced in expectation, not forcibly balanced in a small class. Trial selection is stratified: 2/3 or 3/2 real/scam, shuffled. The same procedure is used in both conditions.
- Return with the same uniqname to resume. Uniqname is an identifier, **not authentication**; this has the same trust assumption as the Ass1 class interface. Do not treat this as suitable for sensitive or adversarial studies.
- Both conditions show identical posting fields and logo-presence information. AI assistance appears automatically below the posting in the assisted condition. All details are visible without opening task-content expanders.
- Each response requires Real/Scam and confidence 1–5; neither is preselected. Responses are locked after submission. There is no answer feedback during the study.
- A final effort rating (1–7) completes the study. The completion page appears only after storage confirms the final event.
- All public routes collect real responses. A condition link sets the first assignment, while the base URL randomizes it. Existing saved assignments cannot be overridden by query parameters. The assignment method is exported; use the base URL for the randomized experiment.

## Timing and pilot

Five postings is a provisional choice. Budget roughly 1–2 minutes for instructions/check, 5–6 minutes for decisions, and under a minute for the final question. **A human timing pilot is still required**: automated tests do not establish completion under ten minutes. If needed, revise the protocol/trial count before collection, update all five-trial UI wording and tests, and use a new study version/sheet.

Trial elapsed time runs from the first server-recorded exposure to submission and survives refresh. It includes pauses, returning later, rendering and network latency; it is not active attention time. Trials over 300 seconds are flagged, not silently removed. Total time includes instructions and the questionnaire. Document any exclusion rule before analyzing outcomes.

Freeze the dataset, `VERSION`, assignment salt, and protocol during collection. The dataset SHA-256 is saved per participant; the app refuses to continue an existing assignment against a changed dataset. The copied CSV is byte-identical to Ass2's saved predictions. Predictions come from `ai_prediction`, never from the rounded score.

## Export and analyze (organizer only)

```sh
python export_results.py --source local --output exports/local
python export_results.py --source sheets --output exports/study
```

Outputs:

- `participants.csv`: assignments, instruction-check attempts, progress, completion, and participant-level means.
- `trials.csv`: judgments, confidence, elapsed time, truth, AI baseline correctness and exact AI content shown (null in baseline).
- `questionnaires.csv`: linked effort responses, completion timestamps, and total duration.
- `summary.json`: descriptive condition summaries for completed participants, including the AI-only accuracy on trials they actually received.

Keep these files private. Incomplete participants remain in exports but are excluded from the summary. Participant means avoid treating a person's repeated answers as independent participants. No significance tests or causal conclusions are implied. Human/AI agreement is descriptive; this design does not collect an initial unaided response from assisted participants.

## Reliability and limits

SQLite uses unique event IDs and transactions. Google Sheets uses RAW append operations, a process lock, and read-after-write confirmation. Repeated submissions have stable event IDs; readers/exporters keep the first event when a timeout or concurrent worker produces duplicate physical rows. Never delete/reorder raw event rows during collection. Sheets is not a transactional database, so multi-worker races can create duplicate physical rows even though they resolve to one logical response. Use a single Streamlit deployment and this exporter, not raw row counts, for the class study.

An unavailable backend stops progression and offers retry. There is no silent production fallback to local files. The app neither displays ground-truth labels nor exposes result downloads. The study CSV remains server-side, but a public source repository would make it publicly accessible; use a private repository when restricting access to the trial bank matters.

## Verification

```sh
pip install pytest
python -m pytest -q
```

Tests cover condition/trial assignment, stratification, concurrent SQLite saves, Sheets uncertain-write recovery using a fake transport, persistent sign-in and five saved responses through every condition link, including legacy URLs, missing production configuration, validation, failed attention check recovery, complete flows in both conditions, sign-in/resume, completion locking, and exports.

See `STUDY_DESIGN.md` for the measurement rationale and assignment mapping.

## Configured backend for this installation

The supplied spreadsheet already contained `annotations` and `ass3` tabs. Those were preserved. This installation uses a separate `ass3_events` tab in the same private spreadsheet. A single `__system__` connection-check event verifies write/read access and is excluded from participant exports because it has no study session. Real credentials are in the ignored local `.streamlit/secrets.toml`, with owner-only file permissions.
