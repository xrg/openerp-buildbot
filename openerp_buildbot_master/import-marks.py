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

parser.add_option('--force', action="store_true", default=False,
                    help="Force import when bzr even bad marks exist")
parser.add_option('--reset-old', dest="reset_old", 
                    action="store_true", default=False,
                    help="Only re-import old ones, don't push new"),
parser.add_option('--write-errors', action="store_true", default=False,
                    help="Write errors to files")
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
commit_obj = rpc.RpcProxy('software_dev.commit')

for fname in args:
    try:
        if rtype == 'git':
            rev_ids = git_marks_import(fname)

        elif rtype == 'bzr':
            logger.info("import as bzr")
            rev_ids_orig = marks_file.import_marks(fname)
            bad_marks = []
            rev_ids = {}
            for m, rev in rev_ids_orig.items():
                if m.startswith(':'):
                    rev_ids[m] = rev
                else:
                    if (':'+m) in rev_ids_orig:
                        logger.debug("Invalid mark %s", m)
                        bad_marks.append(m)
                    else:
                        rev_ids[':'+m] = rev
            if bad_marks and opt.force:
                logger.warning("Skipping %d bad marks", len(bad_marks))
            elif bad_marks:
                raise Exception("Bad marks found")
            del rev_ids_orig
        else:
            raise Exception("Unknown repository type: %s" % rtype)
        for m in rev_ids:
                if not m.startswith(':'):
                    raise RuntimeError(m)
        context = {}
        if opt.reset_old:
            context['old_marks_only'] = True
            context['double_marks'] = 'older'
        res = cmmap_obj.feed_marks(opt.repo_id, rev_ids, context=context)

        if not res:
            logger.warning("No result from feed_marks()")
            continue
        
        logger.info("Marks imported: %s processed / %s skipped", res.get('processed', 0), res.get('skipped', 0))
        if res.get('errors'):
            logger.warning("Some errors reported: %s", ', '.join(res['errors'].keys()))
            if opt.write_errors:
                repo_forks = repo_obj.get_all_forks([opt.repo_id])[str(opt.repo_id)]
                if 'double-mapped' in res['errors']:
                    rev_map = dict( [ (k, i) for i, k in rev_ids.items()])
                    # it's a list containing the hashes
                    efname = fname + '.double-mapped'
                    logger.info("Writting double-mapped list to %s", efname)
                    fp = open(efname, 'wb')
                    hashes = res['errors'].pop('double-mapped')
                    other_marks = {}
                    for eres in commit_obj.search_read([('hash', 'in', hashes), ('branch_id.repo_id', 'in', repo_forks)], fields=['commitmap_id', 'hash']):
                        other_marks[eres['hash']] = eres['commitmap_id'][1]
                    for h in hashes:
                        fp.write('%s %s %s\n' %(rev_map.get(h, '?'), h, other_marks.get(h, '?')))
                    fp.close()
                if 'mark-conflict' in res['errors']:
                    efname = fname + '.conflict'
                    logger.info("Writting conflicting marks list to %s", efname)
                    fp = open(efname, 'wb')
                    emarks = res['errors'].pop('mark-conflict')
                    other_marks = {}
                    for eres in commit_obj.search_read([('commitmap_id.mark', 'in', emarks), ('branch_id.repo_id', 'in', repo_forks)], fields=['commitmap_id', 'hash']):
                        other_marks[eres['commitmap_id'][1]] = eres['hash']
                    for em in emarks:
                        fp.write('%s %s %s\n' % (em, rev_ids.get(em,'?'), other_marks.get(em, '?')))
                    fp.close()
            for e, marks in res['errors'].items():
                print "%s: %r" % (e, r)
            print
    except Exception:
        logger.exception("Could not import %s", fname)
        break
else:
    logger.info("All files imported successfully")
#eof
