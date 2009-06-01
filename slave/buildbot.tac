
from twisted.application import service
from buildbot.slave.bot import BuildSlave

basedir = r'/home/tiny/buildbot/slave'
buildmaster_host = 'pap'
port = 9989
slavename = 'testslave'
passwd = 'pap'
keepalive = 600
usepty = 1
umask = None

application = service.Application('buildslave')
s = BuildSlave(buildmaster_host, port, slavename, passwd, basedir,
               keepalive, usepty, umask=umask)
s.setServiceParent(application)

