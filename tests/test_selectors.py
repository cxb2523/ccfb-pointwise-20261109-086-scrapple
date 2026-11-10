"""
Selector contract tests.

css/xpath share one implementation base, so the common contract is
parameterized over both classes via the dynamic dispatch entry point.
Tabular extraction has its own file of assertions because the
missing-cell policy (pad with None, keep the row; empty cell stays '')
is a pinned design decision rather than common behavior.
"""

import pytest

from conftest import (BASE_URL, CSS_LINK_SELECTOR, CSS_TITLE_SELECTOR,
                      XPATH_LINK_SELECTOR, XPATH_TITLE_SELECTOR)
from scrapple.selectors.css import CssSelector
from scrapple.selectors.xpath import XpathSelector
from scrapple.utils.dynamicdispatch import (get_command_class,
                                            get_selector_class)


SELECTOR_CASES = [
    ('css', CssSelector, CSS_LINK_SELECTOR, CSS_TITLE_SELECTOR),
    ('xpath', XpathSelector, XPATH_LINK_SELECTOR, XPATH_TITLE_SELECTOR),
]


@pytest.mark.parametrize('name,cls,link_sel,title_sel', SELECTOR_CASES)
def test_dynamic_dispatch_returns_selector_class(name, cls, link_sel, title_sel):
    assert get_selector_class(name) is cls
    assert get_selector_class(name.upper()) is cls


def test_dynamic_dispatch_rejects_unknown_selector():
    with pytest.raises(KeyError):
        get_selector_class('regex')


def test_command_dispatch_unchanged():
    from scrapple.commands import run as run_module
    assert get_command_class('run') is run_module.RunCommand


@pytest.mark.parametrize('cls,link_sel,title_sel',
                         [(c[1], c[2], c[3]) for c in SELECTOR_CASES])
class TestCommonSelectorContract:
    def test_extract_text(self, fake_transport, cls, link_sel, title_sel):
        page = cls(BASE_URL + 'index.html')
        assert page.extract_content(
            selector=title_sel, attr='text', connector=''
        ) == 'Index'

    def test_extract_url_pseudo_selector(self, fake_transport, cls,
                                         link_sel, title_sel):
        page = cls(BASE_URL + 'index.html')
        assert page.extract_content(selector='url', attr='') == \
            BASE_URL + 'index.html'

    def test_extract_href_is_absolutized(self, fake_transport, cls,
                                         link_sel, title_sel):
        page = cls(BASE_URL + 'index.html')
        href = page.extract_content(selector=link_sel, attr='href')
        assert href == BASE_URL + 'page_a.html'

    def test_missing_selector_returns_default(self, fake_transport, cls,
                                              link_sel, title_sel):
        page = cls(BASE_URL + 'index.html')
        content = page.extract_content(
            selector=self._absent_selector(cls), attr='text',
            default='<missing>'
        )
        assert content == '<missing>'

    def test_extract_links_bfs_order_and_type(self, fake_transport, cls,
                                              link_sel, title_sel):
        page = cls(BASE_URL + 'index.html')
        links = list(page.extract_links(selector=link_sel))
        assert [link.url for link in links] == [
            BASE_URL + 'page_a.html', BASE_URL + 'page_b.html'
        ]
        assert all(isinstance(link, cls) for link in links)

    @staticmethod
    def _absent_selector(cls):
        return 'nav .does-not-exist' if cls is CssSelector \
            else '//nav[@class="does-not-exist"]'


# ---------------------------------------------------------------------------
# Tabular extraction: pinned missing-cell policy
# ---------------------------------------------------------------------------

NESTED_TABLE_ROWS = {
    # direct child <td>s of each data row in the nested-table fixture;
    # the child combinators are essential for CSS so the inner table's
    # own rows do not match
    CssSelector: [
        '#nested-table > tr:nth-child(2) > td',
        '#nested-table > tr:nth-child(3) > td',
    ],
    XpathSelector: [
        "//table[@id='nested-table']/tr[2]/td",
        "//table[@id='nested-table']/tr[3]/td",
    ],
}
NESTED_TABLE_HEADER = {
    CssSelector: '#nested-table > tr:first-child > th',
    XpathSelector: "//table[@id='nested-table']/tr[1]/th",
}
COLUMN_SELECTORS = {
    CssSelector: ['ul.city-col li', 'ul.pop-col li'],
    XpathSelector: [
        "//ul[@class='city-col']/li",
        "//ul[@class='pop-col']/li",
    ],
}


@pytest.mark.parametrize('cls', [CssSelector, XpathSelector])
class TestTabularContract:
    def test_header_selector_and_nested_cell_text(
            self, fake_transport, cls):
        page = cls(BASE_URL + 'level2_1.html')
        headers, rows = page.extract_tabular(
            header=NESTED_TABLE_HEADER[cls],
            table_type='rows',
            selector=NESTED_TABLE_ROWS[cls][0],
            attr='text',
            connector='|',
        )
        # Header selector works on both dispatch paths.
        assert headers == ['name', 'score', 'note']
        row = rows[0]
        # Nested table: itertext walks into the inner table's cells.
        assert 'alice' in row['name'] and 'bob' in row['name']
        assert row['score'] == '10'

    def test_missing_cell_pads_none_but_keeps_row(
            self, fake_transport, cls):
        """
        Pinned policy: 3 headers, only 2 cells -> the row is emitted and
        the trailing field is None, rather than the whole row being
        dropped.
        """
        page = cls(BASE_URL + 'level2_1.html')
        _, rows = page.extract_tabular(
            header=['name', 'score', 'note'],
            table_type='rows',
            selector=NESTED_TABLE_ROWS[cls][0],
            attr='text',
            connector='|',
        )
        assert len(rows) == 1
        assert set(rows[0].keys()) == {'name', 'score', 'note'}
        assert rows[0]['note'] is None

    def test_empty_cell_is_empty_string_not_none(
            self, fake_transport, cls):
        """An existing empty <td></td> yields '', distinct from a missing cell."""
        page = cls(BASE_URL + 'level2_1.html')
        _, rows = page.extract_tabular(
            header=['name', 'score', 'note'],
            table_type='rows',
            selector=NESTED_TABLE_ROWS[cls][1],
            attr='text',
            connector='',
        )
        assert rows[0]['name'] == 'carol'
        assert rows[0]['score'] == '8'
        assert rows[0]['note'] == ''
        assert rows[0]['note'] is not None

    def test_columns_short_column_pads_none(self, fake_transport, cls):
        """
        Pinned policy for column tables: rows follow the longest column;
        a short column contributes None instead of truncating output.
        """
        page = cls(BASE_URL + 'level2_2.html')
        _, rows = page.extract_tabular(
            header=['city', 'pop'],
            table_type='columns',
            selector=COLUMN_SELECTORS[cls],
            attr='text',
            connector='',
        )
        assert rows == [
            {'city': 'paris', 'pop': '2'},
            {'city': 'london', 'pop': '9'},
            {'city': 'tokyo', 'pop': None},
        ]

    def test_invalid_table_type_raises(self, fake_transport, cls):
        page = cls(BASE_URL + 'level2_1.html')
        with pytest.raises(Exception):
            page.extract_tabular(
                header=['a'], table_type='diagonal', selector='whatever'
            )
