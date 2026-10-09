# Usability test plan (step 4, NFR1)

## 1. Goal

Measure whether first-time users can do the daily work of each role without help, and how usable they find the
system. This provides the evidence for **NFR1** ("simple enough for non-technical staff"), defined in
`docs/REQUIREMENTS.md` as:

> A first-time user completes the **3 core tasks for their role** without help in **5 minutes or less**, and the
> **SUS score is 68 or more**.

Results go into report section 10.4 and the NFR1 row of section 11.4.

## 2. Participants

- **Pilot restaurant staff first (added 9 Oct 2026).** If a partner outlet agrees, test **2 to 3 real staff**: the
  kitchen manager or a senior cook (kitchen role), the storekeeper (inventory role) and the owner or manager
  (administrator role). They are the proposal's intended users (NFR1 "non-technical staff"); report them separately
  from the students. Their sessions follow the same tasks, sheets and rules. **[TEAM: name the outlet only if it agrees
  in writing; otherwise describe it as "a fast-food outlet in Colombo".]**
- **Plus 3 to 5 students or friends** who have **never used SmartRestaurant** and were not involved in building it.
  Team members cannot take part.
- One role per participant. Aim for at least **3 kitchen** participants (the main daily user), **2 inventory** and
  **1 to 2 administrator**. The Food Production Manager role should preferably be tested on a **phone**.
- Record only an anonymous id (P1, P2 ...), role, device and a short background line (for example "IT student, uses
  food apps"). Do not record names in the results files; consent forms stay on paper or in a private folder.
- In the report, state who the participants were (staff of one outlet and/or students), how many, and that with this
  few participants the figures are indicative (limitation).

## 3. Measures

| Measure | How | Target |
|---|---|---|
| Task success | Observer marks each task: **S** success without help, **A** success with a hint, **F** failed or gave up | Core tasks: all S |
| Core-task time | Stopwatch from "start" to the observer seeing the result, summed over the 3 core tasks (★) | **5 minutes or less** (NFR1) |
| Errors | Count of wrong paths or wrong entries the participant had to undo | Reported, no target |
| Ease per task | Single Ease Question (SEQ): "Overall, how easy or difficult was this task?" 1 (very difficult) to 7 (very easy) | Average 5.5 or more |
| Overall usability | System Usability Scale (SUS), 10 items, after all tasks (Brooke, 1996) | Mean **68 or more** (NFR1; 68 is the usual average benchmark) |
| Comments | Think-aloud notes and the closing interview | Themes and concrete problems |
| All tasks (added 9 Oct 2026) | Share of all tasks marked **S** | **80% or more** without help |
| Problems | Severity per `problems.csv` | **No severity-1 problem** (one that prevents a task) left unfixed |

The NFR1 core tasks stay K1, K3 and K5 for the kitchen so results remain comparable with the original definition;
the two kitchen tasks added on 9 Oct 2026 (K6 mark preparation done, K7 record other food use) are reported as extra
tasks with their own success, time and SEQ.

## 4. Set-up (operator, before each session)

**Changed 9 Oct 2026: sessions never use the live demonstration system.** Participants change data (they accept,
override, record and order), and the earlier instruction to run `demo-reset` on the live server would also replace
the live accounts and model. Sessions run on the **staging instance** (`/srv/smartrest-staging`, its own user
`smartstage`, its own SQLite database and `.env`, reachable only through an SSH tunnel or the operator's laptop),
deployed from the branch that is being tested (including the preparation workflow and other food use).

1. On the server, reset the **staging** demo so every participant starts from the same state (about 20 seconds):
   `cd /srv/smartrest-staging && runuser -u smartstage -- env FLASK_APP=wsgi.py .venv/bin/flask smartrest demo-reset`.
   Check first that the prompt shows `/srv/smartrest-staging`; never run this in `/srv/smartrest`.
2. Print the answer key for today from the same staging copy and give it to the observer:
   `cd /srv/smartrest-staging && runuser -u smartstage -- .venv/bin/python scripts/usability_answers.py`
3. Open the staging login page on the test device (through the tunnel set up by the developer, for example
   `ssh -L 39520:127.0.0.1:39520 ...` then `http://127.0.0.1:39520/login`). Log in for the participant with the
   seeded staging account for the role (`admin`, `kitchen1`, `inventory1`; staging passwords from the staging `.env`,
   given to the operator only): logging in is not a task being tested.
4. Have ready: task cards for the role, SEQ and SUS sheets, observer sheet, stopwatch (phone), pen.

## 5. Session (about 20 to 25 minutes)

| Step | Time | What |
|---|---|---|
| 1 | 2 min | Welcome; read the information sheet together; participant signs consent |
| 2 | 2 min | Briefing (script below); explain thinking aloud |
| 3 | 10-15 min | Tasks one by one: hand over the card, start the stopwatch, observe silently, stop when done; participant answers the SEQ after each task |
| 4 | 3 min | SUS questionnaire |
| 5 | 3 min | Closing questions |
| 6 | 2 min | Thank the participant; observer completes the sheet |

**Briefing script.** "We are testing the system, not you. There are no wrong answers. Please think aloud: say what
you are looking for and what you expect to happen. I cannot help you during a task, because we want to see where the
system is unclear. If you get stuck, say so and we will move on. The data is made up, so nothing you do affects a real
restaurant."

**Rules for the observer.** Do not point or hint. If the participant is stuck for **two minutes** or asks for help,
give one neutral hint ("Where would you look for ...?") and mark the task **A**; if still stuck after another minute,
mark **F** and move on. Note every hesitation, wrong click and comment.

## 6. Analysis

Type the observer sheets and questionnaires into the CSV files in `docs/usability/data/` (formats in that folder's
`README.md`), then run:

```
.venv/bin/python scripts/usability_report.py
```

It checks the files, computes per-task success, median time and mean SEQ, each participant's SUS score and the mean,
the NFR1 result per participant, and writes `docs/usability/RESULTS.md`, ready to paste into report section 10.4.
Problems found go into a table with a severity: **1** prevents the task, **2** causes delay or an error the user
recovers from, **3** cosmetic.

## 7. Ethics and data

Participation is voluntary and can stop at any time; data is anonymous; no recordings are made unless the participant
agrees in writing. **[TEAM: check whether the module or institute requires ethics approval or a specific consent form
for testing with students, and use it instead of the sheet in KIT.md if so.]**

## Reference

Brooke, J. (1996) 'SUS: a "quick and dirty" usability scale', in Jordan, P.W. et al. (eds.) *Usability evaluation in
industry*. London: Taylor and Francis, pp. 189-194.
