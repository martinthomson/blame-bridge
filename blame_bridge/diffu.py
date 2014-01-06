from collections import deque
from sys import stdout
import re

contextLines = 3

class DiffLines:
    """A single span of lines from a chunk of diff, used to store either the original
       or the changed lines"""
    def __init__(self, start, lines):
        """Note: end is inclusive"""
        self.start = start
        # prepopulate end, which for empty line sets is one less than the start
        self.end = start + len(lines)
        self.lines = lines

    def take(self, n):
        if n > len(self.lines):
            raise ValueError('not enough lines remaining')
        piece = DiffLines(self.start, self.lines[:n])
        self.start += n
        self.lines = self.lines[n:]
        return piece

    def bump(self, n):
        self.start += n
        self.end += n

    def count(self):
        return self.end - self.start

    def write(self, output, prefix=''):
        for line in self.lines:
            output.write(prefix)
            output.write(line)

    def isEmpty(self):
        return self.count() == 0

    def setStart(self, start):
        # set end before count() is messed up
        self.end = start + self.count()
        self.start = start

class DiffChunk:
    """A single piece of diff, original and changed line spans both"""
    def __init__(self, original, changed, preContext=None, postContext=None):
        self.original = original
        self.changed = changed
        if preContext is None:
            self.preContext = []
        else:
            self.preContext = preContext[-contextLines:]
        if postContext is None:
            self.postContext = []
        else:
            self.postContext = postContext[:contextLines]

    def take(self, n, m=None):
        if m is None:
            m = n
        retOrig = self.original.take(n)
        retPost = self.original.lines + self.postContext
        retPost = retPost[:contextLines]
        ret = DiffChunk(retOrig, self.changed.take(m),
                         self.preContext, retPost)
        self.preContext += ret.original.lines
        self.preContext = self.preContext[-contextLines:]
        return ret

    def delta(self):
        """Determine how many lines this change adds"""
        return self.changed.count() - self.original.count()

    def update(self, other):
        """Takes the other patch chunk and assumes that it's been applied.
        Returns True if changes were made"""

        if other.original.start <= self.original.start:
            # overlap on the preContext part
            #self.original.bump(other.delta())

            overlap = other.original.end - (self.original.start - len(self.preContext))
            if overlap > 0:
                overlapstart = max(0, overlap - other.original.count())
                self.preContext[overlapstart:overlap] = other.changed.lines
                self.preContext = self.preContext[-contextLines:]
            return True

        if other.original.end >= self.original.end:
            # overlap on the postContext part
            overlap = self.original.end + len(self.postContext) - other.original.start
            if overlap > 0:
                oend = len(self.postContext) - overlap + other.original.count()
                self.postContext[-overlap:oend] = other.changed.lines
                self.postContext = self.postContext[:contextLines]
                return True
        return False

    def resetChangedLineStart(self):
        """When taken on its own, both the original and changed lines start
        at the same line number.  This makes it so."""
        self.changed.setStart(self.original.start)

    def bumpOriginal(self, other):
        if other.changed.start <= self.original.start:
            self.original.bump(other.delta())

    def bumpChanged(self, other):
        """Takes the other patch and assumes that it's in the same patch set.
        When patches are grouped together, the line counts on the changed end
        need to be incremented based on what has come before.
        """
        if other.original.end < self.original.start:
            self.changed.bump(other.delta())

    def contextOverlap(self, other):
        """If other follows this, return the amount of overlap in the context parts.
        If this is positive, the chunks will have to be merged for output.
        """
        endOfSelf = self.original.end + len(self.postContext)
        startOfOther = other.original.start - len(other.preContext)
        return endOfSelf - startOfOther

def saveContext(line, context, pendingChunks):
    """save a line of context.  sometimes this gives a pending chunk
    enough trailing context to be complete, so return true when that happens
    so that the chunk can be emitted"""
    if context is not None:
        context.append(line)
        context = context[-contextLines:]
    for chunk in pendingChunks:
        if len(chunk.postContext) < contextLines:
            chunk.postContext.append(line)

    # only the first chunk will be finished, return true iff it is
    return len(pendingChunks) > 0 and len(pendingChunks[0].postContext) >= contextLines

def parseDiff(input):
    line = input.readline()
    while line != '' and line[:3] != '---':
        line = input.readline()
    line = input.readline()
    if line[:3] == '+++':
        line = input.readline()

    headerRegex = re.compile(r'^@@ -(\d+),\d+ \+(\d+),\d+ @@')
    pendingChunks = deque()
    while line != '':
        operation, remainder = line[0], line[1:]
        if operation == '@':
            for chunk in pendingChunks:
                yield chunk
            pendingChunks.clear()

            context = []
            original = []
            changed = []

            m = headerRegex.match(line)
            if m is None:
                raise RuntimeError('can\'t parse @@ line')
            originalLine, changedLine = map(int, (m.group(1), m.group(2)))

        elif operation == '-':
            original.append(remainder)
            # don't add to context, so that we don't get original
            # lines mixed up in there, we'll need to add these lines back later
            # though in case there a multiple chunks in the one section
            if saveContext(remainder, None, pendingChunks):
                yield pendingChunks.popleft()

        elif operation == '+':
            changed.append(remainder)

        elif operation == ' ':
            if len(original) > 0 or len(changed) > 0:
                pendingChunks.append(
                    DiffChunk(DiffLines(originalLine, original),
                              DiffLines(changedLine, changed),
                              context))
                context += original
                originalLine += len(original)
                changedLine += len(changed)
                original = []
                changed = []

            originalLine += 1
            changedLine += 1
            if saveContext(remainder, context, pendingChunks):
                yield pendingChunks.popleft()
        else:
            raise RuntimeError('unknown diff character %s' % operation)

        line = input.readline()
    for chunk in pendingChunks:
        yield chunk

def writeMergedChunks(chunks, output):
    prev = None
    totalOriginal = 0
    totalChanged = 0
    for c in chunks:
        contextSize = len(c.preContext) + len(c.postContext)
        if prev is not None:
            contextSize -= prev.contextOverlap(c)
        totalOriginal += c.original.count() + contextSize
        totalChanged += c.changed.count() + contextSize
        prev = c
    output.write("@@ -%d,%d +%d,%d @@\n" % (chunks[0].original.start - len(chunks[0].preContext),
                                            totalOriginal,
                                            chunks[0].changed.start - len(chunks[0].preContext),
                                            totalChanged))
    prev = None
    for c in chunks:
        overlap = 0
        if prev is not None:
            overlap = prev.contextOverlap(c)
            removed = min(len(prev.postContext), overlap)
            overlap -= removed
            context = prev.postContext[:-removed]
        else:
            context = []
        context += c.preContext[overlap:]
        for cline in context:
            output.write(' ')
            output.write(cline)
        c.original.write(output, '-')
        c.changed.write(output, '+')
        prev = c
    for cline in prev.postContext:
        output.write(' ')
        output.write(cline)
