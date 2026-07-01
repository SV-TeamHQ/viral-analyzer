import sys, pathlib
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.apify_client import run_actor


def test_run_actor_returns_dataset_items():
    fake_run = MagicMock(default_dataset_id="ds1")
    fake_client = MagicMock()
    fake_client.actor.return_value.call.return_value = fake_run
    fake_client.dataset.return_value.iterate_items.return_value = iter([{"a": 1}, {"a": 2}])

    with patch("viral_core.apify_client.ApifyClient", return_value=fake_client) as AC:
        items = run_actor("tok", "the/actor", {"urls": ["x"]})

    AC.assert_called_once_with("tok")
    fake_client.actor.assert_called_with("the/actor")
    assert items == [{"a": 1}, {"a": 2}]

def test_run_actor_requires_token():
    try:
        run_actor("", "the/actor", {})
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "APIFY_TOKEN" in str(e)
