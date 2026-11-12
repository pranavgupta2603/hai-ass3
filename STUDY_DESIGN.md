# A3-1 design and measurement rationale

## Research question
Does access to the Assignment 2 classifier improve classmates' ability to distinguish real job postings from scams, and how does it affect confidence, efficiency, and perceived effort?

The hypothesis from Assignment 2 is human–AI joint performance > AI-only > human-only. This is a hypothesis, not a measured result. The original AI scored 175/200 (87.5%) on the full balanced bank, with 19 missed scams and 6 false alarms. Comparisons in this study also compute AI correctness on each participant's actual five trials.

## Conditions and workflow
A between-participants study assigns each uniqname to baseline or assisted using a secret-seeded pseudorandom procedure. Randomization is persistent and independent of labels sampled. Each person receives five unique trials, with either two or three scams and the complementary number of real postings. The sample is shuffled and differs across participants. The balanced trial bank intentionally differs from real-world scam prevalence.

Workflow: identify participant → acknowledge data collection → instructions → easy attention check → five judgments/confidence ratings → effort question → confirmed completion.

The baseline presents title, company profile, description, requirements, salary, and company-logo presence. The assisted interface adds the saved model prediction, estimated scam probability, confidence category, supporting keywords, and company signals. Showing the panel automatically ensures assistance is available on every assisted trial. AI confidence is labeled separately from the participant's confidence.

The asynchronous model outputs are exactly those exported in Assignment 2. This avoids model drift and allows all participants viewing a given trial to receive the same assistance. The synchronous-output bonus is not implemented.

## Measurements

| Measure | Operationalization | Rationale |
| --- | --- | --- |
| Performance | Fraction of correct decisions per participant; scam recall/false alarms can be computed from exported responses | Directly evaluates the task objective and the two types of mistakes |
| Confidence | Required ordinal 1–5 rating after each judgment, before submission | Assistance may increase confidence even when wrong; compare correctness-conditioned confidence as well as overall confidence |
| Efficiency | First recorded trial exposure to submitted response, in seconds | Tests whether reading AI output saves time or adds effort; includes interruptions and is not active attention |
| Effort | Required final ordinal 1–7 response to “How mentally demanding was this task?” | Measures perceived cognitive demand that task accuracy alone cannot capture; this is a single-item measure, not a validated full NASA-TLX instrument |
| AI agreement | Whether assisted responses match the saved AI prediction, split by AI correctness | Describes appropriate/inappropriate agreement; does not prove that assistance changed an initial judgment |

Analyze at participant level for condition comparisons; repeated trials from the same person are not independent participants. Report sample sizes, incomplete sessions, trial sampling, and uncertainty. Small class samples and unequal trial difficulty limit conclusions. Do not invent a statistical significance claim from descriptive summaries.

## Attention and fairness
The check asks what participants will decide: whether a posting is real or a scam. It tests the instructions rather than job-domain expertise. Failed attempts receive corrective feedback; participants can retry without termination. Attempts are recorded for transparent reporting; this protocol does not automatically exclude participants for one error.

## Requirement mapping

1. Baseline interface and backend: Streamlit interface, Google Sheets persistence, instructions and durable response confirmation.
2. Random N trials under ten minutes: five persistent randomly sampled trials; under-ten-minute target remains subject to a human timing pilot.
3. Additional measurement: trial confidence, elapsed time, and final perceived effort, linked by participant ID.
4. Attention check: simple instruction question with tolerant retry behavior and recorded attempts.
5. Assisted interface: static, saved Assignment 2 predictions and explanations, shown automatically and logged exactly.

## Before launch
Configure a new private Sheet, deploy the app, verify real backend permissions using a pilot Sheet, and complete timed human pilots in both conditions. Use the main URL for randomized assignment. Explicit condition URLs and legacy preview URLs both require sign-in and save data; condition-linked assignment is recorded separately. Use local mode or a separate pilot Sheet for grading demonstrations. Do not mix pilot records into the final study Sheet. Keep the dataset, protocol, salt and version unchanged once collection starts.
