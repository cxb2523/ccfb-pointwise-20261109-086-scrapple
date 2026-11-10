"""
Regression tests for the mid-run crash incident.

Scenario: the process dies after the 3rd fetched page. On resume the
output must contain every page exactly once (no duplicates, no gaps), and
the depth limit must be enforced on BFS boundaries -- depth-3 pages are
never even requested when levels=2.
"""

import json

import pytest
import requests

from conftest import (EXPECTED_BFS_LEVELS_2, EXPECTED_BFS_LEVELS_3,
                      EXPECTED_LEVEL3, build_crawl_config, run_args)
from scrapple.commands.run import RunCommand
from scrapple.utils.checkpoint import RunCheckpoint


def _start_run(transport_factory, write_project, selector_type, levels,
               fail_after=None):
    config = build_crawl_config(selector_type, levels)
    write_project(config)
    transport = transport_factory(fail_after=fail_after)
    rc = RunCommand(run_args())
    return rc, transport


def _fetched_paths(transports):
    paths = []
    for transport in transports:
        paths.extend(transport.paths)
    return paths


def _load_result(tmp_path):
    with open(tmp_path / 'result.json', encoding='utf-8') as f:
        return json.load(f)


def test_resume_after_crash_is_exact_no_duplicates_no_gaps(
        tmp_path, transport_factory, write_project):
    # First attempt: the "process is killed" on the 4th request.
    rc, first_transport = _start_run(
        transport_factory, write_project, 'xpath', levels=2, fail_after=3
    )
    with pytest.raises(Exception):
        rc.execute_command()

    # The first three BFS pages were committed before the crash; no final
    # output file exists yet, but the durable checkpoint does.
    assert not (tmp_path / 'result.json').exists()
    checkpoint_path = tmp_path / 'result.checkpoint.json'
    assert checkpoint_path.exists()
    checkpoint = RunCheckpoint.load_or_create(str(checkpoint_path), 'crawlproj')
    assert len(checkpoint.seen_urls) == 3
    assert len(checkpoint.data) == 3
    # Three pages durably committed; the fourth GET is the one that died.
    assert first_transport.paths == EXPECTED_BFS_LEVELS_2[:3]
    assert first_transport.attempted_paths == EXPECTED_BFS_LEVELS_2[:4]

    # Resume with a healthy transport: seen pages are not re-fetched.
    second_transport = transport_factory(fail_after=None)
    RunCommand(run_args()).execute_command()

    all_paths = _fetched_paths(transport_factory.all)

    # Not one page twice, not one page missing -- across both processes.
    assert len(all_paths) == len(set(all_paths))
    assert sorted(all_paths) == sorted(EXPECTED_BFS_LEVELS_2)

    result = _load_result(tmp_path)
    assert len(result['data']) == len(EXPECTED_BFS_LEVELS_2)

    # Full-record uniqueness (the checkpoint's record-key dedup) and the
    # page each record belongs to -- the highest-numbered urlN field is
    # the page's own URL; lower-numbered ones are inherited ancestors.
    record_keys = [json.dumps(row, sort_keys=True) for row in result['data']]
    assert len(record_keys) == len(set(record_keys))
    page_urls = []
    for row in result['data']:
        own_field = max(
            (name for name in row if name.startswith('url')),
            key=lambda name: int(name[3:]),
        )
        page_urls.append(row[own_field].rsplit('/', 1)[-1])
    assert sorted(page_urls) == sorted(EXPECTED_BFS_LEVELS_2)

    # Checkpoint is retired only after the output is durably written.
    assert not checkpoint_path.exists()
    assert second_transport.paths == EXPECTED_BFS_LEVELS_2[3:]


