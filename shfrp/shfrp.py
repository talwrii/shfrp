#!/usr/bin/python -u
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import contextlib
import json
import logging
import os
import string
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import fasteners
import psutil
import termcolor

import termios

LOGGER = logging.getLogger()
FILE_LOGGER = logging.getLogger('filewatch')

DEFAULT_DATA = os.path.join(os.environ['HOME'], '.config', 'shfrp')

def json_option(parser):
    parser.add_argument('--json', action='store_true', help='Output in machine readable json')

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
PARSER.add_argument('--data-dir', '-d', help='Directory to store spreadsheet data in ', default=DEFAULT_DATA)
parsers = PARSER.add_subparsers(dest='command')
run_parser = parsers.add_parser('run', help='Run this shell command whenever something changes. Use {name} for the value of name.')
run_parser.add_argument('--echo', action='store_true', default=False, help='Echo command rather than run')
run_parser.add_argument('--kill', action='store_true', default=False, help='Kill a command if an update is triggered')
run_parser.add_argument(
    '--listen', '-l', type=str, action='append',
    help='Fire if the value of this parameter changed')
run_parser.add_argument(
    '--listen-file', '-f', type=str, action='append',
    help='Fire if this changes')

run_parser.add_argument('--output', '-o', type=str, help='Write output to this file (overwrite on change)')
run_parser.add_argument('expr', type=str, action='append')
set_parser = parsers.add_parser('set', help='Set a variables value')
set_parser.add_argument('key', type=str)
set_parser.add_argument('value', type=str)
reset_parser = parsers.add_parser('reset', help='Cause variables that use this parameter to update')
reset_parser.add_argument('parameter', type=str)

stream_param = parsers.add_parser(
    'stream-param',
    help='Read lines from standard in and reset parameters in response')
stream_param.add_argument('param', type=str, help='name of variable we are streaming')

params_parser = parsers.add_parser('params', help='Print parameters')
params_parser.add_argument('--no-color', action='store_false', dest='color', default=True)
json_option(params_parser)

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

    def wait_for_changes(self, variables, files=None):
        FILE_LOGGER.debug('Waiting for changes to variables(%r) and files (%r)...', variables, files)

        non_abs_files = [f for f in files if not os.path.isabs(f)]
        if non_abs_files:
            raise ValueError(non_abs_files)

        variables = set(variables)
        for message in self._client.get_messages():
            if message['type'] == 'file_change':
                if message['file'] in files:
                    return
            elif message['type'] == 'parameter_update' and set(message['changed']) & set(variables):
                return
            else:
                FILE_LOGGER.debug('Ignoring message')
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
            data.setdefault('listened', dict())
            data.setdefault('paraeters', dict())
            data.setdefault('parameter.history', dict())
            yield data

    @contextlib.contextmanager
    def with_listen(self, listener, listened):
        with self.with_data() as data:
            for param in listened:
                data["listened"].setdefault(param, list())
                data["listened"][param].append(listener)
        try:
            yield
        finally:
            with self.with_data() as data:
                for param in listened:
                    data["listened"].setdefault(param, list())
                    data["listened"][param].remove(listener)

    def get_values(self, keys):
        LOGGER.debug('Get values %r', keys)
        with self.with_data() as data:
            try:
                return {k: data["parameters"][k] for k in keys}
            except KeyError as k:
                key, = k.args
                raise ShfrpNoValue(key)

    def set(self, pairs):
        with self.with_data() as data:
            data["parameters"].update(**pairs)
            for key, value in pairs.items():
                data["parameter.history"].setdefault(key, list())
                data["parameter.history"][key].append(value)


    @contextlib.contextmanager
    def with_listened(self):
        with self.with_data() as data:
            result = []
            for name, listeners in data['listened'].items():
                value = data['parameters'].get(name)
                history = data['parameter.history'].get(name)
                result.append([name, value, list(listeners), history])
            yield result




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


class HackFileWatcher(object):
    def __init__(self, publisher, files):
        self._publisher = publisher
        self._files = [os.path.abspath(filename) for filename in files]

        # I find pynotify fiddley to use, use a process instead

    def run(self):
        p = subprocess.Popen(['inotifywait', '-m'] + self._files, stdout=subprocess.PIPE)

        while True:
            line = p.stdout.readline()
            if line == b'':
                break
            line = line.rstrip('\n').rstrip(' ')
            filename, _rest = line.rsplit(b' ', 1)
            self._publisher.push(Messages.file_change(filename))


