"""scripts/usability_report.py: SUS scoring, time parsing, NFR1 per participant, data checks (hand-calculated values)."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "usability_report", Path(__file__).resolve().parents[2] / "scripts" / "usability_report.py")
ur = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ur)


def test_sus_scoring_hand_values():
    assert ur.sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0
    assert ur.sus_score([3] * 10) == 50.0
    # odd items (4,4,4,5,4) -> 3+3+3+4+3 = 16; even items (2,1,2,2,3) -> 3+4+3+3+2 = 15; (16+15) x 2.5
    assert ur.sus_score([4, 2, 4, 1, 4, 2, 5, 2, 4, 3]) == 77.5
    with pytest.raises(ur.DataError):
        ur.sus_score([3] * 9)
    with pytest.raises(ur.DataError):
        ur.sus_score([3] * 9 + [6])


def test_time_parsing():
    assert ur.seconds("1:05") == 65
    assert ur.seconds("0:48") == 48
    assert ur.seconds("75") == 75
    assert ur.mmss(173) == "2:53"
    for bad in ("1:75", "abc", "1:2:3"):
        with pytest.raises(ur.DataError):
            ur.seconds(bad)


def write(d: Path, name: str, text: str):
    (d / name).write_text(text)


@pytest.fixture
def data(tmp_path):
    write(tmp_path, "participants.csv", "participant,role,device,background\n"
          "P1,kitchen,phone,student\nP2,inventory,laptop,student\n")
    write(tmp_path, "tasks.csv", "participant,task,outcome,time,errors,seq\n"
          "P1,K1,S,0:48,0,6\nP1,K2,A,2:30,1,3\nP1,K3,S,1:10,0,6\nP1,K4,F,3:00,2,2\nP1,K5,S,0:55,0,7\n"
          "P2,I1,S,1:30,0,5\nP2,I3,S,2:40,1,4\nP2,I4,A,1:50,1,3\n")
    write(tmp_path, "sus.csv", "participant,q1,q2,q3,q4,q5,q6,q7,q8,q9,q10\n"
          "P1,4,2,4,1,4,2,5,2,4,3\nP2,3,3,3,3,3,3,3,3,3,3\n")
    write(tmp_path, "problems.csv", "participant,task,severity,description\n"
          "P1,K4,1,\"Did not find the ingredients page, looked under Orders\"\n")
    write(tmp_path, "comments.csv", "participant,comment\nP1,Clear numbers\n")
    return tmp_path


def test_nfr1_per_participant_hand_values(data):
    d = ur.load(data)
    parts = {p["participant"]: p for p in ur.participant_results(d)}
    # P1: core K1 + K3 + K5 = 48 + 70 + 55 = 173 s, all without help -> pass
    assert parts["P1"]["core_time"] == 173 and parts["P1"]["core_ok"] and parts["P1"]["nfr1_tasks"]
    # P2: core I1 + I3 + I4 = 90 + 160 + 110 = 360 s and I4 needed a hint -> fail
    assert parts["P2"]["core_time"] == 360 and not parts["P2"]["core_ok"] and not parts["P2"]["nfr1_tasks"]
    assert parts["P1"]["sus"] == 77.5 and parts["P2"]["sus"] == 50.0


def test_task_table_and_report(data):
    d = ur.load(data)
    k4 = next(t for t in ur.task_results(d) if t["task"] == "K4")
    assert (k4["n"], k4["S"], k4["A"], k4["F"], k4["errors"], k4["seq"]) == (1, 0, 0, 1, 2, 2)
    text = ur.report(d)
    assert "1 of 2 participants" in text
    assert "**63.8**" in text                      # mean of 77.5 and 50 = 63.75
    assert "**NFR1 not met**" in text
    assert "Did not find the ingredients page, looked under Orders" in text


@pytest.mark.parametrize("fname,content,message", [
    ("tasks.csv", "participant,task,outcome,time,errors,seq\nP9,K1,S,0:48,0,6\n", "unknown participant P9"),
    ("tasks.csv", "participant,task,outcome,time,errors,seq\nP1,I1,S,0:48,0,6\n", "not a kitchen task"),
    ("tasks.csv", "participant,task,outcome,time,errors,seq\nP1,K1,X,0:48,0,6\n", "outcome must be S, A or F"),
    ("tasks.csv", "participant,task,outcome,time,errors,seq\nP1,K1,S,0:48,0,9\n", "seq must be 1 to 7"),
    ("sus.csv", "participant,q1,q2,q3,q4,q5,q6,q7,q8,q9,q10\nP1,4,2,4,1,4,2,5,2,4,8\n", "sus.csv row 2"),
    ("participants.csv", "participant,role,device,background\nP1,chef,phone,x\n", "role must be"),
])
def test_bad_data_is_reported_with_its_row(data, fname, content, message):
    write(data, fname, content)
    with pytest.raises(ur.DataError, match=message):
        ur.load(data)


def test_empty_templates_give_a_report_without_errors(tmp_path):
    for name, header in (("participants.csv", "participant,role,device,background"),
                         ("tasks.csv", "participant,task,outcome,time,errors,seq"),
                         ("sus.csv", "participant," + ",".join(f"q{i}" for i in range(1, 11))),
                         ("problems.csv", "participant,task,severity,description")):
        write(tmp_path, name, header + "\n")
    assert "No participants recorded yet." in ur.report(ur.load(tmp_path))
