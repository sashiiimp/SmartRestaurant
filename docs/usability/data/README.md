# Usability results: data files

Type each session's sheets into these CSV files (UTF-8, comma-separated, one header row). Use anonymous ids only
(P1, P2 ...); never names. Then run `.venv/bin/python scripts/usability_report.py`, which checks the files and writes
`docs/usability/RESULTS.md`.

| File | Columns | Values |
|---|---|---|
| `participants.csv` | participant, role, device, background | role: `kitchen`, `inventory` or `admin`; device: `phone` or `laptop`; background: one line, no name |
| `tasks.csv` | participant, task, outcome, time, errors, seq | task: `K1`-`K7`, `I1`-`I5`, `A1`-`A4` (K6, K7 added 9 Oct 2026: preparation done, other food use); outcome: `S` success, `A` success after a hint, `F` failed; time: `m:ss` (for example `1:05`); errors: whole number; seq: 1-7 |
| `sus.csv` | participant, q1 ... q10 | each answer 1 (strongly disagree) to 5 (strongly agree), exactly as ticked; the script does the SUS scoring |
| `problems.csv` | participant, task, severity, description | severity: 1 prevents the task, 2 delay or error recovered from, 3 cosmetic; quote the description if it contains a comma |
| `comments.csv` | participant, comment | Answers to the closing questions and notable quotes; quote the text if it contains a comma |

Core tasks (NFR1): kitchen K1, K3, K5; inventory I1, I3, I4; administrator A1, A2, A3.

Example rows:

```
participants.csv   P1,kitchen,phone,IT student who orders food online
tasks.csv          P1,K1,S,0:48,0,6
sus.csv            P1,4,2,4,1,4,2,5,2,4,3
problems.csv       P1,K3,2,"Looked for 'record prepared' on the Served & waste page first"
comments.csv       P1,"The numbers under each item made it clear why it said 114"
```
