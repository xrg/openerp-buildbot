OpenERP - Buildbot
===================

Introduction
---

This is an implementation/backend for [Buildbot](http://trac.buildbot.net/) continuous
Integration system, based on OpenERP. We use OpenERP as a database; store the
configuration and build results there. Then, OpenERP can provide an instant GUI
for all those, as well as extra business logic in analyzing the results and
correlating the Buildbot data with project management models.

History
---

This project, and the initial design choices, were performed by devs at OpenERP SA,
when they had wanted to setup a CI for their own project's testing. Initially, and
up to v2.x, it was only designed to perform a single kind of test against an
OpenERP testing server. A rough addon was put on a "master" openerp instance to
store the results.

At 2010, v3 had been conceived: generalize on the idea, let this system perform
multiple tests, on projects other than OpenERP itself. Also, let the OpenERP 
models control the Buildbot configuration as well (rather than having it 
hard-coded in a python file). 

The v3 idea had been blocked until the summer of 2011, when it was eventually
implemented. Now, this project is used to help with anything that starts from
a code repository and involves an automated procedure:

 * building of RPMs (directly from repos)
 * trivial testing of code commits (eg. Lint)
 * mirroring of Git <-> Bzr repos
 * testing a variety of OpenERP setups (per branch, setup, set of tests)


Installation
---

That's the least documented/evolved part, since it has only happened twice
in the history of this project. Please be tolerant.

OpenERP-buildbot DOES require 'pg84' or 'F3' series of the server. It's a
matter of performance that the official servers cannot deliver.

You must at least install the "software_dev" addon, supplied in this project
in your openerp database. The "software_dev_mirrors" is only needed if you
intend to do DVCS mirroring.

Then, roughly speaking, you'd need to setup a buildmaster and a few 
buildslaves. So far, you need the [xrg-0.8](https://github.com/xrg/buildbot/tree/xrg-0.8)
branch of buildbot, as only this decouples the built-in SQL connector.
Install python-buildbot's master and slave, as site-packages, to your nodes.

At the master, there is only one file "master.cfg" to configure, where you
will only need to setup the connection to the openerp-f3 server.

For each builslave, you should setup the "buildbot.tac" file with connection
details and a password. Accordingly, you should enter the name/password in
the "buildslaves" of the OpenERP GUI.

Then, the hard part is, to setup repositories, projects, components and tests
for the code you wish to build/test. (to be written)

Once the configuration is changed, you must issue the "reload" command to
the buildbot master. This is either through a SIGHUP to the master process
or a Reconfigure async request through the OpenERP GUI. It may also take
a while to refresh the configuration, a limitation of buildbot 0.8 design.


TODO
---

Several ideas have been accumulated, candidates for further development:
 * Port to latest Buildbot API. Buildbot has been changing too much lately
   and I had not been able to catch up. Once it settles somewhere, it would
   be a nice chance to exploit its new features.
 * Exploit the Web-GUI of OpenERP-F3 . Instead of the literally "twisted"
   framework buildbot uses (which has I/O issues), serve the dashboards
   directly from F3 and expand them.
 * Finish the .spec file so that openerp-buildbot can easily install from RPMs
 * Be able to reconfigure builders on the fly (with newer buildbot API, perhaps)
 * Support Mercurial repos (must be easy)
 * Support SVN repos (may be hard, even impossible to mirror)
 * Finish the push mechanism to upstream repos (a bit tricky with authentication)
 * Statistically analyze the test results, connect to 'project' and 'hr'.
   Some work already started there.
 * Connect to the GitHub API, so that pull requests, issues can be sync
   between the build DB and the site. A few tests already done w. Launchpad, too.
 * Deactivate the buildbot's notifications, move them instead to "messaging"
   of F3, and thus support a richer set of possibilities.

Author
------

Versions v1, v2 developed by OpenERP SA.
v2.5, v3.x by Panos Christeas - [Twitter](http://twitter.com/#panos_xrg) [E-mail](xrg@hellug.gr)
