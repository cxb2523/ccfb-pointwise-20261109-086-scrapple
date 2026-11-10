"""
scrapple.utils.dynamicdispatch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Functions related to dynamic dispatch of objects
"""

def get_command_class(command):
    """
    Called from runCLI() to select the command class for the selected command.

    :param command: The command to be implemented
    :return: The command class corresponding to the selected command
    """
    from scrapple.commands import genconfig, generate, run, web
    commandMapping = {
    	'genconfig': genconfig,
    	'generate': generate,
    	'run': run,
    	'web': web
    }
    cmdClass = getattr(commandMapping.get(command), command.title() + 'Command')
    return cmdClass


def get_selector_class(selector_type):
    """
    Select the selector implementation for ``selector_type`` ("css" or
    "xpath"). Centralising the dispatch here lets the css/xpath pair be
    exercised against the same contract in the test suite.

    :param selector_type: ``"css"`` or ``"xpath"`` (case insensitive)
    :return: The corresponding selector class
    """
    from scrapple.selectors.css import CssSelector
    from scrapple.selectors.xpath import XpathSelector
    selectorMapping = {
        'css': CssSelector,
        'xpath': XpathSelector,
    }
    return selectorMapping[selector_type.lower()]
