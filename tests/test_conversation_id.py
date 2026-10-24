from __future__ import annotations

import uuid

from main import _load_or_create_conversation_id


def test_conversation_id_is_persisted_as_a_uuid_with_real_newline(tmp_path):
    path = tmp_path / "data" / "conversation_id.txt"

    first = _load_or_create_conversation_id(path)

    assert str(uuid.UUID(first)) == first
    assert path.read_text(encoding="utf-8") == first + "\n"
    assert not path.read_text(encoding="utf-8").endswith("\\n")

    second = _load_or_create_conversation_id(path)
    assert second == first
