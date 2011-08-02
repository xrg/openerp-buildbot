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

#.apidoc title: Import Fastexport Marks
import sys
import os

import logging
import time
import optparse
import re
import marks_file

logging.basicConfig(level=logging.INFO)

from openerp_libclient import rpc, agent_commands

import getpass

usage = """%prog [options]
"""

parser = optparse.OptionParser(usage)
parser.add_option("-H", "--url", default=None,
                    help="URL of remote server to connect to"),
parser.add_option("-v", "--debug", dest="debug", action='store_true', default=False,
                    help="Enable debugging information")
parser.add_option("--quiet", dest="quiet", action='store_true', default=False,
                    help="Print less verbose messages")

# parser.add_option("-d", "--database", dest="db_name", help="specify the database name")
# parser.add_option("-t", "--type", dest="marks_type", help="Type of marks file, bzr or git")
parser.add_option("-R", "--repo-id", dest="repo_id", type="int", help="Id of repository")

(opt, args) = parser.parse_args()

def die(msg, *args):
    logging.getLogger().critical(msg, *args)
    sys.exit(1)

if not opt.repo_id:
    die("Repository id must be specified")

if not args:
    die("At least one marks file must be selected")

if opt.debug:
    logging.getLogger().setLevel(logging.DEBUG)
elif opt.quiet:
    logging.getLogger().setLevel(logging.WARN)

connect_dsn = {'proto': 'http', 'user': 'admin', 'host': 'localhost', 'port': 8069, 
        'dbname': 'buildbot'}

def parse_url_dsn(url):
    import urlparse
    global connect_dsn
    netloc_re = re.compile( r'(?:(?P<user>[^:@]+?)(?:\:(?P<passwd>[^@]*?))?@)?'
        r'(?P<host>(?:[\w\-\.]+)|(?:\[[0-9a-fA-F:]+\]))'
        r'(?:\:(?P<port>[0-9]{1,5}))?$')
    uparts = urlparse.urlparse(url, allow_fragments=False)
    
    if uparts.scheme:
        connect_dsn['proto'] = uparts.scheme
    if uparts.netloc:
        um = netloc_re.match(uparts.netloc)
        if not um:
            raise ValueError("Cannot decode net locator: %s" % uparts.netloc)
        for k, v in um.groupdict().items():
            if v is not None:
                connect_dsn[k] = v
    if uparts.query:
        pass
    if uparts.path and len(uparts.path) > 1:
        connect_dsn['dbname'] = uparts.path.split('/')[1]
    # path, params, fragment

if opt.url:
    parse_url_dsn(opt.url)

if not connect_dsn.get('passwd'):
    connect_dsn['passwd'] = getpass.getpass("Enter the password for %s@%s: " % \
        (connect_dsn['user'], connect_dsn['dbname']))

rpc.openSession(**connect_dsn)

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


repo_obj = rpc.RpcProxy('software_dev.repo')
repo_res = repo_obj.read([opt.repo_id], fields=['rtype'])
if not repo_res:
    die("Could not fetch repo_id: %d" % opt.repo_id)

logger = logging.getLogger('main')

rtype = repo_res[0]['rtype']
logger.debug("Operating at a %s repo #%d", rtype, repo_res[0]['id'])

cmmap_obj = rpc.RpcProxy('software_dev.mirrors.commitmap')

for fname in args:
    try:
        if rtype == 'git':
            rev_ids = git_marks_import(fname)

        elif rtype == 'bzr':
            rev_ids = marks_file.import_marks(fname)[0]
            bad_marks = []
            for m in rev_ids:
                if not m.startswith(':'):
                    if (':'+m) in rev_ids:
                        print "Invalid mark %s" % m
                        bad_marks.append(m)
                    else:
                        rev_ids[':'+m] = rev_ids.pop(m)
            if bad_marks:
                raise Exception("Bad marks found")
        else:
            raise Exception("Unknown repository type: %s" % rtype)
        
        res = cmmap_obj.feed_marks(opt.repo_id, rev_ids)

        if not res:
            logger.warning("No result from feed_marks()")
            continue
        
        logger.info("Marks imported: %s processed / %s skipped", res.get('processed', 0), res.get('skipped', 0))
        if res.get('errors'):
            logger.warning("Some errors reported: %s", ', '.join(res['errors'].keys()))
            print "Errors:"
            for e, r in res['errors'].items():
                print "%s: %r" % (e, r)
            print
    except Exception:
        logger.exception("Could not import %s", fname)
        break
else:
    logger.info("All files imported successfully")
#eof