def run_loop(state, event_file, args):
    client_id = str(uuid.uuid4())

    if args.listen_file:
        pub = StupidPubSub.Publisher(event_file)
        pub.start()
        file_watcher = HackFileWatcher(pub, args.listen_file)
        spawn(file_watcher.run)

    with StupidPubSub.with_client(event_file) as client:
        event_bus = EventBus(client)
        expr = ' '.join(args.expr)
        needed_args = list(referenced_names(expr))

        def wait_for_changes():
            event_bus.wait_for_changes(needed_args + list(args.listen), files=args.listen_file or [])

        with state.with_listen(client_id, needed_args + list(args.listen)):
            while True:
                try:
                    values = state.get_values(needed_args)
                except ShfrpNoValue as e:
                    show_info('Could not find parameter {} in {}'.format(e.key, expr))
                    wait_for_changes()
                    continue
                else:
                    command = expr.format(**values)
                    if args.echo:
                        print(command)
                        wait_for_changes()
                        continue
                    else:
                        file_manager = open(args.output, 'w') if args.output is not None else identity_manager(sys.stdout)
                        LOGGER.debug('Writing to %r', file_manager)


                        waiter = ThreadWaiter()

                        # vim was breaking C-c when killed.
                        with with_restore_tty():
                            p = subprocess.Popen(
                                command, shell=True, executable='/bin/bash',
                                stdout=subprocess.PIPE if args.output is not None else sys.stdout)

                            if args.output is not None:
                                output, _ = p.communicate()

                                # minimise the time the file is invalid
                                with tempfile.NamedTemporaryFile(delete=False) as f:
                                    f.write(output)
                                    f.close()
                                    os.rename(f.name, args.output)

                            event_wait_thread, event_wait_event = waiter.spawn(
                                wait_for_changes)
                            if args.kill:
                                # IMPROVEMENT: perhaps the kill should go through
                                #    the event bus, this could would then become simpler
                                waiter.spawn(p.wait)
                                LOGGER.debug('Waiting for process or event')
                                waiter.wait()
                                try:
                                    LOGGER.debug('Killing process')
                                    kill_tree(p)
                                except psutil.NoSuchProcess:
                                    pass

                            LOGGER.debug('Waiting for process %r...', p.pid)
                            p.wait()
                            LOGGER.debug('%r exited', p.pid)

                # Use an event rather than thread.join
                # so that C-c works
                event_wait_event.wait()

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    LOGGER.debug('Started %d', os.getpid())

    event_file = os.path.join(args.data_dir, 'events')

    ensure_file(event_file)

    state = State(args.data_dir)

    if args.command == 'bus':
        with StupidPubSub.with_client(event_file) as client:
            event_bus = EventBus(client)
            for message in client.get_messages():
                print(json.dumps(message))

    if args.command == 'run':
        if args.listen is None:
            args.listen = []
        run_loop(state, event_file, args)

    elif args.command in ('set', 'reset'):
        if args.command == 'set':
            changes = dict([(args.key, args.value)])
            state.set(changes)
            message = Messages.update(changes)
        elif args.command == 'reset':
            message = Messages.update(None, changed=[args.parameter])
        else:
            raise ValueError(args.cmmand)

        pub = StupidPubSub.Publisher(event_file)
        pub.start()
        pub.push(message)
    elif args.command in 'stream-param':
        stream_param(state, event_file, args.param)
    elif args.command in 'params':
        json_result = []
        with state.with_listened() as listened:
            for param, value, _listeners, history in listened:
                if args.color:
                    flag = termcolor.colored('set', 'green') if value is not None else termcolor.colored('unset', 'red')
                else:
                    flag = 'set' if value is not None else 'unset'
                if not args.json:
                    print(param, flag, repr(value))
                else:
                    json_result.append(dict(name=param, value=value, history=history))

        if args.json:
            print(json.dumps(json_result))

    else:
        raise ValueError(args.command)

class Messages(object):
    @staticmethod
    def update(changes, changed=None):
        changed = set.union(set(changes) if changes else set() , set(changed) if changed else set())
        return dict(
            type='parameter_update', changes=changes,
            ident=str(uuid.uuid4()),
            changed=list(changed),
            timestamp=time.time())

    @staticmethod
    def file_change(file):
        return dict(
            type='file_change',
            file=file)


@contextlib.contextmanager
def identity_manager(x):
    yield x

def spawn(f, *args, **kwargs):
	thread = threading.Thread(target=f, args=args, kwargs=kwargs)
	thread.setDaemon(True)
	thread.start()
	return thread

class ThreadWaiter(object):
    def __init__(self):
        self._event = threading.Event()

    # waiter.spawn(func, *args, **kwargs)
    def spawn(self, func, *args, **kwargs):
        event = threading.Event()
        return spawn(self.wrap, event, func, *args, **kwargs), event

    def wrap(self, event, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            event.set()
            self._event.set()

    def wait(self):
        self._event.wait()


@contextlib.contextmanager
def with_restore_tty():
    out_settings = termios.tcgetattr(sys.stdout)
    in_settings = termios.tcgetattr(sys.stdin)
    try:
        yield
    finally:
        termios.tcsetattr(sys.stdout, termios.TCSANOW, out_settings)
        termios.tcsetattr(sys.stdout, termios.TCSANOW, in_settings)

def stream_param(state, event_file, param):
    pub = StupidPubSub.Publisher(event_file)
    pub.start()
    while True:
        line = sys.stdin.readline()
        if line == '':
            break
        changes = dict([(param, line)])
        state.set(changes)
        message = Messages.update(changes)
        pub.push(message)

def kill_tree(p):
    parent = psutil.Process(p.pid)
    for child in parent.children(recursive=True):  # or parent.children() for recursive=False
        child.kill()
    parent.kill()
