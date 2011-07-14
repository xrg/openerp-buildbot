import os
from twisted.application import service
from buildbot.master import BuildMaster
from bbot_oe.master_poller import MasterPoller

basedir = os.path.normpath(os.path.dirname(__file__))
configfile = r'master.cfg'

application = service.Application('buildmaster')
BuildMaster(basedir, configfile).setServiceParent(application)

MasterPoller().setServiceParent(application)

