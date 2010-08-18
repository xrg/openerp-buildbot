=========================
Build Framework Overview
=========================

This is a general overview of the architecture and design principles of the
"buildbot" and its surrounding programs/settings.

Goal
=====
The goal, always, is to identify any problems that may exist at an OpenERP
version. We are looking for bugs, regressions and blocking issues. We want
to see if the problems are introduced in some specific commit of the VCS.

Design considerations
======================
The testing framework *must* report anything that might go wrong.
The testing framework *must not assume* a clean state of the workdirs,
it should ensure itself that the server runs at the correct environment.
The framework *should* get as close to the problem as possible, to help
us fix it fast. That also helps statistics, because we trace the correct
components/commits that cause each failure.

The testing framework *should* be flexible, adapt to future versions
of the server (+ addons), allow us to extend it with more logic.

The testing framework *should* keep the client-server design and consider
that we may deploy it to multiple slaves, with different architectures or
Linux distros, for cross-checking.

Testing tools
==============
We have a few test tools we can test our software with. These are:
  - Simple run of the openerp-server (a bug will break it)
  - Create database (a long operation, involves interesting steps)
  - Install modules (they must be sound to install)
  - Quality-check
and, in the future, we might add a few more steps:
  - Lint check (to xml and python files)
  - OERP Scenario testing
  - Other external tools (like ftp/webdav protocol testers)
  - db migrations
  - Test against older dbs


Upstream buildbot
==================
Our buildbot is based on the upstream buildbot project. We are using v0.7.x
of that. That one has been designed to overview compile procedures, typically
around a makefile that builds a program. It provides us with a rich library
of base classes and the client-server architecture.

However, it has a few limitations that must be worked around.

OpenERP buildbot
=================
Our buildbot is an "implementation" of the upstream framework. It consists
of the following key elements:
    - Buildbot classes (master / slave)
    - OpenERP module for a controlling database (through a stable openerp)
    - The "base_quality_interrogation" script (= engine)
    - Satellite scripts (LP :( , commit formatters etc.)

Buildbot classes
-----------------
These are mainly at the "master" (aka server) part, which tune the way we
read the commits, discover the changes and plan our tests.

At this point, the strategy is to test only the openerp addons that have
files changed at each commit. This can change, however, or even be conditional
on "nightly" or "daily" builds.

Base quality interrogation
---------------------------
This is a script at the slave side, will be discussed later


The base_quality_interrogation script
======================================
Referred as the "b-q-i" or "bqi", it is a key component of our testing 
framework.
One main reason for having it is that the upstream "buildbot" had only
been designed for synchronous testing steps, in which each shell command
has to finish before another will execute. In our case, we wanted to
launch the server, issue RPC calls to it and observe both processes.
The original "b-q-i" script would just detach from the server and act as
a openerp RPC client.

The b-q-i script has been moved from the openerp-server repo to the
buildbot one, because its version should not depend on the server, it has
to be developed independently.

Now, the b-q-i script does most of the work for us. It:
    - launches the server, makes sure it works
    - reads its log output, streams it to buildbot
    - parses the logs, picks interesting lines
    - issues RPC calls, enough to trigger tests (not extensive, though,
      we expect the Scenario to help us there)
    - Handles create-db, drop-db (so that tests are "clean")
    - Formats logs into a stream, that the buildbot can understand.

The b-q-i has a stateful engine, which will combine log lines from the 
server in order to produce meaningful error messages. Consider the case
of the log:
    INFO: module foobar: loading spam.xml
    ...
    ERROR: KeyError: id foobar.model_bar
it helps a lot to know that the KeyError exception happened while loading
that "spam.xml" file at "foobar" module.

The b-q-i, whatever it may parse with its engine, will still always push
the full, unchanged output of the openerp-server in a separate log.

The logging stream
-------------------
We are running the b-q-i script, the server and those tests. We want to 
log all output, but distinguish it so that the calling buildbot knows
what to do with it.

So, the b-q-i uses a concept of "log channels" that each receive a specific
subset of the log information. The channels are nothing more than individual
pythonic loggers, where the name of each logger matters.
Some loggers (like the 'bqi.state' and 'bqi.blame') have machine-formatted
content, so that buildbot can directly parse them into statistics etc.

The b-q-i script supports 3 logging formats: text, xml, and "machine". We 
use the last one (although the xml would also be sufficient), which is a
text-based, streamed, machine-parseable format. Buildbot has a decoder that
can directly parse the machine stream into several loggers. The machine
format is also simplistic enough to be read by humans (better than xml), so
that we can debug it easily.

That said, the full output of the openerp-server will be transparently
logged in a "server.stdout" logger.

We also have the bqi.state logger which conveys "commands" for the buildbot,
ie. switches its state (or report progress, in future). The "bqi.blame"
logger is the one that will hopefully report a formatted dictionary of
information for each error, to tell us exactly what had gone wrong. If the
blame information is not there or not meaningful, the detailed logs can
be examined.

B-q-i, finally logs its own operations (what it is trying to do) at a few
loggers named bqi.* . As a last resort, they will help us ensure that the
b-q-i works right and let us put more intelligence into it.

Channel structure
------------------
We want to connect the errors to the openerp addons that are involved, or
even the particular YAML tests that trigger them. That's where the b-q-i
will try to help us with the "context" concept. It will report us some
keyword of "where" each operation takes place.
With "modname" being a module, context can be:
    - modname.startup (when the server loads it at startup)
    - modname.install (when we install it afterwards)
    - modname.upgrade
    - modname.test
    [ - modname.test.some_test_file.yml  RFC ]

These will be decoded at the buildbot master side as individual "steps" and 
thus appear as separate entries in the "OpenERP-Test" build step.


