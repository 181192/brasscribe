import json

from brasscribe_engine import build_info


def test_the_workspace_stamp_names_the_build(tmp_path):
    (tmp_path / build_info.STAMP_FILE).write_text(json.dumps({"stamp": "ab" * 32, "commit": "c3dc2ad", "version": "1.0"}))
    assert build_info.build.__wrapped__(tmp_path) == "c3dc2ad " + "ab" * 6


def test_a_stamp_without_a_commit_still_names_the_build(tmp_path):
    (tmp_path / build_info.STAMP_FILE).write_text(json.dumps({"stamp": "0123456789abcdef"}))
    assert build_info.from_stamp(tmp_path) == "0123456789ab"


def test_no_stamp_and_no_checkout_is_unknown(tmp_path):
    assert build_info.build.__wrapped__(tmp_path) is None
    (tmp_path / build_info.STAMP_FILE).write_text("not json")
    assert build_info.from_stamp(tmp_path) is None
