import backend.engine.learning as learning


def test_duplicate_open_signal_and_new_signal_after_close(tmp_path, monkeypatch):
    # Använd en separat, tillfällig SQLite-databas.
    # Den riktiga databasen och dess historik lämnas orörda.
    monkeypatch.setattr(learning, "DATABASE_URL", "")
    monkeypatch.setattr(learning, "DB", str(tmp_path / "signals.db"))

    candidate = {
        "symbol": "TEST",
        "detected_at": "2026-01-01T00:00:00+00:00",
        "trade_plan": {
            "entry": 10,
            "stop_loss": 9,
            "target_1": 12,
        },
        "score": 80,
        "confidence": 70,
        "signal": "KÖPSETUP",
    }

    # Samma symbol ska inte skapa en dubblett när signalen är öppen.
    first_id = learning.record_signal(candidate)
    duplicate_id = learning.record_signal(candidate)

    assert duplicate_id == first_id

    # Efter stängning ska en ny signal kunna registreras.
    learning.close_signal(first_id, "FLAT", 10, 0)
    reopened_id = learning.record_signal(candidate)

    assert reopened_id != first_id
