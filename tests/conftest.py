# Shared test setup.

import pytest


# Momus keeps a usage ledger in the user's state folder. Tests must never
# write there, so every test gets a state folder of its own.
@pytest.fixture(autouse=True)
def state_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("state")
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home / "momus"
