"""Offline integrity checks for the M4 destructive-reset export pair."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent.parent / "scripts" / filename
    )
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


exporter = _module("export_core_data", "export-core-data.py")
restorer = _module("restore_core_data", "restore-core-data.py")


def test_export_rejects_s3_key_that_escapes_the_export_directory(tmp_path):
    with pytest.raises(ValueError, match="Unsafe S3 key"):
        exporter._safe_destination(tmp_path, "../outside")


def test_restore_refuses_a_tampered_export_before_aws_writes(tmp_path):
    data = tmp_path / "dynamodb" / "old-table.jsonl"
    data.parent.mkdir()
    data.write_text('{"esp_id":{"S":"ESP-101"}}\n', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "format": "oilfield-esp-core-export-v1",
                "objects": [],
                "tables": [{"name": "old-table", "path": "dynamodb/old-table.jsonl", "sha256": "wrong"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Checksum mismatch"):
        restorer._load_verified(tmp_path)
