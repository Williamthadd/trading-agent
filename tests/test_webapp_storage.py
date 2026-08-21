from tradingagents.webapp.storage import FirestoreRunStore, LocalJsonRunStore, build_run_store


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


def test_firestore_update_does_not_read_document_after_successful_merge(tmp_path):
    class DocumentReference:
        def __init__(self):
            self.writes = []

        def set(self, payload, merge=False):
            self.writes.append((dict(payload), merge))

    class CollectionReference:
        def __init__(self):
            self.documents = {}

        def document(self, document_id):
            return self.documents.setdefault(document_id, DocumentReference())

    class Client:
        def __init__(self):
            self.collections = {}

        def collection(self, name):
            return self.collections.setdefault(name, CollectionReference())

    client = Client()
    store = FirestoreRunStore(client, LocalJsonRunStore(tmp_path))
    store.create_run({"run_id": "run-001", "status": "queued"})

    updated = store.update_run("run-001", {"status": "running"})

    reference = client.collection("trading_runs").document("run-001")
    assert reference.writes[-1][1] is True
    assert updated["run_id"] == "run-001"
    assert updated["status"] == "running"
    assert store.configured is True