def test_repeated_resume_attempts_stay_deduped(
        tmp_path, transport_factory, write_project):
    # Two consecutive crashes, then a clean run: every crash boundary must
    # remain a valid transaction boundary. Crash points are chosen so no
    # partial run ever finishes (otherwise its checkpoint is retired and
    # the next run is a fresh full crawl).
    rc, _ = _start_run(
        transport_factory, write_project, 'css', levels=2, fail_after=2
    )
    with pytest.raises(Exception):
        rc.execute_command()

    rc2 = RunCommand(run_args())
    transport_factory(fail_after=3)
    with pytest.raises(Exception):
        rc2.execute_command()

    transport_factory(fail_after=None)
    RunCommand(run_args()).execute_command()

    successful = []
    for transport in transport_factory.all:
        successful.extend(transport.paths)
    # 2 + 3 + 1 pages across three processes, each page fetched exactly once.
    assert len(successful) == len(EXPECTED_BFS_LEVELS_2)
    assert len(successful) == len(set(successful))
    assert sorted(successful) == sorted(EXPECTED_BFS_LEVELS_2)
    assert len(_load_result(tmp_path)['data']) == len(EXPECTED_BFS_LEVELS_2)


def test_completed_rerun_rewrites_identical_output(
        tmp_path, fake_transport, write_project):
    write_project(build_crawl_config('xpath', levels=2))
    RunCommand(run_args()).execute_command()
    first = _load_result(tmp_path)

    # No checkpoint remains, so this is a full re-crawl: still exact.
    RunCommand(run_args()).execute_command()
    second = _load_result(tmp_path)
    assert first == second
    assert len(second['data']) == len(EXPECTED_BFS_LEVELS_2)


def test_depth_limit_cuts_at_level_2_in_bfs_order(
        tmp_path, fake_transport, write_project):
    write_project(build_crawl_config('css', levels=2))
    RunCommand(run_args()).execute_command()

    # Exact BFS order, not just the same set: the termination condition is
    # only meaningful if the frontier is served breadth-first.
    assert fake_transport.paths == EXPECTED_BFS_LEVELS_2
    for level3_page in EXPECTED_LEVEL3:
        assert level3_page not in fake_transport.paths
    assert len(_load_result(tmp_path)['data']) == len(EXPECTED_BFS_LEVELS_2)


def test_depth_3_does_reach_level_3(tmp_path, fake_transport, write_project):
    # Control test: level-3 pages exist and are reachable when the limit is
    # raised, proving the levels=2 cutoff comes from the depth guard.
    write_project(build_crawl_config('xpath', levels=3))
    RunCommand(run_args()).execute_command()

    assert fake_transport.paths == EXPECTED_BFS_LEVELS_3
    for level3_page in EXPECTED_LEVEL3:
        assert level3_page in fake_transport.paths


def test_checkpoint_commit_is_idempotent(tmp_path):
    path = str(tmp_path / 'cp.json')
    cp = RunCheckpoint.load_or_create(
        path, 'p', root_url='http://crawl.test/root'
    )
    entry = cp.pop_frontier()
    assert entry['url'] == 'http://crawl.test/root'
    cp.commit_page(
        'http://crawl.test/root', [{'k': 'v'}],
        children=[('http://crawl.test/a', 1, {}, [0])],
    )
    # Re-committing the same URL adds nothing.
    assert cp.commit_page('http://crawl.test/root', [{'k': 'v'}], []) == 0
    assert len(cp.data) == 1
    assert cp.seen_urls == {'http://crawl.test/root'}

    # Frontier survived the commit and round-trips through the file.
    reloaded = RunCheckpoint.load_or_create(path, 'p')
    assert reloaded.seen_urls == {'http://crawl.test/root'}
    assert reloaded.data == [{'k': 'v'}]
    assert [e['url'] for e in reloaded.queue] == [
        'http://crawl.test/a'
    ]
    assert reloaded.queue[0]['node_path'] == [0]
    assert not (tmp_path / 'cp.json.tmp').exists()


def test_real_network_is_blocked():
    # The pytest-socket backstop: without the fake transport, a request
    # cannot leave the process.
    with pytest.raises(RuntimeError):
        requests.get('http://example.com/')


def test_csv_output_writes_one_row_per_page(
        tmp_path, fake_transport, write_project):
    write_project(build_crawl_config('css', levels=2))
    RunCommand(run_args(output_type='csv')).execute_command()

    import csv
    with open(tmp_path / 'result.csv', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(EXPECTED_BFS_LEVELS_2)
    # One header per configured field, no checkpoint file left behind.
    assert set(rows[0].keys()) == {
        'title0', 'url0', 'title1', 'url1', 'title2', 'url2'
    }
    assert not (tmp_path / 'result.checkpoint.json').exists()
