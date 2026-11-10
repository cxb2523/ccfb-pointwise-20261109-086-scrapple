"""
Tests for configuration helpers, including a regression for the
string-formatting precedence bug that made duplicate-field validation
crash with TypeError instead of raising InvalidConfigException.
"""

import pytest

from scrapple.utils.config import (InvalidConfigException,
                                   extract_fieldnames, validate_config)


def _config_with_fields(fields):
    return {
        'selector_type': 'xpath',
        'scraping': {
            'url': 'http://crawl.test/index.html',
            'data': [
                {'field': f, 'selector': '//h1', 'attr': 'text',
                 'default': '', 'connector': ''}
                for f in fields
            ],
        },
    }


def test_validate_config_accepts_unique_fields():
    assert validate_config(_config_with_fields(['a', 'b'])) is True


def test_validate_config_rejects_duplicate_fields():
    with pytest.raises(InvalidConfigException) as excinfo:
        validate_config(_config_with_fields(['a', 'b', 'a']))
    assert '1 duplicate field names' in str(excinfo.value)


def test_extract_fieldnames_disambiguates_repeats():
    # Repeated names across scraper levels are renamed deterministically.
    config = _config_with_fields(['a', 'a'])
    assert extract_fieldnames(config) == ['a', 'a_2']
