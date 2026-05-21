from obsidian_couch_sync.livesync import build_livesync_docs, normalize_vault_path


def test_normalize_vault_path():
    assert normalize_vault_path("/A/B.md") == "A/B.md"
    assert normalize_vault_path("A\\B.md") == "A/B.md"


def test_build_docs():
    docs = build_livesync_docs("Folder/Note.md", "# Hello\n", chunk_size=4)
    assert docs[0]["_id"] == "Folder/Note.md"
    assert docs[0]["children"]
    assert docs[1]["_id"].startswith("h:+")
    assert docs[1]["type"] == "leaf"
