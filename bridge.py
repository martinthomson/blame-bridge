import subprocess

from sys import stdout, stderr, argv
from collections import deque

from diffu import parseDiff, writeMergedChunks
from blame import blameCursor, defaultBlame, mergeBlames, augmentBlame, pickNewest

verbose = 0

def ignoreWhitespace(str):
    return ''.join(str.split())

def commonPart(a, b):
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))

def findContributors(originalLines, changedLines):
    """Finds the lines from originalLines that contribute to changedLines."""
    owalk = enumerate(map(ignoreWhitespace, originalLines)).__iter__()
    original = owalk.next()
    originalIdx = 0
    changedIdx = 0
    lastCompleteContributor = -1
    for changed in map(ignoreWhitespace, changedLines):
        if lastCompleteContributor is None:
            yield (None, False)
            continue

        changedIdx = 0

        common = commonPart(original[1][originalIdx:], changed)

        try:
            while common == len(original[1]) - originalIdx:
                lastCompleteContributor += 1
                originalIdx = 0
                original = owalk.next()
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
                lastCompleteContributor = None
        originalIdx += common

        # return the last contributing line index
        # ...and whether the next line is partially consumed
        # (which will determine if the patch can be safely split)
        yield (lastCompleteContributor, originalIdx != 0)

def findBlame(blames, line):
    """Assuming the blames are sorted, as they are, find the one that owns the given line"""
    for blame in blames:
        if (line < blame.end):
            return blame
    raise RuntimeError('out of range, missing blame!')

def attemptToSplitDiffChunkByBlame(chunk, allBlames):
    previousBlame = None
    previousContributionEnd = -1

    # the number of lines we've looked at and are accumulating into a single chunk
    pending = 0
    # the number of lines we've already taken from the chunk
    originalTaken = 0
    for (lastCompleteContributor, partial) in findContributors(chunk.original.lines, chunk.changed.lines):

        if lastCompleteContributor is not None:
            contributors = range(originalTaken, lastCompleteContributor + 1)
            if partial:
                contributors.append(lastCompleteContributor + 1)
            absoluteContributors = map(lambda i: chunk.original.start + i - originalTaken, contributors)
            lineBlames = map(lambda line: findBlame(allBlames, line), absoluteContributors)
        else:
            # bad, blame the latest person to commit
            lineBlames = allBlames
            if verbose > 0:
                print('Warning: the following chunk cannot be attributed:')
                writeMergedChunks([chunk], stdout)
        lineBlame = pickNewest(lineBlames)

        if previousContributionEnd >= 0 and lineBlame.id != previousBlame.id:
            toTakeFromOriginal = previousContributionEnd - originalTaken
            originalTaken += toTakeFromOriginal
            yield (chunk.take(toTakeFromOriginal, pending), previousBlame)
            pending = 0
            savedBlames.clear()
        previousBlame = lineBlame
        previousContributionEnd = lastCompleteContributor
        pending += 1
    yield (chunk, previousBlame)

def processDiff(diffOutput, filename):
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
    if verbose > 0:
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


def writePatches(blameGenerator, filename):
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
            if verbose > 0:
                print('--- %s' % patchname)
                if verbose > 1:
                    print(blame.header())
            patchFile.write('--- a/%s\n' % fullname)
            patchFile.write('+++ b/%s\n' % fullname)

            chunks = collectChunks(blame.id, all)
            chunkCount += len(chunks)

            fixLineNumbers(chunks)

            printChunks(chunks, patchFile)
    print('# %s: %d patches over %d chunks created\n' % (filename, counter, chunkCount))

def producePatches(reformatted, filename):
    writePatches(processDiff(reformatted, filename), filename)
