#!/usr/bin/python
"""
Implementation of the command-line I{pyflakes} tool.
"""

import compiler, sys
import os

from pyflakes import checker
from pyflakes.messages import UnusedImport, UndefinedExport, UndefinedLocal, UndefinedName

def check(codeString, filename):
    """
    Check the Python source given by C{codeString} for flakes.

    @param codeString: The Python source to check.
    @type codeString: C{str}

    @param filename: The name of the file the source came from, used to report
        errors.
    @type filename: C{str}

    @return: The number of warnings emitted.
    @rtype: C{int}
    """
    # Since compiler.parse does not reliably report syntax errors, use the
    # built in compiler first to detect those.
    try:
        try:
            compile(codeString, filename, "exec")
        except MemoryError:
            # Python 2.4 will raise MemoryError if the source can't be
            # decoded.
            if sys.version_info[:2] == (2, 4):
                raise SyntaxError(None)
            raise
    except (SyntaxError, IndentationError), value:
        msg = value.args[0]

        (lineno, offset, text) = value.lineno, value.offset, value.text

        # If there's an encoding problem with the file, the text is None.
        if text is None:
            # Avoid using msg, since for the only known case, it contains a
            # bogus message that claims the encoding the file declared was
            # unknown.
            print >> sys.stderr, "%s: problem decoding source" % (filename, )
        else:
            line = text.splitlines()[-1]

            if offset is not None:
                offset = offset - (len(text) - len(line))

            print >> sys.stderr, '%s:%d: %s' % (filename, lineno, msg)
            print >> sys.stderr, line

            if offset is not None:
                print >> sys.stderr, " " * offset, "^"

        raise
    else:
        # Okay, it's syntactically valid.  Now parse it into an ast and check
        # it.
        tree = compiler.parse(codeString)
        w = checker.Checker(tree, filename)
        w.messages.sort(lambda a, b: cmp(a.lineno, b.lineno))
        if filename.endswith('__init__.py'):
            w.messages = filter(lambda x: not isinstance(x, UnusedImport), w.messages)
        warns = errors = 0
        for warning in w.messages:
            print warning
            if isinstance(warning, UndefinedName):
                # Some undefined names may be legal, such as gettext's "_()"
                if warning.message_args[0] in ('_', 'openerp_version' ):
                    warns += 1
                else:
                    errors += 1
            elif isinstance(warning, (UndefinedExport, UndefinedLocal, UndefinedName)):
                errors += 1
            else:
                warns += 1
            
        return warns, errors


def checkPath(filename):
    """
    Check the given path, printing out any warnings detected.

    @return: the number of warnings printed
    """
    try:
        return check(file(filename, 'U').read() + '\n', filename)
    except IOError, msg:
        print >> sys.stderr, "%s: %s" % (filename, msg.args[1])
        return 1


def main():
    warnings = errors = 0
    args = sys.argv[1:]
    try:
        if args:
            for arg in args:
                if os.path.isdir(arg):
                    for dirpath, dirnames, filenames in os.walk(arg):
                        for filename in filenames:
                            if filename.endswith('.py'):
                                wa, er = checkPath(os.path.join(dirpath, filename))
                                warnings += wa
                                errors += er
                else:
                    wa, er = checkPath(arg)
                    warnings += wa
                    errors += er
        else:
            wa, er = check(sys.stdin.read(), '<stdin>')
            warnings += wa
            errors += er
    except SyntaxError:
        raise SystemExit(1)
    
    if errors > 0:
        raise SystemExit(1)
    if warnings > 0 :
        raise SystemExit(3)

    return None

main()