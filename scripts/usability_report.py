"""Analyse the usability test (docs/usability/PLAN.md) and write docs/usability/RESULTS.md.

Reads the CSV files in docs/usability/data (formats in that folder's README.md), checks them, and reports per-task
success, time and ease (SEQ), each participant's SUS score, the NFR1 result and the problems found.

Usage: .venv/bin/python scripts/usability_report.py [data_dir] [output.md]
"""
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = {"kitchen": ["K1", "K2", "K3", "K4", "K5", "K6", "K7"], "inventory": ["I1", "I2", "I3", "I4", "I5"],
         "admin": ["A1", "A2", "A3", "A4"]}
CORE = {"kitchen": ["K1", "K3", "K5"], "inventory": ["I1", "I3", "I4"], "admin": ["A1", "A2", "A3"]}
ROLE_NAME = {"kitchen": "Food Production Manager", "inventory": "Inventory & Procurement Manager",
             "admin": "System Administrator"}
CORE_LIMIT_S = 300   # NFR1: the three core tasks in 5 minutes or less
SUS_TARGET = 68      # NFR1 and the usual average benchmark
OUTCOMES = {"S": "success", "A": "with a hint", "F": "failed"}


class DataError(ValueError):
    pass


def sus_score(answers) -> float:
    """Standard SUS scoring (Brooke, 1996): odd items score answer-1, even items 5-answer; the sum times 2.5."""
    a = [int(x) for x in answers]
    if len(a) != 10 or any(x < 1 or x > 5 for x in a):
        raise DataError(f"SUS needs ten answers from 1 to 5, got {answers}")
    return sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(a)) * 2.5


def seconds(text: str) -> int:
    """'m:ss' (or plain seconds) to seconds."""
    text = text.strip()
    try:
        if ":" in text:
            m, s = text.split(":")
            if not 0 <= int(s) < 60:
                raise ValueError
            return int(m) * 60 + int(s)
        return int(text)
    except ValueError:
        raise DataError(f"time must look like 1:05, got {text!r}")


def mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def load(data_dir: Path) -> dict:
    """Read and check all files; raise DataError with the file and row on the first problem."""
    people = {}
    for n, r in enumerate(read(data_dir / "participants.csv"), start=2):
        if r["role"] not in TASKS:
            raise DataError(f"participants.csv row {n}: role must be kitchen, inventory or admin")
        if r["participant"] in people:
            raise DataError(f"participants.csv row {n}: {r['participant']} appears twice")
        people[r["participant"]] = r

    tasks = []
    for n, r in enumerate(read(data_dir / "tasks.csv"), start=2):
        where = f"tasks.csv row {n}"
        p = people.get(r["participant"])
        if p is None:
            raise DataError(f"{where}: unknown participant {r['participant']}")
        if r["task"] not in TASKS[p["role"]]:
            raise DataError(f"{where}: task {r['task']} is not a {p['role']} task")
        if r["outcome"] not in OUTCOMES:
            raise DataError(f"{where}: outcome must be S, A or F")
        try:
            seq = int(r["seq"]) if r["seq"] else None
            errors = int(r["errors"] or 0)
        except ValueError:
            raise DataError(f"{where}: errors and seq must be whole numbers")
        if seq is not None and not 1 <= seq <= 7:
            raise DataError(f"{where}: seq must be 1 to 7")
        try:
            secs = seconds(r["time"])
        except DataError as e:
            raise DataError(f"{where}: {e}")
        tasks.append({**r, "seconds": secs, "errors": errors, "seq": seq})
    seen = set()
    for t in tasks:
        key = (t["participant"], t["task"])
        if key in seen:
            raise DataError(f"tasks.csv: {key[0]} {key[1]} appears twice")
        seen.add(key)

    sus = {}
    for n, r in enumerate(read(data_dir / "sus.csv"), start=2):
        if r["participant"] not in people:
            raise DataError(f"sus.csv row {n}: unknown participant {r['participant']}")
        try:
            sus[r["participant"]] = sus_score([r[f"q{i}"] for i in range(1, 11)])
        except (DataError, ValueError) as e:
            raise DataError(f"sus.csv row {n}: {e}")

    problems = []
    for n, r in enumerate(read(data_dir / "problems.csv"), start=2):
        if r["severity"] not in ("1", "2", "3"):
            raise DataError(f"problems.csv row {n}: severity must be 1, 2 or 3")
        problems.append(r)
    comments = read(data_dir / "comments.csv") if (data_dir / "comments.csv").exists() else []
    return {"people": people, "tasks": tasks, "sus": sus, "problems": problems, "comments": comments}


def participant_results(d: dict) -> list[dict]:
    out = []
    for pid, p in d["people"].items():
        mine = {t["task"]: t for t in d["tasks"] if t["participant"] == pid}
        core = CORE[p["role"]]
        missing = [c for c in core if c not in mine]
        core_time = sum(mine[c]["seconds"] for c in core if c in mine)
        core_ok = not missing and all(mine[c]["outcome"] == "S" for c in core)
        out.append({"participant": pid, "role": p["role"], "device": p["device"], "core_time": core_time,
                    "core_ok": core_ok, "missing": missing, "sus": d["sus"].get(pid),
                    "nfr1_tasks": core_ok and core_time <= CORE_LIMIT_S})
    return out


