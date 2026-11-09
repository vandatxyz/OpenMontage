"""thread_key rotates after 2 consecutive failures."""

from lib.film_factory import muse_thread as mt


def setup_function():
    mt._fail_counts.clear()
    mt._active.clear()


def test_rotate_after_two_fails():
    key = "series-demo"
    k1, rot1 = mt.note_failure(key)
    assert rot1 is False
    assert k1 == key
    k2, rot2 = mt.note_failure(k1)
    assert rot2 is True
    assert k2 != key
    assert k2.startswith("series-demo__t")


def test_success_resets_counter():
    key = "series-ok"
    mt.note_failure(key)
    mt.note_success(key)
    k, rot = mt.note_failure(key)
    assert rot is False
    assert k == key


def test_resolve_honors_active_rotation():
    base = "series-r"
    _, _ = mt.note_failure(base)
    new_key, rotated = mt.note_failure(base)
    assert rotated
    assert mt.resolve_thread(base) == new_key
