import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.paths import new_run_dir, latest_run, run_artifact


def test_new_run_dir_created_under_runs(tmp_path):
    run = new_run_dir(str(tmp_path))
    assert run.parent == (tmp_path / "runs").resolve()
    assert run.exists() and run.is_dir()

def test_latest_run_returns_most_recent(tmp_path):
    first = new_run_dir(str(tmp_path))
    # minute-granularity stamp: force a distinct name by renaming the first
    first = first.rename(first.parent / (first.name + "_a"))
    second = new_run_dir(str(tmp_path))
    second = second.rename(second.parent / (second.name + "_b"))
    assert latest_run(str(tmp_path)).name.endswith("_b")

def test_latest_run_none_when_empty(tmp_path):
    assert latest_run(str(tmp_path)) is None

def test_run_artifact_path(tmp_path):
    run = new_run_dir(str(tmp_path))
    assert run_artifact(run, "research") == run / "research.json"
