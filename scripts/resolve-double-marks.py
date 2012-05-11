#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# Copyright P. Christeas <xrg@hellug.gr> 2012
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
    pgroup.add_option('--collection', '-C', help="Collection id or name")
    #pgroup.add_option('--limit', type=int, default=10, 
    #                help="Only attempt so many bad marks")
    pgroup.add_option('--git-marks', help="Load additional git marks")
    pgroup.add_option('--bzr-marks', help="Load additional bzr marks")
    #pgroup.add_option('--active', dest="do_write",
    #                action="store_true", default=False,
    #                help="write back to the database"),
    parser.add_option_group(pgroup)

options.init(options_prepare=custom_options,
        config='~/.openerp/buildbot.conf',
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


git_marks = {}
bzr_marks = {}
rev_git_marks = {}
rev_bzr_marks = {}


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
        rev_git_marks.setdefault(revid,[]).append(mark)
        git_marks[mark] = revid
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
        bzr_marks[mark] = revid
        rev_bzr_marks.setdefault(revid,[]).append(mark)
    f.close()

def check_hashes(hashes):
    """ Each hash supplied may have a double entry. Resolve it
    """
    
    hdone = []
    
    num_checked = 0
    num_errors = 0
    for h in hashes:
        if h in hdone:
            continue
        
        num_checked += 1
        hdone.append(h)
        
        remote_hashes = []
        if h in rev_git_marks:
            mids = rev_git_marks[h]
            log.debug('Git hash %s maps to marks %r', h[:12], mids)
            assert mids
            for m in mids:
                b = bzr_marks.get(m, False)
                if b:
                    remote_hashes.append(b)
                elif m.startswith(':') and m[1:] in bzr_marks:
                    remote_hashes.append(bzr_marks[m[1:]])
            if not remote_hashes:
                log.warning("No bzr hashes found for marks %r", mids)
                num_errors += 1
                continue
            
        elif h in rev_bzr_marks:
            mids = rev_bzr_marks[h]
            log.debug('Bzr hash %s maps to marks %r', h[:12], mids)
            assert mids
            for m in mids:
                if not m.startswith(':'):
                    m = ':' + m
                b = git_marks.get(m, False)
                if b:
                    remote_hashes.append(b)
            if not remote_hashes:
                log.warning("No git hashes found for marks %r", mids)
                num_errors += 1
                continue
        else:
            log.error("Hash %s is not fastexported!", h)
            num_errors += 1
        
        log.debug("Remote hashes are now: %r", remote_hashes)
        cmts = commit_obj.search_read([('hash', 'in', [h,] + remote_hashes )], fields=['hash', 'commitmap_id'])
        
        hash_mark = None
        for cmt in cmts:
            if not cmt['commitmap_id']:
                log.warning("Fishy, why no mark for %s?", cmt['hash'])
                continue
            if cmt['hash'] == h:
                hash_mark = cmt['commitmap_id'][1]
        
        assert hash_mark
        sane = False
        
        other_marks = []
        # second iteration
        for cmt in cmts:
            if not cmt['commitmap_id']:
                continue
            elif cmt['hash'] == h:
                continue
            elif cmt['commitmap_id'][1] == hash_mark:
                if cmt['hash'] in remote_hashes:
                    sane = True
                    hdone.append(cmt['hash'])
                    log.debug("Found remote hash %s from mark %s, matching", cmt['hash'][:20], hash_mark)
                else:
                    log.info("Commit is not mapped here: %s", cmt['hash'][20])
            else:
                other_marks.append(cmt['commitmap_id'][1])
                
        if not sane:
            log.warning("Hash %s maps to marks %r in file, %s + %r in db", h[:20], mids, other_marks)
            num_errors += 1

    log.info("Checked %d hashes, %d errors", num_checked, num_errors)

if __name__ == "__main__":
    if options.opts.git_marks:
        git_marks_import(options.opts.git_marks)
        log.info("loaded %d git marks", len(git_marks))
    else:
        log.error("Must supply git marks")
        sys.exit(1)
    if options.opts.bzr_marks:
        bzr_marks_import(options.opts.bzr_marks)
        log.info("loaded %d bzr marks", len(bzr_marks))
    else:
        log.error("Must supply bzr marks")
        sys.exit(1)

    hash_to_check = []
    for fil in options.args:
        try:
            log.info("Reading %s", fil)
            fp = open(fil,'rb')
            for lin in fp.read().split('\n'):
                lin = lin.strip()
                if (not lin) or lin.startswith('#'):
                    continue
                hash_to_check.append(lin)
            fp.close()
        except Exception, e:
            log.error("Could not read %s: %s", fil, e)
        
        log.info("Must check %d hashes", len(hash_to_check))

        check_hashes(hash_to_check)

    log.info('Exiting.')
#eof
