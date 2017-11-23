#!/usr/bin/python
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import contextlib
import json
import logging
import os
import string
import subprocess
import threading
import time
import uuid

import fasteners

LOGGER = logging.getLogger()

# make code as python 3 compatible as possible

DEFAULT_DATA = os.path.join(os.environ['HOME'], '.config', 'shfrp')


PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
PARSER.add_argument('--data-dir', '-d', help='Directory to store spreadsheet data in ', default=DEFAULT_DATA)
parsers = PARSER.add_subparsers(dest='command')
run_parser = parsers.add_parser('run', help='Run this shell command whenever something changes. Use {name} for the value of name.')
run_parser.add_argument('expr', type=str, action='append')
set_parser = parsers.add_parser('set', help='Set a variables value')
set_parser.add_argument('key', type=str)
set_parser.add_argument('value', type=str)


bus_parser = parsers.add_parser('bus', help='Listen to messages on the event bus')


def referenced_names(format_string):
    for _, name, _, _ in string.Formatter().parse(format_string):
        if name is not None:
            yield name

class StupidPubSub(object):
    # https://unix.stackexchange.com/questions/406378/command-line-pub-sub-without-a-server/406424?noredirect=1#comment727192_406424
    "A terrible way of doing pubsub without a server"
    class Publisher(object):
        def __init__(self, event_file):
            self._event_file = event_file
            self._stream = None

        def start(self):
            if self._stream is not None:
                raise ValueError(self._stream)

            LOGGER.debug('Pushing to file: %r', self._event_file)

            self._stream = open(self._event_file, 'a')


        def push(self, message):
            self._stream.write(json.dumps(message) + '\n')
            self._stream.flush()

    class _Client(object):
        def __init__(self, event_file):
            self._event_file = event_file
            self._proc = None

        def start(self):
            if self._proc is not None:
                raise ValueError(self._proc)

            command = ["tail",  "-f", self._event_file, '-n', '0']
            LOGGER.debug('Running %r', command)
            self._proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE
            )

        def get_messages(self):
            while True:
                line = self._proc.stdout.readline()
                if line == '':
                    break
                else:
                    message = json.loads(line)
                    LOGGER.debug('Got message %r', message)
                    yield message

        def stop(self):
            LOGGER.debug('Killing event bus proc')
            if self._proc:
                self._proc.kill()
        

    @classmethod
    @contextlib.contextmanager
    def with_client(cls, event_file):
        client = cls._Client(event_file)
        client.start()
        try:
            yield client
        finally:
            client.stop()


class EventBus(object):
    def __init__(self, client):
        self._client = client


    def wait_for_changes(self, variables):
        variables = set(variables)
        for message in self._client.get_messages():

            if message['type'] == 'parameter_update' and set(message['changed']) & set(variables):
                return
        else:
            raise ConnectionLost()

class ConnectionLost(Exception):
    pass
    

class State(object):
    def __init__(self, data_dir):
        self._data_dir = data_dir

    @contextlib.contextmanager
    def with_data(self):
        with with_json_data(os.path.join(self._data_dir, 'data.json')) as data:
            yield data
    
    def get_values(self, keys):
        with self.with_data() as data:
            try:
                return {k: data[k] for k in keys}
            except KeyError as k:
                key, = k.args
                raise ShfrpNoValue(key)

    def set(self, pairs):
        with self.with_data() as data:
            data.update(**pairs)


class ShfrpNoValue(Exception):
    "No value for a parameter"
    def __init__(self, key):
        self.key = key

    def __str__(self):
        return 'No parameter {!r}'.format(self.key)
    

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()


DATA_LOCK = threading.Lock()
@contextlib.contextmanager
def with_json_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            data = read_json(data_file)
            yield data

            output = json.dumps(data)
            with open(data_file, 'w') as stream:
                stream.write(output)

def show_info(message):
    # Show human readable information
    print(message)

def ensure_file(filename):
    directory = os.path.dirname(filename)
    if not os.path.isdir(directory):
    	os.mkdir(directory)

    if not os.path.exists(filename):
        with open(filename, 'w'):
            pass

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    LOGGER.debug('Started')

    event_file = os.path.join(args.data_dir, 'events')

    ensure_file(event_file)
    
    state = State(args.data_dir)

    if args.command == 'bus':
        with StupidPubSub.with_client(event_file) as client:
            event_bus = EventBus(client)
            for message in client.get_messages():
                print(json.dumps(message))

    if args.command == 'run':
        with StupidPubSub.with_client(event_file) as client:
            event_bus = EventBus(client)
            expr = ' '.join(args.expr)
            needed_args = list(referenced_names(expr))
            while True:
                try:
                    values = state.get_values(needed_args)
                except ShfrpNoValue as e:
                    show_info('Could not find parameter {} in {}'.format(e.key, expr))
                else:
                    subprocess.call(expr.format(**values), shell=True, executable='/bin/bash')

                LOGGER.debug('Waiting for changes...')
                event_bus.wait_for_changes(needed_args)
    elif args.command == 'set':
        changes = dict([(args.key, args.value)])
        state.set(changes)
        pub = StupidPubSub.Publisher(event_file)
        pub.start()
        pub.push(Messages.update(changes))
    else:
        raise ValueError(args.command)

class Messages(object):
    @staticmethod
    def update(changes):
        return dict(
            type='parameter_update', changes=changes,
            ident=str(uuid.uuid4()),
            timestamp=time.time())
