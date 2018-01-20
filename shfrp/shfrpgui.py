# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import json
import logging
import subprocess
import xerox
import screeninfo

LOGGER = logging.getLogger()


shfrp = None # Talk to shfrp via ipc - I want to keep gui tools out of shfrp

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
parsers = PARSER.add_subparsers(dest='command')
edit_parser = parsers.add_parser('edit', help='Edit a value')
edit_parser.add_argument('param', type=str, nargs='?')

subparser = parsers.add_parser('clip-push', help='Push something from the clipboard into a value')
subparser = parsers.add_parser('reset', help='Push something from the clipboard into a value')

def rofi_prompt(prompt, choices):
    p = subprocess.Popen(
        ['rofi', '-width', '100%', '-dmenu', '-p', prompt],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    choice_string = '\n'.join(choices)
    reply, _ = p.communicate(choice_string)
    return reply.strip()


def get_params():
    return json.loads(subprocess.check_output(['shfrp', 'params', '--json']))

def zenity_read(prompt, value):
    monitor = screeninfo.get_monitors()[0]
    # yad seems to deal with --width better than zenity
    return subprocess.check_output(['yad', '--entry', '--width', str(monitor.width).encode('utf8'), '--text', prompt, '--entry-text', value]).strip('\n')

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.command == 'edit':
        params = get_params()
        if args.param is None:
            parameter = rofi_prompt('Which value to edit', [d['name'] for d in params])
        else:
            parameter = args.param

        for param_data in params:
            if param_data['name'] == parameter:
                break
        else:
            param_data = None

        if param_data:
            value = param_data['value']
        else:
            value = ''
        history = param_data.get('history', []) or []
        old_value = rofi_prompt('select value to edit:', [''] + list(remove_dups(history))).strip('\n')
        new_value = zenity_read('Edit value', old_value)
        subprocess.check_call(['shfrp', 'set', parameter, new_value])
    elif args.command == 'clip-push':
        params = get_params()
        parameter = rofi_prompt('Which value to edit', [d['name'] for d in params])
        subprocess.check_call(['shfrp', 'set', parameter, xerox.paste(xsel=True)])
    elif args.command == 'reset':
        params = get_params()
        parameter = rofi_prompt('Which value to edit', [d['name'] for d in params])
        subprocess.check_call(['shfrp', 'reset', parameter])
    else:
    	raise ValueError(args.command)

def remove_dups(lst):
    result = []
    found = set()
    for x in reversed(lst):
        if x not in found:
            found.add(x)
            result.append(x)
    return reversed(result)

