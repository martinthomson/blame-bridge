#!/usr/bin/env python

import argparse
import subprocess
import tempfile

from sys import stderr, stdout

import bridge

parser = argparse.ArgumentParser(description='Reformat code, maintain blame.')
parser.add_argument('file', action='append')
parser.add_argument('--verbose', '-v', action='count')
args = parser.parse_args()

bridge.verbose = args.verbose

for file in args.file:
    try:
        beautify = subprocess.Popen(['js-beautify', '-s', '2', file],
                                    stdout=subprocess.PIPE, stderr=stderr)
        diff = subprocess.Popen(['diff', '-u', '-d', file, '-'],
                                stdin=beautify.stdout, stdout=subprocess.PIPE)
        bridge.producePatches(diff.stdout, file)
    except OSError as e:
        stderr.write('error formatting: %s' % e)
        exit(1)
