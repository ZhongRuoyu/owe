# Copyright (c) 2024 - 2026 Ruoyu Zhong
# SPDX-License-Identifier: MIT

import contextlib
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def database_path() -> Iterator[Path]:
  """Return a repo-local SQLite database path and clean it after the test."""
  repo_root = Path(__file__).resolve().parent.parent
  test_artifacts_dir = repo_root / ".test-artifacts"
  test_dir = test_artifacts_dir / uuid4().hex
  test_dir.mkdir(parents=True)
  try:
    yield test_dir / "owe.db"
  finally:
    shutil.rmtree(test_dir, ignore_errors=True)
    with contextlib.suppress(OSError):
      test_artifacts_dir.rmdir()
