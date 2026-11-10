from docopt import docopt

from scrapple import cmd

doc = cmd.__doc__


def test_version():
    args = docopt(doc, "--version")
    assert args['--version'] is True


def test_genconfig():
    args1 = docopt(doc, "genconfig project1 google.com")
    assert args1['<projectname>'] == 'project1'
    assert args1['<url>'] == 'google.com'
    assert args1['--type'] == 'scraper'
    assert args1['--selector'] == 'xpath'

    args2 = docopt(doc, "genconfig project1 google.com --type=crawler")
    assert args2['<projectname>'] == 'project1'
    assert args2['<url>'] == 'google.com'
    assert args2['--type'] == 'crawler'
    assert args2['--selector'] == 'xpath'

    args3 = docopt(doc, "genconfig project1 google.com -s css")
    assert args3['<projectname>'] == 'project1'
    assert args3['<url>'] == 'google.com'
    assert args3['--type'] == 'scraper'
    assert args3['--selector'] == 'css'

    args4 = docopt(doc, "genconfig project1 google.com -t crawler --selector=css")
    assert args4['<projectname>'] == 'project1'
    assert args4['<url>'] == 'google.com'
    assert args4['--type'] == 'crawler'
    assert args4['--selector'] == 'css'


def test_run():
    args1 = docopt(doc, "run project1 output1")
    assert args1['<projectname>'] == 'project1'
    assert args1['<output_filename>'] == 'output1'
    assert args1['--output_type'] == 'json'

    args2 = docopt(doc, "run project1 output1 -o csv")
    assert args2['<projectname>'] == 'project1'
    assert args2['<output_filename>'] == 'output1'
    assert args2['--output_type'] == 'csv'


def test_generate():
    args1 = docopt(doc, "generate project1 output1")
    assert args1['<projectname>'] == 'project1'
    assert args1['<output_filename>'] == 'output1'
    assert args1['--output_type'] == 'json'

    args2 = docopt(doc, "generate project1 output1 --output_type=csv")
    assert args2['<projectname>'] == 'project1'
    assert args2['<output_filename>'] == 'output1'
    assert args2['--output_type'] == 'csv'
