"""
scrapple.utils.crawler
~~~~~~~~~~~~~~~~~~~~~~

BFS crawl engine used by the ``run`` command.

The crawl is a breadth-first traversal of the link graph described by the
``next`` sections of the configuration. BFS (rather than the old recursive
depth-first ``traverse_next``) makes the depth limit testable: with
``levels = N`` every fetched page is at depth 0..N and no request is ever
issued for depth N+1.

The BFS frontier lives in the durable
:class:`~scrapple.utils.checkpoint.RunCheckpoint`, not in process memory:
each page commit atomically (1) marks the URL seen, (2) appends its
records and (3) advances the frontier. A killed process therefore resumes
with the exact queue it held at the last commit.
"""


def extract_rows(page, node, base_record, verbosity=0):
    """
    Extract the result rows produced by one page config node.

    :param page: a selector object for the fetched page
    :param node: the ``scraping`` config node describing this page
    :param base_record: fields inherited from the parent page
    :return: ``(tabular_headers, rows)``
    """
    result = dict(base_record)
    for attribute in node.get('data', []):
        if attribute.get('field', '') != '':
            result[attribute['field']] = page.extract_content(**attribute)
    if not node.get('table'):
        return [], [result]
    headers = []
    rows = []
    for table in node['table']:
        if table.get('selector', '').strip() == '':
            continue
        table_kwargs = dict(table)
        table_kwargs.update({'result': result, 'verbosity': verbosity})
        table_headers, result_list = page.extract_tabular(**table_kwargs)
        headers.extend(table_headers)
        rows.extend(result_list)
    return headers, rows


def resolve_node(root_node, node_path):
    """
    Walk ``root_node`` following the ``next`` branch indices in
    ``node_path`` to reach the scraping config node for a frontier entry.
    """
    node = root_node
    for branch_index in node_path:
        node = node['next'][branch_index]['scraping']
    return node


def bfs_crawl(selector_class, root_url, scraping_cfg, levels, checkpoint,
              verbosity=0):
    """
    Crawl the link graph in breadth-first order.

    :param selector_class: ``CssSelector``/``XpathSelector`` class
    :param root_url: entry URL (depth 0)
    :param scraping_cfg: the root ``scraping`` config node
    :param levels: maximum follow depth; depth 0 is the entry page, so
                   ``levels = 2`` fetches depths 0, 1, 2 only
    :param checkpoint: durable :class:`RunCheckpoint` holding the frontier
    :return: the same checkpoint, updated in place
    """
    while checkpoint.queue:
        entry = checkpoint.pop_frontier()
        url = entry['url']
        depth = entry['depth']
        base_record = entry['base']
        node_path = entry['node_path']
        if url in checkpoint.seen_urls or depth > levels:
            continue

        node = resolve_node(scraping_cfg, node_path)
        page = selector_class(url)
        headers, rows = extract_rows(page, node, base_record, verbosity)

        children = []
        if depth < levels:
            child_record = rows[0] if rows else base_record
            for branch_index, nextx in enumerate(node.get('next') or []):
                child_node_path = node_path + [branch_index]
                for next_url in page.extract_link_urls(
                        selector=nextx['follow_link']):
                    children.append(
                        (next_url, depth + 1, child_record, child_node_path)
                    )

        # One atomic transaction: seen mark + records + frontier advance.
        checkpoint.commit_page(
            url, rows,
            [(u, d, b, p) for (u, d, b, p) in children],
            tabular_headers=headers,
        )

    return checkpoint
