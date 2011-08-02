#!/usr/bin/python
# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP Buildbot
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import sys
import os

import logging
import time
logging.basicConfig(level=logging.DEBUG)

from openerp_libclient import rpc, agent_commands

import getpass

d_dbname = 'refdb'
d_user = 'admin'
d_passwd = getpass.getpass("Enter the password for %s@%s: " % \
        (d_user, d_dbname))

rpc.openSession(proto="https", host='localhost', port='8071', 
    user=d_user, passwd=d_passwd, dbname=d_dbname)

r = rpc.login()
if not r :
    raise Exception("Could not login! %r" % r)

def git_marks_import(filename):
    """Read the mapping of marks to revision-ids from a file.

    :param filename: the file to read from
    :return: a dictionary with marks as keys and revision-ids
    """
    # Check that the file is readable and in the right format
    try:
        f = file(filename)
    except IOError:
        raise Exception("Could not import marks file %s - not importing marks",
            filename)

    # Read the revision info
    revision_ids = {}
    for line in f:
        line = line.rstrip('\n')
        mark, revid = line.split(' ', 1)
        revision_ids[mark] = revid
    f.close()
    return revision_ids


rev_ids = git_marks_import('/home/panos/build/openerp-rebzr/gits/buildbot/.git/import.marks')
repo_id = 36

cmmap_obj = rpc.RpcProxy('software_dev.mirrors.commitmap')

res = cmmap_obj.feed_marks(repo_id, rev_ids)

print "Result:", res

#eof
