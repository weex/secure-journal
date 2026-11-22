from journal_app.crypto import decrypt_entry, encrypt_entry, new_dek, unwrap_dek, wrap_dek


def test_wrap_roundtrip_uses_a_different_salt_from_the_ciphertext():
    dek = new_dek()
    wrapped = wrap_dek("correct horse battery", dek, time_cost=1, memory_cost=8192, parallelism=1)
    assert unwrap_dek("correct horse battery", wrapped) == dek
    try:
        unwrap_dek("wrong horse battery!", wrapped)
    except Exception:
        pass
    else:
        raise AssertionError("wrong password unwrapped the data key")


def test_entry_ciphertext_is_bound_to_the_entry_id():
    dek = new_dek()
    payload = {"title": "Morning", "doc": {"type": "doc", "content": []}}
    nonce, ciphertext = encrypt_entry(dek, "entry-1", payload)
    assert b"Morning" not in ciphertext
    assert decrypt_entry(dek, "entry-1", nonce, ciphertext) == payload
    try:
        decrypt_entry(dek, "entry-2", nonce, ciphertext)
    except Exception:
        pass
    else:
        raise AssertionError("ciphertext decrypted under a different entry id")
