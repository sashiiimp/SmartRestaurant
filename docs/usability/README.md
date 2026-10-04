# Usability test kit (step 4)

Everything needed to run the usability test with 5 to 8 first-time users and to report the result (NFR1).

| File | Use |
|---|---|
| `PLAN.md` | Test plan: goal, participants, measures and targets, set-up, session running order, briefing script, observer rules, analysis, ethics |
| `KIT.md` / `SmartRestaurant_Usability_Kit.docx` | Printable materials: information and consent sheet, task cards per role, ease question after each task, SUS questionnaire, observer sheet, closing questions |
| `data/*.csv` | Empty files to type the results into (formats in `data/README.md`) |
| `RESULTS.md` | Generated results, ready for report section 10.4 |
| `../../scripts/usability_answers.py` | Prints the observer's answer key for today's demo data (read-only) |
| `../../scripts/usability_report.py` | Checks the CSV files and writes `RESULTS.md` |

## Checklist per session

1. `FLASK_APP=wsgi.py .venv/bin/flask smartrest demo-reset` (resets the demo; never during a real demonstration).
2. `.venv/bin/python scripts/usability_answers.py` and give the printout to the observer.
3. Log the participant in with the role's account; hand over the consent sheet, then the task cards one by one.
4. After the session, type the sheets into `data/*.csv`; when all sessions are done run
   `.venv/bin/python scripts/usability_report.py`.

## Pilot (4 October 2026)

Every task that changes data was run once through the services on the demo data and checked against the answer key;
all passed, and the demo was reset afterwards. Two findings were added to the answer key: after the chicken delivery an
alert for a *later* day can remain (correct behaviour), and a waste alert about Chicken *Kottu* could be mistaken for
the chicken stock alert. The pilot checked the tasks and answers, not the interface: that is what the sessions test.