def task_results(d: dict) -> list[dict]:
    out = []
    for role, ids in TASKS.items():
        for tid in ids:
            rows = [t for t in d["tasks"] if t["task"] == tid]
            if not rows:
                continue
            seqs = [t["seq"] for t in rows if t["seq"] is not None]
            out.append({"task": tid, "role": role, "core": tid in CORE[role], "n": len(rows),
                        "S": sum(t["outcome"] == "S" for t in rows), "A": sum(t["outcome"] == "A" for t in rows),
                        "F": sum(t["outcome"] == "F" for t in rows),
                        "median_time": statistics.median(t["seconds"] for t in rows),
                        "errors": sum(t["errors"] for t in rows),
                        "seq": statistics.mean(seqs) if seqs else None})
    return out


def report(d: dict) -> str:
    parts = participant_results(d)
    tasks = task_results(d)
    scores = [p["sus"] for p in parts if p["sus"] is not None]
    n = len(parts)
    lines = ["# Usability test results", "",
             "Generated by `scripts/usability_report.py` from `docs/usability/data/`. Participants were students or "
             "friends who had not used the system, not restaurant staff; with this few participants the figures are "
             "indicative, not statistically representative.", ""]
    if not n:
        return "\n".join(lines + ["No participants recorded yet."]) + "\n"

    by_role = {r: sum(p["role"] == r for p in parts) for r in TASKS}
    passed = sum(p["nfr1_tasks"] for p in parts)
    lines += ["## Summary", "", "| Measure | Result | Target |", "|---|---|---|",
              f"| Participants | {n} ({', '.join(f'{v} {k}' for k, v in by_role.items() if v)}) | 5-8 |",
              f"| Core tasks done without help in 5:00 or less (NFR1) | {passed} of {n} participants | all |"]
    if scores:
        sd = statistics.stdev(scores) if len(scores) > 1 else 0.0
        lines.append(f"| Mean SUS score (NFR1) | **{statistics.mean(scores):.1f}** (sd {sd:.1f}, range "
                     f"{min(scores):g}-{max(scores):g}, n = {len(scores)}) | {SUS_TARGET} or more |")
    all_seq = [t["seq"] for t in d["tasks"] if t["seq"] is not None]
    if all_seq:
        lines.append(f"| Mean ease per task (SEQ, 1-7) | {statistics.mean(all_seq):.1f} | 5.5 or more |")
    nfr1 = passed == n and scores and statistics.mean(scores) >= SUS_TARGET
    lines += ["", f"**NFR1 {'met' if nfr1 else 'not met'}** on this sample"
              + ("." if nfr1 else ": see the participant table and the problems below."), ""]

    lines += ["## Tasks", "", "★ = core task (NFR1). S success, A with a hint, F failed.", "",
              "| Task | Role | n | S | A | F | Median time | Errors | Mean SEQ |", "|---|---|---|---|---|---|---|---|---|"]
    for t in tasks:
        lines.append(f"| {t['task']}{' ★' if t['core'] else ''} | {ROLE_NAME[t['role']]} | {t['n']} | {t['S']} | {t['A']} | "
                     f"{t['F']} | {mmss(t['median_time'])} | {t['errors']} | "
                     f"{'-' if t['seq'] is None else f'{t['seq']:.1f}'} |")

    lines += ["", "## Participants", "", "| Participant | Role | Device | Core tasks without help | Core time | NFR1 tasks | SUS |",
              "|---|---|---|---|---|---|---|"]
    for p in parts:
        core = "missing " + ", ".join(p["missing"]) if p["missing"] else ("yes" if p["core_ok"] else "no")
        lines.append(f"| {p['participant']} | {ROLE_NAME[p['role']]} | {p['device']} | {core} | {mmss(p['core_time'])} | "
                     f"{'pass' if p['nfr1_tasks'] else 'fail'} | {'-' if p['sus'] is None else f'{p['sus']:g}'} |")

    lines += ["", "## Problems found", ""]
    if d["problems"]:
        lines += ["Severity: 1 prevents the task, 2 delay or error recovered from, 3 cosmetic.", "",
                  "| Severity | Task | Participant | Problem |", "|---|---|---|---|"]
        for pr in sorted(d["problems"], key=lambda r: (r["severity"], r["task"])):
            lines.append(f"| {pr['severity']} | {pr['task']} | {pr['participant']} | {pr['description']} |")
    else:
        lines.append("None recorded.")
    if d["comments"]:
        lines += ["", "## Comments", ""] + [f"- {c['participant']}: \"{c['comment']}\"" for c in d["comments"]]
    return "\n".join(lines) + "\n"


def main(argv):
    data_dir = Path(argv[1]) if len(argv) > 1 else ROOT / "docs" / "usability" / "data"
    out = Path(argv[2]) if len(argv) > 2 else ROOT / "docs" / "usability" / "RESULTS.md"
    try:
        d = load(data_dir)
    except DataError as e:
        print(f"Data problem: {e}", file=sys.stderr)
        return 1
    out.write_text(report(d))
    print(f"wrote {out} ({len(d['people'])} participants, {len(d['tasks'])} task rows, {len(d['sus'])} SUS forms)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
