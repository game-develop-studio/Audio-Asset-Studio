"""캐시 테스트."""
from pathlib import Path
from shared.cache import AssetCache, hash_params


def test_hash_params_deterministic():
    p = {"a": 1, "b": "hello"}
    assert hash_params(p) == hash_params(p)


def test_hash_params_order_independent():
    assert hash_params({"a": 1, "b": 2}) == hash_params({"b": 2, "a": 1})


def test_cache_put_restore(tmp_path):
    cache = AssetCache(tmp_path / "cache")
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    f = files_dir / "test.wav"
    f.write_bytes(b"fake audio")

    cache.put("key1", [f])
    assert cache.has("key1")

    dest = tmp_path / "restored"
    restored = cache.restore("key1", dest)
    assert restored is not None
    assert len(restored) == 1
    assert restored[0].read_bytes() == b"fake audio"


def test_cache_miss(tmp_path):
    cache = AssetCache(tmp_path / "cache")
    assert not cache.has("nonexistent")
    assert cache.restore("nonexistent", tmp_path / "dest") is None
