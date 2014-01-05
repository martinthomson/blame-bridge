#!/usr/bin/env python

import argparse
import subprocess
import tempfile

from sys import stdout, stderr, argv
from collections import deque

from diffu import parseDiff, writeMergedChunks
from blame import blameCursor, defaultBlame, mergeBlames, augmentBlame

output = argv[1]

parser = argparse.ArgumentParser(description='Reformat code, maintain blame.')
parser.add_argument('file', action='append')
parser.add_argument('--verbose', '-v', action='count')
args = parser.parse_args()

def ignoreWhitespace(str):
    return ''.join(str.split())

def commonPart(a, b):
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))

def walkLines(originalLines, changedLines):
    owalk = enumerate(map(ignoreWhitespace, originalLines)).__iter__()
    original = owalk.next()
    originalIdx = 0
    changedIdx = 0
    busted = False
    for changed in map(ignoreWhitespace, changedLines):
        if busted:
            yield ([], False)
            continue

        contributingLines = []
        changedIdx = 0

        common = commonPart(original[1][originalIdx:], changed)

        try:
            while common == len(original[1]) - originalIdx:
                contributingLines.append(original[0])
                original = owalk.next()
                originalIdx = 0
                changedIdx += common
                common = commonPart(original[1], changed[changedIdx:])
        except StopIteration as e:
            common = 0

        if common > 0:
            if common < len(changed) - changedIdx:
                # if we haven't consumed a whole line, then the formatter changed
                # something other than whitespace, without more sophisticated
                # searching, this line is a no go, report zero contributors
                # and give up on matching future lines
                contributingLines = []
                busted = True
            else:
                contributingLines.append(original[0])
        originalIdx += common

        # return the set of contributing lines
        # ...and whether this uses to the end of those lines
        # (which will determine if the patch can be safely split)
        yield (contributingLines, originalIdx == 0)

def findBlame(blames, line):
    """Assuming the blames are sorted, as they are, find the one that owns the given line"""
    for blame in blames:
        if (line < blame.end):
            return blame
    raise RuntimeError('out of range, missing blame!')

def allIn(items, completeSet):
    return reduce(lambda x, i: x and i in completeSet, items)

def attemptToSplitDiffChunkByBlame(chunk, allBlames):
    contiguous = 0
    savedBlames = set()
    lastContributionComplete = False
    lastContributionEnd = 0

    originalTaken = 0
    for (contributors, complete) in walkLines(chunk.original.lines, chunk.changed.lines):

        if len(contributors) > 0:
            absoluteContributors = map(lambda i: chunk.original.start + i - originalTaken, contributors)
            lineBlames = set(map(lambda line: findBlame(allBlames, line), absoluteContributors))
            lastContributionEnd = max(contributors)
        else:
            lineBlames = set(allBlames)

        if lastContributionComplete and not lineBlames.issubset(savedBlames):
            toTakeFromOriginal = lastContributionEnd - originalTaken
            originalTaken += toTakeFromOriginal
            yield (chunk.take(toTakeFromOriginal, contiguous), mergeBlames(savedBlames))
            contiguous = 0
            savedBlames.clear()
        savedBlames = savedBlames.union(lineBlames)
        lastContributionComplete = complete
        contiguous += 1
    yield (chunk, mergeBlames(savedBlames))

def processChunks(diffOutput, filename):
    blames = blameCursor(filename)
    for chunk in parseDiff(diffOutput):
        if chunk.original.count() > 0:
            chunkBlames = deque(blames.getRange(chunk.original.start, chunk.original.end))
            if len(chunkBlames) == 1:
                yield (chunk, chunkBlames.popleft())
            else:
                # Now things get tricky
                for piece in attemptToSplitDiffChunkByBlame(chunk, chunkBlames):
                    yield piece
        else:
            yield (chunk, defaultBlame)

def collectChunks(blameId, all):
    """Looks through the list of chunks for ones that match the blameId
    it saves those."""
    chunks = []
    i = 0
    while i < len(all):
        chunk, blame = all[i]
        if blame.id == blameId:
            del all[i]
            chunk.resetChangedLineStart()
            for c in chunks:
                chunk.bumpChangedLineStart(c)

            chunks.append(chunk)

            # apply fixup to all remaining chunks
            for other, oblame in all[:i]:
                other.update(chunk)
        else:
            for c in chunks:
                all[i][0].update(c)
            i += 1
    if args.verbose > 0:
        print('Chunks: %d' % len(chunks))
    return chunks


def fixLineNumbers(chunks):
    for i, c in enumerate(chunks):
        c.resetChangedLineStart()
        for later in chunks[i+1:]:
            later.bumpChangedLineStart(c)


def printChunks(chunks, patchFile):
    saved = deque()

    def printSaved():
        writeMergedChunks(saved, patchFile)
        saved.clear()

    for c in chunks:
        if len(saved) > 0 and not saved[-1].contextOverlap(c) > 0:
            printSaved()
        saved.append(c)
    printSaved()


def producePatches(blameGenerator, filename):
    fullname = subprocess.check_output(['git', 'ls-files', '--full-name', filename])[:-1]
    counter = 0
    chunkCount = 0
    all = list(blameGenerator)
    while len(all) > 0:
        blame = all[0][1]

        counter += 1
        patchname = '%s.blame-bridge%3.3d' % (filename, counter)
        with open(patchname, 'w') as patchFile:
            patchFile.write(augmentBlame(blame).header())
            if args.verbose > 0:
                print('--- %s' % patchname)
                if args.verbose > 1:
                    print(blame.header())
            patchFile.write('--- a/%s\n' % fullname)
            patchFile.write('+++ b/%s\n' % fullname)

            chunks = collectChunks(blame.id, all)
            chunkCount += len(chunks)

            fixLineNumbers(chunks)

            printChunks(chunks, patchFile)
    print('# %s: %d patches over %d chunks created\n' % (filename, counter, chunkCount))


for file in args.file:
    try:
        beautify = subprocess.Popen(['js-beautify', '-s', '2', file],
                                    stdout=subprocess.PIPE, stderr=stderr)
        diff = subprocess.Popen(['diff', '-u', '-d', file, '-'],
                                stdin=beautify.stdout, stdout=subprocess.PIPE)
        producePatches(processChunks(diff.stdout, file), file)
    except OSError as e:
        stderr.write('error formatting: %s' % e)
        exit(1)
