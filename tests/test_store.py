from journal_app.crypto import new_dek
from journal_app.store import (
    connect,
    create_entry,
    delete_entry,
    get_entry,
    list_entries,
    plain_text,
    update_entry,
)

DOC = {
    "type": "doc",
    "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "The river was high."}]}
    ],
}


def test_entries_roundtrip_search_and_do_not_store_plaintext(settings):
    dek = new_dek()
    conn = connect(settings)
    created = create_entry(conn, dek, title="Flood", doc=DOC)
    fetched = get_entry(conn, dek, created["id"])
    assert fetched["title"] == "Flood"
    assert plain_text(fetched["doc"]) == "The river was high."

    update_entry(conn, dek, created["id"], title="Flood notes", doc=DOC)
    rows = list_entries(conn, dek, query="river")
    assert [row["title"] for row in rows] == ["Flood notes"]
    assert "river" in rows[0]["snippet"].lower()
    assert list_entries(conn, dek, query="mountain") == []

    raw = settings.db_path.read_bytes()
    assert b"Flood notes" not in raw
    assert b"river was high" not in raw

    delete_entry(conn, created["id"])
    assert list_entries(conn, dek) == []


def test_empty_title_becomes_untitled(settings):
    conn = connect(settings)
    created = create_entry(
        conn,
        new_dek(),
        title="   ",
        doc={"type": "doc", "content": []},
    )
    assert created["title"] == "Untitled"
