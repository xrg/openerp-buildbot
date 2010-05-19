
from twisted.application import service
from buildbot.slave.bot import BuildSlave
from buildbot.slave.registry import registerSlaveCommand
from openobject import command 

basedir = r'/home/hmo/Projects/OpenERP-Buildbot/openerp-buildbot-v2/openerp_buildbot_slave'
buildmaster_host = '127.0.0.1'
port = 8999
slavename = 'openerp_bot'
passwd = 'tiny'
keepalive = 600
usepty = 1
umask = None

application = service.Application('buildslave')
s = BuildSlave(buildmaster_host, port, slavename, passwd, basedir,
               keepalive, usepty, umask=umask)
s.setServiceParent(application)

	

registerSlaveCommand("copy", command.SlaveCp, command.command_version)
registerSlaveCommand("create-db", command.CreateDB, command.command_version)
registerSlaveCommand("install-module", command.InstallModule, command.command_version)
registerSlaveCommand("openobjectbzr", command.OpenObjectBzr, command.command_version)


