# blame-bridge

Beautify code without losing blame labels

## Reformat your code

Any serious project has a coding standard, but it's often the case that existing
code doesn't always conform to that standard.  Maybe the standard has been
changed, or maybe it's new, or maybe the odd problem slips through the cracks
from time to time.

You want to fix this, but reformatting causes your version control to lose all
that precious blame information.  You don't want your code to be attributed to
the reformatter, or the poor sap who was given the job of running it.  You want
to seamlessly move code across, retaining blames.

Now it's easy:

```sh
$ blame-bridge/main.py file1.js file2.js
# file1.js: 30 patches over 58 chunks created
# file2.js: 5 patches over 12 chunks created
```

blame-bridge doesn't alter files directly, instead it creates a numbered set of
patches, all in a form that can be passed to `git am` or equivalent.  Just apply
them all in order and your reformatted file can be correctly attributed.

```sh
$ (for i in (ls *.blame-bridge* | sort); do echo "Applying $i:"; git am "$i" || exit 1; done)
...
```

## Limitations

This only supports git.  There are some small dependencies in a few places, but
the major problem is the dependency on the output of `git blame -p`.

Currently, blame-bridge hard codes the beautifier options.  This is an easy fix,
but I'm tired already and I don't want to wrestle with argparse.

blame-bridge uses diff to work out what the code beautifier has done.  If a
single chunk of diff is attributed to multiple people, it tries to split things
out, but it's not always possible to do so cleanly.  It can't do any splitting
if the reformatter changes things other than whitespace It might be possible to
add extra characters that are ignored for this case.

This is my first attempt at Python, it's probably^Wdefinitely sucky code, and buggy.
