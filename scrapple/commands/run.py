"""
scrapple.commands.run
~~~~~~~~~~~~~~~~~~~~~

"""

from __future__ import print_function

import csv
import json
import os

from colorama import Back, Fore, init

from scrapple.commands import command
from scrapple.utils.checkpoint import RunCheckpoint
from scrapple.utils.config import (InvalidConfigException, extract_fieldnames,
                                   validate_config)
from scrapple.utils.crawler import bfs_crawl
from scrapple.utils.dynamicdispatch import get_selector_class


def _atomic_write(path, write_payload):
    """Write via a temp file then os.replace so the output is never torn."""
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8', newline='') as f:
        write_payload(f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


class RunCommand(command.Command):
    """
    Defines the execution of :ref:`run <command-run>`
    """

    def __init__(self, args):
        super(RunCommand, self).__init__(args)
        init()

    def execute_command(self):
        """
        The run command implements the web content extractor corresponding to the given \
        configuration file.

        The execute_command() validates the input project name and opens the JSON \
        configuration file. The run() method handles the execution of the extractor run.

        The extractor implementation follows these primary steps :

        1. Selects the appropriate :ref:`selector class <implementation-selectors>` through \
        a dynamic dispatch, with the selector_type argument from the configuration file.

        #. Crawls the link graph described by the ``next`` sections in breadth-first \
        order. The ``levels`` key in the configuration (default 1) is the maximum follow \
        depth, where the entry page is depth 0.

        #. Each fetched page is committed to a durable checkpoint -- the visited-URL set \
        and its result records share one atomic commit -- so an interrupted run can be \
        resumed without duplicate records.

        #. According to the --output_type argument, the result data is saved in a JSON \
        document or a CSV document.
        """
        try:
            self.args['--verbosity'] = int(self.args['--verbosity'])
            if self.args['--verbosity'] not in [0, 1, 2]:
                raise ValueError
            if self.args['--verbosity'] > 0:
                print(Back.GREEN + Fore.BLACK + "Scrapple Run")
                print(Back.RESET + Fore.RESET)
            with open(self.args['<projectname>'] + '.json', 'r') as f:
                self.config = json.load(f)
            validate_config(self.config)
            self.run()
        except ValueError:
            print(Back.WHITE + Fore.RED + "Use 0, 1 or 2 for verbosity." \
                + Back.RESET + Fore.RESET, sep="")
        except IOError:
            print(Back.WHITE + Fore.RED + self.args['<projectname>'], ".json does not ", \
                  "exist. Use ``scrapple genconfig``." + Back.RESET + Fore.RESET, sep="")
        except InvalidConfigException as e:
            print(Back.WHITE + Fore.RED + e + Back.RESET + Fore.RESET, sep="")

    def run(self):
        selector_class = get_selector_class(self.config['selector_type'])
        project = self.args['<projectname>']
        output_filename = self.args['<output_filename>']
        output_type = self.args['--output_type']
        verbosity = self.args['--verbosity']
        scraping = self.config['scraping']
        levels = int(self.config.get('levels', 1))

        checkpoint_path = os.path.join(
            os.getcwd(), output_filename + '.checkpoint.json'
        )
        checkpoint = RunCheckpoint.load_or_create(
            checkpoint_path, project, root_url=scraping['url']
        )
        if verbosity > 0 and checkpoint.resumed:
            print(Back.YELLOW + Fore.BLUE + "Resuming run, "
                  + str(len(checkpoint.seen_urls)) + " page(s) already done"
                  + Back.RESET + Fore.RESET)

        # Exceptions propagate: the checkpoint on disk is the resume point.
        bfs_crawl(
            selector_class,
            scraping['url'],
            scraping,
            levels,
            checkpoint,
            verbosity=verbosity,
        )

        results = {'project': project, 'data': checkpoint.data}
        output_path = os.path.join(os.getcwd(), output_filename + '.' + output_type)
        if output_type == 'json':
            _atomic_write(
                output_path,
                lambda f: json.dump(results, f, indent=4, ensure_ascii=False)
            )
        else:
            fields = extract_fieldnames(self.config)
            fields.extend(checkpoint.ordered_headers())

            def write_csv(f):
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(results['data'])

            _atomic_write(output_path, write_csv)

        # The output now durably contains everything the checkpoint knew,
        # so the resume point can be dropped. If the process dies right
        # before this line, a re-run simply rewrites an identical output.
        checkpoint.discard()
        if verbosity > 0:
            print()
            print(Back.WHITE + Fore.RED + output_filename,
                  ".", output_type, " has been created"
                  + Back.RESET + Fore.RESET, sep="")
