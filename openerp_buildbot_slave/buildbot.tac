#!/usr/bin/python

import os

from twisted.application import service
from buildslave.bot import BuildSlave
# from buildslave.commands.registry import registerSlaveCommand

import command

basedir = os.path.abspath(os.path.join(os.path.normpath(os.path.dirname(__file__)),'build'))
buildmaster_host = '127.0.0.1'
port = 8999
slavename = 'openerp_bot'
passwd = 'tiny'
keepalive = 600
usepty = 1
umask = None

application = service.Application('buildslave')
s = BuildSlave(buildmaster_host, port, slavename, passwd, basedir, keepalive, usepty, umask=umask)
s.setServiceParent(application)

# registerSlaveCommand("OpenObjectShell", command.OpenObjectShell, command.command_version)
# registerSlaveCommand("openobjectbzr", command.OpenObjectBzr, command.command_version)


