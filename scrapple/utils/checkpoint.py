"""
scrapple.utils.checkpoint
~~~~~~~~~~~~~~~~~~~~~~~~~

Durable checkpoint state for the run command.

A crawl marks pages as visited, appends their records and advances the
BFS frontier in *one* atomic commit per page. The state file therefore
always satisfies the invariant that every URL in ``seen_urls`` has every
one of its records in ``data``, and every not-yet-visited URL reachable
from a committed page is present in ``frontier``. If the process is
killed between two page commits, the interrupted page is simply re-fetched
on resume; it can never land in the output twice, and no reachable page
can be stranded by a lost in-memory queue.

The commit is a write-to-temp-then-``os.replace`` (atomic on both POSIX
and Windows), so a crash can leave at most the previous intact state file
or the new one -- never a torn JSON document.
"""

import json
import os
from collections import deque


def record_key(record):
    """Stable hashable identity for a result record."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


class RunCheckpoint(object):
    """
    Holds the durable crawl state:

    * ``seen_urls``    -- URLs already fetched (frontier dedup)
    * ``seen_records`` -- identity keys of records already emitted
                          (output-level dedup, belt and braces)
    * ``data``         -- the result records in crawl (BFS) order
    * ``headers``      -- tabular headers with their insertion order,
                          used to lay out CSV output
    * ``frontier``     -- BFS queue entries
                          ``{"url", "depth", "base", "node_path"}``
                          waiting to be fetched, persisted so a resume
                          rebuilds the exact queue the killed process held
    """

    def __init__(self, path, project, seen_urls=None, seen_records=None,
                 data=None, headers=None, frontier=None):
        self.path = path
        self.project = project
        self.seen_urls = set(seen_urls or [])
        self.seen_records = set(seen_records or [])
        self.data = list(data or [])
        self.headers = dict(headers or {})
        self.queue = deque(frontier or [])
        self.queued_urls = {entry['url'] for entry in self.queue}

    @classmethod
    def load_or_create(cls, path, project, root_url=None):
        """
        Load an existing checkpoint for a resumed run, or start a fresh
        one whose frontier contains only the entry URL.
        """
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            return cls(
                path,
                payload.get('project', project),
                seen_urls=payload.get('seen_urls', []),
                seen_records=payload.get('seen_records', []),
                data=payload.get('data', []),
                headers=payload.get('headers', {}),
                frontier=payload.get('frontier', []),
            )
        checkpoint = cls(path, project)
        if root_url is not None:
            checkpoint.enqueue(root_url, depth=0, base={}, node_path=[])
        return checkpoint

    @property
    def resumed(self):
        return bool(self.seen_urls)

    def enqueue(self, url, depth, base, node_path):
        """Add a URL to the persisted frontier unless already known."""
        if url in self.seen_urls or url in self.queued_urls:
            return False
        self.queue.append({
            'url': url, 'depth': depth, 'base': base,
            'node_path': node_path,
        })
        self.queued_urls.add(url)
        return True

    def pop_frontier(self):
        return self.queue.popleft()

    def commit_page(self, url, rows, children, tabular_headers=()):
        """
        Atomically mark ``url`` visited, append its records and replace
        the frontier with the remaining queue plus ``children``.

        ``children`` is an iterable of
        ``(url, depth, base, node_path)`` tuples.
        Returns the number of records actually appended. A URL that was
        already committed contributes nothing, so re-calling this after a
        crash-and-resume cannot create duplicates. The URL mark, the
        record appends and the frontier advance share a single commit --
        there is no window in which one is durable and the others are not.
        """
        if url in self.seen_urls:
            return 0
        added = 0
        for row in rows:
            key = record_key(row)
            if key in self.seen_records:
                continue
            self.seen_records.add(key)
            self.data.append(row)
            added += 1
        for header in tabular_headers:
            if header not in self.headers:
                self.headers[header] = len(self.headers)
        self.seen_urls.add(url)
        self.queued_urls.discard(url)
        for child_url, depth, base, node_path in children:
            self.enqueue(child_url, depth, base, node_path)
        self._commit()
        return added

    def ordered_headers(self):
        return sorted(self.headers, key=lambda h: self.headers[h])

    def discard(self):
        """Remove the state file once the final output has been written."""
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _commit(self):
        payload = {
            'project': self.project,
            'seen_urls': sorted(self.seen_urls),
            'seen_records': sorted(self.seen_records),
            'data': self.data,
            'headers': self.headers,
            'frontier': list(self.queue),
        }
        tmp_path = self.path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.path)
