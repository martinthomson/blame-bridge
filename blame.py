import sys
import subprocess
import time
import calendar
from datetime import datetime

reformatTime = time.time();

class BlameData:
    def __init__(self, id, start, end, data):
        self.id = id
        self.start = start
        self.end = end
        self.data = data

    def header(self, sha=False):
        timestamp = time.asctime(time.gmtime(float(self.data['author-time'])))
        if sha and 'committer-time' in self.data:
            commitTimestamp = time.asctime(time.gmtime(float(self.data['committer-time'])))
            commitSha = 'From %s %s\n' % (self.id, commitTimestamp)
        else:
            commitSha = ''
        return "%sFrom: %s %s\nDate: %s Z\nSubject: %s\n\n" % (
            commitSha,
            self.data['author'], self.data['author-mail'],
            timestamp,
            self.data['summary'].replace('\n', '\n  '))

    def copy(self):
        return BlameData(self.id, self.start, self.end, self.data.copy())

    def __hash__(self):
        return hash(self.id)

    def __eq__(x, y):
        return x.id == y.id

    def augment(self):
        self.data['summary'] = '%s\nReformatted %s; original %s' % (self.data['summary'],
                                                                    time.asctime(time.gmtime(reformatTime)),
                                                                    self.id)

defaultBlame = BlameData('newline', 0, 0, {
    'author': 'blame-bridge',
    'author-mail': '<blame-bridge@example.com>',
    'author-time': reformatTime,
    'author-tz': 'Z',
    'summary': 'Whitespace added by reformatter'
})

def readCommitData(blameOutput, id):
    commitData = {}
    line = blameOutput.readline()
    while line != '' and line[0] != '\t':
        key, value = line.partition(' ')[::2]
        commitData[key] = value[:-1]
        line = blameOutput.readline()
    commitData['id'] = id
    return commitData

def parseBlame(blameOutput):
    allCommits = {}
    previousCommit = None
    line = blameOutput.readline()
    while line != '':
        commit, lineTmp  = line.split(' ')[0::2]
        if commit != previousCommit:
            if previousCommit is not None:
                yield BlameData(previousCommit, lineStart,
                                lineStart + lineCount, allCommits[previousCommit])
            previousCommit = commit
            lineStart = int(lineTmp)
            lineCount = 0
        lineCount += 1
        data = readCommitData(blameOutput, commit)
        if commit in allCommits:
            allCommits[commit].update(data)
        else:
            allCommits[commit] = data
        line = blameOutput.readline()
    yield BlameData(commit, lineStart,
                    lineStart + lineCount, allCommits[commit])

class BlameCursor:
    def __init__(self, generator):
        self.iterator = generator.__iter__()
        self._next();

    def _next(self):
        self.current = self.iterator.next()

    def getRange(self, start, end):
        if self.current.end > start:
            yield self.current
        while self.current.end <= start:
            self._next()
        yield self.current
        while self.current.end < end:
            self._next()
            yield self.current

def pipeBlame(filename):
    blame = subprocess.Popen(['git', 'blame', '-p', filename],
                             stdout=subprocess.PIPE, stderr=sys.stderr)
    for tuple in parseBlame(blame.stdout):
        yield tuple

def blameCursor(filename):
    return BlameCursor(pipeBlame(filename))


def pickNewest(blames):
    newest = blames[0]
    for b in blames[1:]:
        if not 'committer-time' in b.data or int(b.data['committer-time']) > int(newest.data['committer-time']):
            newest = b
    return newest

def concatIds(x, y):
    return x + '-' + y.id;

def mergeBlames(blames):
    blames = list(set(blames)) # uniq based on id
    if len(blames) == 1:
        return blames[0]
    id = reduce(concatIds, blames, 'merged')
    start = reduce(min, map(lambda b: b.start, blames))
    end = reduce(max, map(lambda b: b.end, blames))
    summary = 'Ambiguous attribution after reformat\n\n'
    summary += ''.join(map(lambda x: x.header(True),
                           sorted(blames, key=lambda x: x.id)))
    data = defaultBlame.data.copy()
    data['summary'] = summary
    return BlameData(id, start, end, data)

def padSubject(str):
    return str.replace('\n', '\n  ')
