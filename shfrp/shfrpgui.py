# make code as python 3 compatible as possible
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import json
import logging
import subprocess
import xerox

LOGGER = logging.getLogger()


shfrp = None # Talk to shfrp via ipc - I want to keep gui tools out of shfrp

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
parsers = PARSER.add_subparsers(dest='command')
edit_parser = parsers.add_parser('edit', help='Edit a value')
edit_parser.add_argument('param', type=str, nargs='?')

subparser = parsers.add_parser('clip-push', help='Push something from the clipboard into a value')

def rofi_prompt(prompt, choices):
    p = subprocess.Popen(
        ['rofi', '-dmenu', '-p', prompt],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    choice_string = '\n'.join(choices)
    reply, _ = p.communicate(choice_string)
    return reply.strip()


def get_params():
    return json.loads(subprocess.check_output(['shfrp', 'params', '--json']))

def zenity_read(prompt, value):
    print((prompt, value))
    return subprocess.check_output(['zenity', '--entry', '--text', prompt, '--entry-text', value])

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
        old_value = rofi_prompt('select value to edit:', [''] + (param_data.get('history', []) or [])).strip('\n')
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
