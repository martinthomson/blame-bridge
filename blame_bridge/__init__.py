#!/usr/bin/env python

import argparse
import subprocess
import tempfile
import os

from sys import stderr, stdout, stdin

import bridge

def main(argv):
    parser = argparse.ArgumentParser(description='Reformat code, maintain blame.',
                                     usage='%(prog)s [options] files [...] -f formatter [formatter options]')
    h = 'files to reformat'
    parser.add_argument('files', nargs='+', help=h)
    h = 'formatter command line parameters; '
    h += 'use {input} to represent input file name, {output} to represent output file name'
    parser.add_argument('--formatter', '-f', nargs=argparse.REMAINDER, help=h)
    h = 'characters to ignore when comparing lines; '
    h += 'include those characters that the formatter might change [default: " \\t\\r\\n"]'
    parser.add_argument('--ignore', '-i', default=' \t\r\n', help=h)
    parser.add_argument('--verbose', '-v', action='count')
    args = parser.parse_args(argv)

    bridge.verbose = args.verbose
    bridge.ignoreCharacters = args.ignore

    inputIdx = None
    outputIdx = None
    for i, c in enumerate(args.formatter):
        if c == '{input}':
            if inputIdx is None:
                inputIdx = i
            else:
                stderr.write('can only specify {input} once')
                exit(2)
        if c == '{output}':
            if outputIdx is None:
                outputIdx = i
            else:
                stderr.write('can only specify {output} once')
                exit(2)

    if inputIdx is None:
        if len(args.files) > 1:
            stderr.write('error: must specify {} in formatter command for multiple files\n')
            exit(2)
        if args.verbose > -1:
            stderr.write('warning: reading from stdin instead of %s\n' % args.files[0])

    for file in args.files:
        try:
            tmp = None
            command = args.formatter[:]
            if inputIdx is None:
                input = open(file, 'r')
            else:
                input = stdin
                command[inputIdx] = file
            h, tmp = tempfile.mkstemp(prefix=file[file.rfind('/') + 1:])
            if outputIdx is None:
                output = open(tmp, 'w')
            else:
                command[outputIdx] = tmp
                output = stdout
            if args.verbose > 0:
                print('running formatter: [%s]' % ', '.join(command))
            beautify = subprocess.Popen(command, stdin=input, stdout=output)
            code = beautify.wait()
            if code != 0:
                stderr.write('Error running formatter: %d' % code)
            diff = subprocess.Popen(['diff', '-u', '-d', file, tmp], stdout=subprocess.PIPE)
            bridge.producePatches(diff.stdout, file)
        except OSError as e:
            stderr.write('error formatting: %s' % e)
            exit(1)
        finally:
            if tmp is not None:
                os.remove(tmp)
