import sys
from contextlib import contextmanager

from docopt import docopt
import pytest

from scrapple import cmd
from scrapple.commands import generate

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


def test_if_generate_instance_created():
    args = docopt(doc, "generate project1 test_project")
    gc = generate.GenerateCommand(args)
    assert isinstance(gc, generate.GenerateCommand)


def test_xpath_scraper_generate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # project1.json lives alongside the tests; copy the bits the command reads
    import json
    from pathlib import Path
    src = Path(__file__).parent / 'project1.json'
    (tmp_path / 'project1.json').write_text(src.read_text(encoding='utf-8'),
                                            encoding='utf-8')
    args = docopt(doc, "generate project1 project1")
    gc = generate.GenerateCommand(args)
    gc.execute_command()
    program = (tmp_path / 'project1.py').read_text(encoding='utf-8')
    assert "from scrapple.selectors.xpath import XpathSelector" in program
    assert 'page0 = XpathSelector("https://trakt.tv/shows/mr-robot")' in program


def test_css_scraper_generate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import json
    from pathlib import Path
    src = Path(__file__).parent / 'project2.json'
    (tmp_path / 'project2.json').write_text(src.read_text(encoding='utf-8'),
                                            encoding='utf-8')
    args = docopt(doc, "generate project2 project2")
    gc = generate.GenerateCommand(args)
    gc.execute_command()
    program = (tmp_path / 'project2.py').read_text(encoding='utf-8')
    assert "from scrapple.selectors.css import CssSelector" in program
    assert 'page0 = CssSelector("https://www.basketball-reference.com/teams/")' in program


def test_nonexistent_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = docopt(doc, "generate project_unknown project2")
    gc = generate.GenerateCommand(args)
    with output() as out:
        gc.execute_command()
    alert = out.getvalue().strip()
    expected_alert = "project_unknown.json does not exist. Use ``scrapple genconfig``."
    assert expected_alert in alert
