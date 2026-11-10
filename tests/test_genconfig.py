import json

from docopt import docopt

from scrapple import cmd
from scrapple.commands import genconfig

doc = cmd.__doc__


def test_if_genconfig_instance_created():
    args = docopt(doc, "genconfig trial1 http://www.google.com")
    gc = genconfig.GenconfigCommand(args)
    assert isinstance(gc, genconfig.GenconfigCommand)


def test_if_template_filled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = docopt(doc, "genconfig trial1 http://www.google.com -s css")
    gc = genconfig.GenconfigCommand(args)
    gc.execute_command()
    with open(tmp_path / 'trial1.json', 'r') as f:
        config = json.load(f)
    assert config["project_name"] == "trial1"
    assert config["selector_type"] == "css"
    assert config['scraping']['url'] == "http://www.google.com"


def test_crawler_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = docopt(doc, "genconfig trial1 http://www.google.com -t crawler")
    gc = genconfig.GenconfigCommand(args)
    gc.execute_command()
    with open(tmp_path / 'trial1.json', 'r') as f:
        config = json.load(f)
    nextx = [
        {
            "follow_link": "",
            "scraping": {
                "data": [{"field": "", "selector": "", "attr": "", "default": "", "connector": ""}],
                "table": [
                    {
                        "table_type": "",
                        "header": "",
                        "prefix": "",
                        "suffix": "",
                        "selector": "",
                        "attr": "",
                        "default": "",
                        "connector": ""
                    }
                ]
            }
        }
    ]
    assert config['scraping']['next'] == nextx
