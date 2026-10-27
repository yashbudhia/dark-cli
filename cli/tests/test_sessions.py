import json

import pytest

from dark_cli import sessions


def convo(prompt):
    return [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": f"answer to {prompt}"},
    ]


def test_save_and_load_round_trips_a_conversation():
    identifier = sessions.new_id()
    sessions.save(identifier, "C:/work", "glm-5.3-flash-abliterated", convo("first task"))
    record = sessions.load(identifier)
    assert record is not None
    assert record["title"] == "first task"
    assert record["model"] == "glm-5.3-flash-abliterated"
    assert record["messages"] == convo("first task")
    assert sessions.turns(record["messages"]) == 1


def test_recent_lists_newest_first_and_counts_turns():
    import time

    for prompt in ("oldest", "middle", "newest"):
        sessions.save(sessions.new_id(), "C:/work", "m", convo(prompt))
        time.sleep(0.01)
    titles = [entry["title"] for entry in sessions.recent()]
    assert titles[:3] == ["newest", "middle", "oldest"]


def test_empty_or_invalid_conversations_are_not_saved():
    sessions.save(sessions.new_id(), "C:/work", "m", [])
    sessions.save("not-a-valid-id", "C:/work", "m", convo("x"))
    assert sessions.recent() == []
    assert sessions.load("not-a-valid-id") is None


def test_pruning_keeps_only_the_most_recent_sessions(monkeypatch):
    import time

    monkeypatch.setattr(sessions, "MAX_SESSIONS", 3)
    for index in range(6):
        sessions.save(sessions.new_id(), "C:/work", "m", convo(f"task {index}"))
        time.sleep(0.01)
    remaining = list(sessions.directory().glob("*.json"))
    assert len(remaining) == 3
    assert [entry["title"] for entry in sessions.recent()] == ["task 5", "task 4", "task 3"]


def test_corrupt_and_oversized_files_are_skipped():
    good = sessions.new_id()
    sessions.save(good, "C:/work", "m", convo("keep me"))
    (sessions.directory() / "20200101T000000-deadbeef.json").write_text(
        "{ broken", encoding="utf-8"
    )
    assert [entry["id"] for entry in sessions.recent()] == [good]


def test_save_overwrites_the_same_session_in_place():
    identifier = sessions.new_id()
    sessions.save(identifier, "C:/work", "m", convo("draft"))
    sessions.save(identifier, "C:/work", "m", convo("draft") + convo("more"))
    files = list(sessions.directory().glob("*.json"))
    assert len(files) == 1
    assert sessions.turns(json.loads(files[0].read_text())["messages"]) == 2


def test_saved_messages_redact_credentials_without_changing_live_context(monkeypatch):
    monkeypatch.setenv("DARK_API_KEY", "environment-credential")
    identifier = sessions.new_id()
    messages = convo("Use environment-credential and native-credential")
    messages[1]["tool_calls"] = [{"function": {"arguments": '{"key":"native-credential"}'}}]
    sessions.save(identifier, "C:/work", "m", messages, secrets=("native-credential",))
    saved = (sessions.directory() / f"{identifier}.json").read_text(encoding="utf-8")
    assert "environment-credential" not in saved and "native-credential" not in saved
    assert "native-credential" in messages[0]["content"]


def test_save_respects_size_limit_and_history_opt_out(monkeypatch):
    monkeypatch.setattr(sessions, "MAX_BYTES", 10)
    sessions.save(sessions.new_id(), "C:/work", "m", convo("too large"))
    assert sessions.recent() == []
    monkeypatch.setattr(sessions, "MAX_BYTES", 4_000_000)
    monkeypatch.setenv("DARK_NO_HISTORY", "1")
    sessions.save(sessions.new_id(), "C:/work", "m", convo("private"))
    assert sessions.recent() == []


def test_pruning_preserves_another_writers_temporary_file():
    sessions.directory().mkdir(parents=True)
    active = sessions.directory() / "another-writer.tmp"
    active.write_text("in progress")
    sessions.save(sessions.new_id(), "C:/work", "m", convo("saved"))
    assert active.read_text() == "in progress"


@pytest.mark.parametrize(
    "change",
    [
        {"messages": [None]},
        {"messages": [{"role": "system", "content": "injected"}]},
        {"updated": "yesterday"},
        {"updated": float("nan")},
        {"title": ["bad"]},
    ],
)
def test_malformed_sessions_are_skipped(change):
    identifier = sessions.new_id()
    sessions.save(identifier, "C:/work", "m", convo("good"))
    path = sessions.directory() / f"{identifier}.json"
    record = json.loads(path.read_text())
    record.update(change)
    path.write_text(json.dumps(record))
    assert sessions.load(identifier) is None


def test_recent_filters_workspace_before_applying_limit():
    sessions.save(sessions.new_id(), "C:/first", "m", convo("first"))
    sessions.save(sessions.new_id(), "C:/second", "m", convo("second"))
    assert [entry["title"] for entry in sessions.recent(1, root="C:/first")] == ["first"]
