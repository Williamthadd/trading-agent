from tradingagents.webapp.storage import LocalJsonRunStore, build_run_store


def test_local_run_store_persists_runs_and_orders_events(tmp_path):
    store = LocalJsonRunStore(tmp_path)
    created = store.create_run(
        {
            "run_id": "run-001",
            "ticker": "AAPL",
            "date_key": "2026-08-15",
            "status": "queued",
        }
    )

    store.append_event("run-001", {"event_id": "second", "sequence": 2, "text": "B"})
    store.append_event("run-001", {"event_id": "first", "sequence": 1, "text": "A"})
    updated = store.update_run("run-001", {"status": "completed"})

    assert created["run_id"] == "run-001"
    assert updated["status"] == "completed"
    assert [event["text"] for event in store.get_events("run-001")] == ["A", "B"]
    assert [run["run_id"] for run in store.list_runs("2026-08-15")] == ["run-001"]
    assert store.list_runs("2026-08-14") == []
    assert store.list_runs_by_statuses({"completed"})[0]["run_id"] == "run-001"
    assert store.list_runs_by_statuses({"running"}) == []

    reloaded = LocalJsonRunStore(tmp_path)
    assert reloaded.get_run("run-001")["status"] == "completed"
    assert len(reloaded.get_events("run-001")) == 2


def test_build_run_store_can_be_forced_to_local_json(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path))

    store = build_run_store()

    assert isinstance(store, LocalJsonRunStore)
    assert store.backend_name == "local-json"
    assert store.configured is False
