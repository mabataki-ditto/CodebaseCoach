import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="function")
def temp_dir():
    """函数级别的临时目录，每个测试独立。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)