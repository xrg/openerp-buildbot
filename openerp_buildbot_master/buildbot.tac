import os
from twisted.application import service
from buildbot.master import BuildMaster
from bbot_oe.master_poller import MasterPoller

basedir = os.path.normpath(os.path.dirname(__file__))
configfile = os.path.abspath(os.path.join(basedir, r'master.cfg'))

if os.path.islink(os.path.join(basedir,'basedir')):
    basedir = os.path.realpath(os.path.join(basedir,'basedir'))

application = service.Application('buildmaster')
BuildMaster(basedir, configfile).setServiceParent(application)

MasterPoller().setServiceParent(application)

