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

#.apidoc title: Find incomplete Bzr commits and push from local to remote
import sys

import logging
import optparse
import re
from bzrlib.repository import Repository, InterRepository
import bzrlib.errors

logging.basicConfig(level=logging.INFO)

from openerp_libclient import rpc

import getpass

usage = """%prog [options] source destination

    Push incomplete commits from <source> repo to <destination>
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

parser.add_option("-L", "--limit", dest="limit", type="int", help="Limit of commits to try")

(opt, args) = parser.parse_args()

def die(msg, *args):
    logging.getLogger().critical(msg, *args)
    sys.exit(1)

if not opt.repo_id:
    die("Repository id must be specified")

if (not args) or len(args) != 2:
    die("You must provide source and destination Bzr URLs")

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

repo_obj = rpc.RpcProxy('software_dev.repo')
repo_res = repo_obj.read([opt.repo_id], fields=['rtype'])
if not repo_res:
    die("Could not fetch repo_id: %d" % opt.repo_id)
    
if repo_res[0]['rtype'] != 'bzr':
    die("This script can only be run against bzr repositories")

logger = logging.getLogger('main')

logger.debug("Operating at a %s repo #%d", repo_res[0]['rtype'], repo_res[0]['id'])

commit_obj = rpc.RpcProxy('software_dev.commit')

cres = commit_obj.search_read([('branch_id.repo_id', '=', repo_res[0]['id']), ('ctype','=', 'incomplete')],
        limit=(opt.limit or False), fields=['hash'])

if cres:
    logger.info("Found %d incomplete commits, trying them", len(cres))
    source_repo = Repository.open(args[0])
    logger.debug("Opened %s repo as source", args[0])
    target_repo = Repository.open(args[1])
    logger.debug("Opened %s repo as target", args[1])
    irr = InterRepository(source_repo, target_repo)
    
    copied = 0
    for cmt in cres:
        try:
            irr.fetch(str(cmt['hash']))
        except bzrlib.errors.NoSuchId:
            logger.warning('Cannot find "%s" revision in source', cmt['hash'])
            continue
        copied += 1
        if copied % 100 == 0:
            print "Copying commits: %d" % copied
    logger.info("Successfully copied %d commits", copied)
else:
    logger.info("No incomplete commits found for that repo.")
#eof
