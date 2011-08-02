#!/usr/bin/python
# -*- encoding: utf-8 -*-
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
