import os
import tempfile
from pathlib import Path


TEST_STATE_DIRECTORY = Path(tempfile.mkdtemp(prefix="bancue-tests-"))
os.environ["BANCUE_STATE_DB"] = str(TEST_STATE_DIRECTORY / "test-bancue.db")
