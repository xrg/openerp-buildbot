import os
from twisted.application import service
from buildbot.master import BuildMaster

basedir = os.path.normpath(os.path.dirname(__file__))
configfile = r'master.cfg'

application = service.Application('buildmaster')
BuildMaster(basedir, configfile).setServiceParent(application)

