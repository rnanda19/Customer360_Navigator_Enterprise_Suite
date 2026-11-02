"""
tests/mlops/test_tracking.py — Customer360 Navigator

Real pytest coverage for src/mlops/tracking.py. No mocking of hashlib/subprocess - these tests
write real temp files and read back real sha256/size, and call the real `git` binary against
this actual checkout.
"""

from __future__ import annotations

from mlops import tracking


def test_compute_file_sha256_matches_hashlib_directly(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello world")
    import hashlib

    expected = hashlib.sha256(b"hello world").hexdigest()
    result = tracking.compute_file_sha256(p)
    assert result["sha256"] == expected
    assert result["size_bytes"] == 11


def test_dataset_fingerprint_is_order_independent(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"alpha")
    b.write_bytes(b"beta")
    fp1 = tracking.compute_dataset_fingerprint([a, b])
    fp2 = tracking.compute_dataset_fingerprint([b, a])
    assert fp1["combined_sha256"] == fp2["combined_sha256"]
    assert len(fp1["files"]) == 2


def test_dataset_fingerprint_changes_if_file_content_changes(tmp_path):
    a = tmp_path / "a.txt"
    a.write_bytes(b"version1")
    fp1 = tracking.compute_dataset_fingerprint([a])
    a.write_bytes(b"version2")
    fp2 = tracking.compute_dataset_fingerprint([a])
    assert fp1["combined_sha256"] != fp2["combined_sha256"]


def test_compute_dataset_fingerprint_raises_on_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.txt"
    import pytest

    with pytest.raises(FileNotFoundError):
        tracking.compute_dataset_fingerprint([missing])


def test_get_git_sha_returns_a_real_40_char_hex_sha_for_this_repo():
    sha = tracking.get_git_sha()
    assert sha is not None
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_get_git_sha_returns_none_for_a_non_git_directory(tmp_path):
    assert tracking.get_git_sha(repo_root=tmp_path) is None


def test_capture_software_versions_reports_installed_packages_with_real_versions():
    versions = tracking.capture_software_versions(("numpy", "pandas"))
    assert "python" in versions
    assert versions["numpy"] != "not_installed"
    assert versions["pandas"] != "not_installed"


def test_capture_software_versions_reports_not_installed_for_a_fake_package():
    versions = tracking.capture_software_versions(("this_package_does_not_exist_xyz",))
    assert versions["this_package_does_not_exist_xyz"] == "not_installed"


def test_get_tracking_uri_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://example.invalid:5000")
    assert tracking.get_tracking_uri(tmp_path) == "http://example.invalid:5000"


def test_get_tracking_uri_defaults_to_local_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    uri = tracking.get_tracking_uri(tmp_path)
    assert uri == f"sqlite:///{tmp_path / 'mlflow.db'}"


def test_capture_run_provenance_includes_dataset_fingerprint_when_paths_given(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    provenance = tracking.capture_run_provenance(dataset_paths=[f])
    assert "dataset_fingerprint" in provenance
    assert "git_sha" in provenance
    assert "software_versions" in provenance


def test_capture_run_provenance_omits_dataset_fingerprint_when_no_paths_given():
    provenance = tracking.capture_run_provenance(dataset_paths=None)
    assert "dataset_fingerprint" not in provenance
