"""
Shared pytest fixtures.

Network policy: ``pytest.ini`` passes ``--disable-socket`` so any real
socket call fails the suite. The fake transport below is the only way
pages are fetched -- it serves the static HTML under tests/fixtures/site
and records every request in BFS arrival order.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

FIXTURES_DIR = Path(__file__).parent / 'fixtures'
SITE_DIR = FIXTURES_DIR / 'site'
BASE_URL = 'http://crawl.test/'

CSS_LINK_SELECTOR = 'nav a'
XPATH_LINK_SELECTOR = '//nav//a'
CSS_TITLE_SELECTOR = 'h1.title'
XPATH_TITLE_SELECTOR = '//h1[@class="title"]'


class FakeResponse(object):
    def __init__(self, content, url):
        self.content = content
        self.url = url
        self.status_code = 200


class FakeTransport(object):
    """
    Stand-in for ``requests``. Serves fixture HTML keyed by URL path and
    optionally fails after the first ``fail_after`` successful requests,
    simulating the process being killed mid-crawl.
    """

    def __init__(self, fail_after=None):
        self.order = []
        self.successful = []
        self.fail_after = fail_after

    def get(self, url, headers=None, **kwargs):
        self.order.append(url)
        if self.fail_after is not None and len(self.order) > self.fail_after:
            raise requests.exceptions.ConnectionError(
                'injected failure after %d requests' % self.fail_after
            )
        relative = urlparse(url).path.lstrip('/')
        fixture_path = SITE_DIR / relative
        if not fixture_path.is_file():
            raise requests.exceptions.ConnectionError(
                'no static fixture for %s' % url
            )
        self.successful.append(url)
        return FakeResponse(fixture_path.read_bytes(), url)

    @property
    def paths(self):
        """URLs actually fetched and parsed (failed attempts excluded)."""
        return [urlparse(u).path.lstrip('/') for u in self.successful]

    @property
    def attempted_paths(self):
        """Every request, including the one that simulated the crash."""
        return [urlparse(u).path.lstrip('/') for u in self.order]


@pytest.fixture
def fake_transport(monkeypatch):
    """Patch the request entry point used by the selector base class."""
    transport = FakeTransport()
    monkeypatch.setattr(
        'scrapple.selectors.selector.requests.get', transport.get
    )
    return transport


@pytest.fixture
def transport_factory(monkeypatch):
    """Factory so a resumed run can get a fresh transport instance."""
    transports = []

    def _factory(fail_after=None):
        transport = FakeTransport(fail_after=fail_after)
        monkeypatch.setattr(
            'scrapple.selectors.selector.requests.get', transport.get
        )
        transports.append(transport)
        return transport

    _factory.all = transports
    return _factory


def build_crawl_config(selector_type, levels):
    """
    Nested ``next`` config, one node per depth, with distinct field names
    per level (validate_config rejects duplicate field names).
    """
    if selector_type == 'css':
        link_selector, title_selector = CSS_LINK_SELECTOR, CSS_TITLE_SELECTOR
    else:
        link_selector, title_selector = XPATH_LINK_SELECTOR, XPATH_TITLE_SELECTOR

    def node(depth):
        current = {
            'data': [
                {
                    'field': 'title%d' % depth,
                    'selector': title_selector,
                    'attr': 'text',
                    'default': '',
                    'connector': '',
                },
                {
                    'field': 'url%d' % depth,
                    'selector': 'url',
                    'attr': '',
                    'default': '',
                    'connector': '',
                },
            ]
        }
        if depth < levels:
            current['next'] = [
                {
                    'follow_link': link_selector,
                    'scraping': node(depth + 1),
                }
            ]
        return current

    root = node(0)
    root['url'] = BASE_URL + 'index.html'
    return {
        'project_name': 'crawlproj',
        'selector_type': selector_type,
        'levels': levels,
        'scraping': root,
    }


@pytest.fixture
def write_project(tmp_path, monkeypatch):
    """Write a project config into tmp_path and run commands there."""
    monkeypatch.chdir(tmp_path)

    def _write(config, name='crawlproj'):
        config_path = tmp_path / (name + '.json')
        config_path.write_text(json.dumps(config), encoding='utf-8')
        return config_path

    return _write


def run_args(project='crawlproj', output='result', output_type='json'):
    return {
        '<projectname>': project,
        '<output_filename>': output,
        '--output_type': output_type,
        '--verbosity': '0',
    }


# BFS order of the fixture link graph
EXPECTED_BFS_LEVELS_2 = [
    'index.html',
    'page_a.html',
    'page_b.html',
    'level2_1.html',
    'level2_2.html',
    'level2_3.html',
]
EXPECTED_LEVEL3 = ['level3_x.html', 'level3_y.html', 'level3_z.html']
EXPECTED_BFS_LEVELS_3 = EXPECTED_BFS_LEVELS_2 + EXPECTED_LEVEL3
