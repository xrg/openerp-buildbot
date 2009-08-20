
from twisted.application import service
from buildbot.master import BuildMaster

basedir = r'/home/nch/openERP/Extra-branch/HMOsir/openerp-buildbot/openerp_buildbot_master'
configfile = r'master.cfg'

application = service.Application('buildmaster')
BuildMaster(basedir, configfile).setServiceParent(application)

