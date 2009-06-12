
from twisted.application import service
from buildbot.master import BuildMaster

basedir = r'/home/hmo/Office/Projects/openerp_buildbot_master'
configfile = r'master.cfg'

application = service.Application('buildmaster')
BuildMaster(basedir, configfile).setServiceParent(application)

