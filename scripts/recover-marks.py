#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# Copyright P. Christeas <xrg@hellug.gr> 2010-2012
# Based on the git-bzr-verifymarks.py script of 'rebzr' era.
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsibility of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
###############################################################################
#


import os
import sys
import re
# import datetime
import logging
import optparse

from openerp_libclient import rpc
from openerp_libclient.extra import options


def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Other options")
    #pgroup.add_option('-t', '--poll-interval', type=int,
    #                help="Polling Interval")
    pgroup.add_option('--collection', '-C', help="Collection id or name")
    pgroup.add_option('--limit', type=int, default=10, 
                    help="Only attempt so many bad marks")
    pgroup.add_option('--git-marks', help="Load additional git marks")
    pgroup.add_option('--bzr-marks', help="Load additional bzr marks")
    parser.add_option_group(pgroup)

options.init(options_prepare=custom_options,
        config='~/.openerp/buildbot.conf', have_args=False,
        config_section=())

log = logging.getLogger('main')
log.info("Init. Connecting...")

rpc.openSession(**options.connect_dsn)


if not rpc.login():
    raise Exception("Could not login!")
log.info("Connected.")

if not options.opts.collection:
    log.error("Must supply the collection to operate on")
    sys.exit(2)

if options.opts.collection.isdigit():
    coll_id = int(options.opts.collection)
else:
    cids = rpc.RpcProxy('software_dev.mirrors.branch_collection').\
            search([('name', '=', options.opts.collection)],)
    if not cids:
        log.error("Cannot locate collection \"%s\"", options.opts.collection)
        sys.exit(2)
    elif len(cids) > 1:
        log.error("Ambiguous collection specification")
        sys.exit(2)
    else:
        coll_id = cids[0]

marks_obj = rpc.RpcProxy('software_dev.mirrors.commitmap')

known_branches = {}
known_repos = {}
commit_obj = rpc.RpcProxy('software_dev.commit')
branch_obj = rpc.RpcProxy('software_dev.branch')
repo_obj = rpc.RpcProxy('software_dev.repo')

def get_commits(ids, fields=None):
    """ read a set of commit ids
        
        @return a dict like {id: ... }
    """
    
    if fields is None:
        fields = ['date', 'description', 'branch_id', 'hash',
                'commitmap_id', 'contained_commit_ids', 'ctype',
                'parent_id', 'subject']

    log.debug("Fetch commits: %r", ids)
    ret = {}
    fetch_branches = []
    for res in commit_obj.read(ids, fields=fields):
        
        parents = []
        if res.get('parent_id'):
            parents.append(res['parent_id'][0])
        if res.get('contained_commit_ids'):
            parents.extend(res['contained_commit_ids'])
        res['parents'] = parents
        ret[res['id']] = res
    
        if res['branch_id'][0] not in known_branches:
            fetch_branches.append(res['branch_id'][0])
        
    if fetch_branches:
        for fb in branch_obj.read(list(set(fetch_branches)), fields=['name', 'repo_id']):
            if fb['repo_id'][0] not in known_repos:
                known_repos[fb['repo_id'][0]] = repo_obj.read(fb['repo_id'][0], ['name', 'rtype'])
            fb['rtype'] = known_repos[fb['repo_id'][0]]['rtype']
            known_branches[fb['id']] = fb
    
    for cr in ret.values():
        cr['rtype'] = known_branches[cr['branch_id'][0]]['rtype']
    
    return ret

git_marks2 = {}
bzr_marks2 = {}

def git_marks_import(filename):
    """Read the mapping of marks to revision-ids from a file.

    :param filename: the file to read from
    :return: a dictionary with marks as keys and revision-ids
    """
    # Check that the file is readable and in the right format
    try:
        f = file(filename)
    except IOError:
        log.warning("Could not import marks file %s - not importing marks",
            filename)
        return None

    # Read the revision info
    for line in f:
        line = line.rstrip('\n')
        mark, revid = line.split(' ', 1)
        git_marks2.setdefault(revid,[]).append(mark)
    f.close()


def bzr_marks_import(filename):
    """Read the mapping of marks to revision-ids from a file.

    :param filename: the file to read from
    :return: None if an error is encountered or (revision_ids, branch_names)
      where
      * revision_ids is a dictionary with marks as keys and revision-ids
        as values
      * branch_names is a dictionary mapping branch names to some magic #
      
      Copyright (C) 2009 Canonical Ltd (GPL2)
    """
    # Check that the file is readable and in the right format
    try:
        f = file(filename)
    except IOError:
        log.warning("Could not import marks file %s - not importing marks",
            filename)
        return None
    firstline = f.readline()
    match = re.match(r'^format=(\d+)$', firstline)
    if not match:
        log.warning("%r doesn't look like a marks file - not importing marks",
            filename)
        return None
    elif match.group(1) != '1':
        log.warning('format version in marks file %s not supported - not importing'
            'marks', filename)
        return None

    # Read the branch info
    branch_names = {}
    for string in f.readline().rstrip('\n').split('\0'):
        if not string:
            continue
        name, integer = string.rsplit('.', 1)
        branch_names[name] = int(integer)
 
    # Read the revision info
    for line in f:
        line = line.rstrip('\n')
        mark, revid = line.split(' ', 1)
        bzr_marks2.setdefault(revid,[]).append(mark)
    f.close()

if __name__ == "__main__":
    if options.opts.git_marks:
        git_marks_import(options.opts.git_marks)
        log.info("loaded %d git marks", len(git_marks2))
    if options.opts.bzr_marks:
        bzr_marks_import(options.opts.bzr_marks)
        log.info("loaded %d bzr marks", len(bzr_marks2))

    for bad_mark in marks_obj.search_read([('collection_id', '=', coll_id), ('verified', 'not in', ('ok', 'unknown'))],
                fields=['mark', 'commit_ids', 'verified'],
                order='id', limit=options.opts.limit):
        log.debug("Found a %s mark: %s", bad_mark['verified'], bad_mark['mark'])
    
        if bad_mark['verified'] == 'bad-missing':
            commits = get_commits(bad_mark['commit_ids'])
            if not len(commits):
                log.info("Mark %s must be deleted!")
            else:
                for c in commits.values():
                    if c['rtype'] == 'git':
                        alts = git_marks2.get(c['hash'], [])
                        if len(alts) > 1 or bad_mark['mark'] not in alts:
                            log.info("Located alternatives for %s: %r", bad_mark['mark'], alts)
                    elif c['rtype'] == 'bzr':
                        alts = bzr_marks2.get(c['hash'], [])
                        if len(alts) > 1 or bad_mark['mark'] not in alts:
                            log.info("Located alternatives for %s: %r", bad_mark['mark'], alts)
                    else:
                        log.warning("No rtype for commit %d !", c['id'])
        elif bad_mark['verified'] == 'bad-parents':
            commits = get_commits(bad_mark['commit_ids'])
            for cmt in commits.values():
                cmt['parent_marks'] = []
                for pv in commit_obj.read(cmt['parents'], fields=['commitmap_id']):
                    cmt['parent_marks'].append(pv['commitmap_id'])
            
                log.debug('Commit %d has parents: %r', cmt['id'], cmt['parent_marks'])
            
        else:
            log.warning("Cannot handle %s mark: %s!", bad_mark['verified'], bad_mark['mark'])

    log.info('Exiting')
#eof
