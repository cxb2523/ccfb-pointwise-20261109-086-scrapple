import sys
from contextlib import contextmanager

from docopt import docopt
import pytest

from scrapple import cmd
from scrapple.commands import run

doc = cmd.__doc__


try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


@contextmanager
def output():
    new_out = StringIO()
    old_out = sys.stdout
    try:
        sys.stdout = new_out
        yield sys.stdout
    finally:
        sys.stdout = old_out


def test_if_run_instance_created():
    args = docopt(doc, "run project1 test_project")
    rc = run.RunCommand(args)
    assert isinstance(rc, run.RunCommand)


def test_nonexistent_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = docopt(doc, "run project_unknown project2")
    rc = run.RunCommand(args)
    with output() as out:
        rc.execute_command()
    alert = out.getvalue().strip()
    expected_alert = "project_unknown.json does not exist. Use ``scrapple genconfig``."
    assert expected_alert in alert


# The original end-to-end cases hit live third-party sites and compare
# against golden files captured in 2018. They cannot run under the
# no-socket policy; their coverage is replaced by the fixture-backed
# regression suite in test_recovery.py / test_selectors.py.
@pytest.mark.skip(reason="requires live network; see test_recovery.py")
@pytest.mark.parametrize('project,result,expected', [
    ('project1', 'result1', 'expected_result1.json'),
    ('project2', 'result2', 'expected_result2_20180428.json'),
    ('project3', 'result3', 'expected_result3.json'),
    ('project4', 'result4', 'expected_result4.json'),
])
def test_run_against_live_site(project, result, expected):
    args = docopt(doc, "run %s %s" % (project, result))
    rc = run.RunCommand(args)
    rc.execute_command()
