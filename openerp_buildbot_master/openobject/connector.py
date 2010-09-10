# -*- encoding: utf-8 -*-

from twisted.python import log, threadable
from twisted.internet import defer
from buildbot import util

from buildbot.util import collections as bbcollections
from buildbot.changes.changes import Change
from buildbot.sourcestamp import SourceStamp
from buildbot.buildrequest import BuildRequest
from buildbot.process.properties import Properties
from buildbot.status.builder import SUCCESS, WARNINGS, FAILURE
from buildbot.util.eventual import eventually
from buildbot.util import json

import rpc

class Token: # used for _start_operation/_end_operation
    pass

class OERPConnector(util.ComparableMixin):
    # this will refuse to create the database: use 'create-master' for that
    compare_attrs = ["args", "kwargs"]
    synchronized = ["notify", "_end_operation"]

    def __init__(self, spec):
        # self._query_times = collections.deque()
        self._spec = spec

        # this is for synchronous calls: runQueryNow, runInteractionNow
        self._dbapi = spec.get_dbapi()
        self._nonpool = None
        self._nonpool_lastused = None
        self._nonpool_max_idle = spec.get_maxidle()

        self._change_cache = util.LRUCache()
        self._sourcestamp_cache = util.LRUCache()
        self._active_operations = set() # protected by synchronized=
        self._pending_notifications = []
        self._subscribers = bbcollections.defaultdict(set)

        self._pending_operation_count = 0

        self._started = False

    def _getCurrentTime(self):
        # this is a seam for use in testing
        return util.now()

    def start(self):
        # this only *needs* to be called in reactorless environments (which
        # should be eliminated anyway).  but it doesn't hurt anyway
        # self._pool.start()
        self._started = True

    def stop(self):
        """Call this when you're done with me"""

        # Close our synchronous connection if we've got one
        #if self._nonpool:
        #    self._nonpool.close()
        #    self._nonpool = None
        #    self._nonpool_lastused = None

        if not self._started:
            return
        #self._pool.close()
        self._started = False
        #del self._pool

    def get_version(self):
        """Returns None for an empty database, or a number (probably 1) for
        the database's version"""
        return 0

    def _start_operation(self):
        t = Token()
        self._active_operations.add(t)
        return t

    def _end_operation(self, t):
        # this is always invoked from the main thread, but is wrapped by
        # synchronized= and threadable.synchronous(), since it touches
        # self._pending_notifications, which is also touched by
        # runInteraction threads
        self._active_operations.discard(t)
        if self._active_operations:
            return
        for (category, args) in self._pending_notifications:
            # in the distributed system, this will be a
            # transport.write(" ".join([category] + [str(a) for a in args]))
            eventually(self.send_notification, category, args)
        self._pending_notifications = []

    # TODO:
    def notify(self, category, *args):
        # this is wrapped by synchronized= and threadable.synchronous(),
        # since it will be invoked from runInteraction threads
        self._pending_notifications.append( (category,args) )

    def send_notification(self, category, args):
        # in the distributed system, this will be invoked by lineReceived()
        #print "SEND", category, args
        for observer in self._subscribers[category]:
            eventually(observer, category, *args)

    def subscribe_to(self, category, observer):
        self._subscribers[category].add(observer)


    # ChangeManager methods

    def addChangeToDatabase(self, change):
        change_obj = rpc.RpcProxy('software_dev.commit')
        change.number = change_obj.submit_change(change.asDict())

        self.notify("add-change", change.number)
        self._change_cache.add(change.number, change)

    def changeEventGenerator(self, branches=[], categories=[], committers=[], minTime=0):
        q = "SELECT changeid FROM changes"
        args = []
        if branches or categories or committers:
            q += " WHERE "
            pieces = []
            if branches:
                pieces.append("branch IN %s" % self.parmlist(len(branches)))
                args.extend(list(branches))
            if categories:
                pieces.append("category IN %s" % self.parmlist(len(categories)))
                args.extend(list(categories))
            if committers:
                pieces.append("author IN %s" % self.parmlist(len(committers)))
                args.extend(list(committers))
            if minTime:
                pieces.append("when_timestamp > %d" % minTime)
            q += " AND ".join(pieces)
        q += " ORDER BY changeid DESC"
        rows = self.runQueryNow(q, tuple(args))
        for (changeid,) in rows:
            yield self.getChangeNumberedNow(changeid)

    def getLatestChangeNumberNow(self, branch=None, t=None):
        change_obj = rpc.RpcProxy('software_dev.commit')
        res = change_obj.search([], 0, 1, "id desc")
        if (not res) or not res[0]:
            return None
        return res[0][0]

    def getChangeNumberedNow(self, changeid, t=None):
        # this is a synchronous/blocking version of getChangeByNumber
        assert changeid >= 0
        c = self._change_cache.get(changeid)
        if c:
            return c
        if t:
            c = self._txn_getChangeNumberedNow(t, changeid)
        else:
            c = self.runInteractionNow(self._txn_getChangeNumberedNow, changeid)
        self._change_cache.add(changeid, c)
        return c
    def _txn_getChangeNumberedNow(self, t, changeid):
        q = self.quoteq("SELECT author, comments,"
                        " is_dir, branch, revision, revlink,"
                        " when_timestamp, category,"
                        " repository, project"
                        " FROM changes WHERE changeid = ?")
        t.execute(q, (changeid,))
        rows = t.fetchall()
        if not rows:
            return None
        (who, comments,
         isdir, branch, revision, revlink,
         when, category, repository, project) = rows[0]
        branch = str_or_none(branch)
        revision = str_or_none(revision)
        q = self.quoteq("SELECT link FROM change_links WHERE changeid=?")
        t.execute(q, (changeid,))
        rows = t.fetchall()
        links = [row[0] for row in rows]
        links.sort()

        q = self.quoteq("SELECT filename FROM change_files WHERE changeid=?")
        t.execute(q, (changeid,))
        rows = t.fetchall()
        files = [row[0] for row in rows]
        files.sort()

        p = self.get_properties_from_db("change_properties", "changeid",
                                        changeid, t)
        c = Change(who=who, files=files, comments=comments, isdir=isdir,
                   links=links, revision=revision, when=when,
                   branch=branch, category=category, revlink=revlink,
                   repository=repository, project=project)
        c.properties.updateFromProperties(p)
        c.number = changeid
        return c

    def getChangeByNumber(self, changeid):
        # return a Deferred that fires with a Change instance, or None if
        # there is no Change with that number
        assert changeid >= 0
        c = self._change_cache.get(changeid)
        if c:
            return defer.succeed(c)
        d1 = self.runQuery(self.quoteq("SELECT author, comments,"
                                       " is_dir, branch, revision, revlink,"
                                       " when_timestamp, category,"
                                       " repository, project"
                                       " FROM changes WHERE changeid = ?"),
                           (changeid,))
        d2 = self.runQuery(self.quoteq("SELECT link FROM change_links"
                                       " WHERE changeid=?"),
                           (changeid,))
        d3 = self.runQuery(self.quoteq("SELECT filename FROM change_files"
                                       " WHERE changeid=?"),
                           (changeid,))
        d4 = self.runInteraction(self._txn_get_properties_from_db,
                "change_properties", "changeid", changeid)
        d = defer.gatherResults([d1,d2,d3,d4])
        d.addCallback(self._getChangeByNumber_query_done, changeid)
        return d

    def _getChangeByNumber_query_done(self, res, changeid):
        (rows, link_rows, file_rows, properties) = res
        if not rows:
            return None
        (who, comments,
         isdir, branch, revision, revlink,
         when, category, repository, project) = rows[0]
        branch = str_or_none(branch)
        revision = str_or_none(revision)
        links = [row[0] for row in link_rows]
        links.sort()
        files = [row[0] for row in file_rows]
        files.sort()

        c = Change(who=who, files=files, comments=comments, isdir=isdir,
                   links=links, revision=revision, when=when,
                   branch=branch, category=category, revlink=revlink,
                   repository=repository, project=project)
        c.properties.updateFromProperties(properties)
        c.number = changeid
        self._change_cache.add(changeid, c)
        return c

    def getChangesGreaterThan(self, last_changeid, t=None):
        """Return a Deferred that fires with a list of all Change instances
        with numbers greater than the given value, sorted by number. This is
        useful for catching up with everything that's happened since you last
        called this function."""
        assert last_changeid >= 0
        if t:
            return self._txn_getChangesGreaterThan(t, last_changeid)
        else:
            return self.runInteractionNow(self._txn_getChangesGreaterThan,
                                          last_changeid)
    def _txn_getChangesGreaterThan(self, t, last_changeid):
        q = self.quoteq("SELECT changeid FROM changes WHERE changeid > ?")
        t.execute(q, (last_changeid,))
        changes = [self.getChangeNumberedNow(changeid, t)
                   for (changeid,) in t.fetchall()]
        changes.sort(key=lambda c: c.number)
        return changes

    def getChangeIdsLessThanIdNow(self, new_changeid):
        """Return a list of all extant change id's less than the given value,
        sorted by number."""
        def txn(t):
            q = self.quoteq("SELECT changeid FROM changes WHERE changeid < ?")
            t.execute(q, (new_changeid,))
            changes = [changeid for (changeid,) in t.fetchall()]
            changes.sort()
            return changes
        return self.runInteractionNow(txn)

    def removeChangeNow(self, changeid):
        """Thoroughly remove a change from the database, including all dependent
        tables"""
        def txn(t):
            for table in ('changes', 'scheduler_changes', 'sourcestamp_changes',
                          'change_files', 'change_links', 'change_properties'):
                q = self.quoteq("DELETE FROM %s WHERE changeid = ?" % table)
                t.execute(q, (changeid,))
        return self.runInteractionNow(txn)

    def getChangesByNumber(self, changeids):
        return defer.gatherResults([self.getChangeByNumber(changeid)
                                    for changeid in changeids])

    # SourceStamp-manipulating methods

    def getSourceStampNumberedNow(self, ssid, t=None):
        assert isinstance(ssid, (int, long))
        ss = self._sourcestamp_cache.get(ssid)
        if ss:
            return ss
        if t:
            ss = self._txn_getSourceStampNumbered(t, ssid)
        else:
            ss = self.runInteractionNow(self._txn_getSourceStampNumbered,
                                           ssid)
        self._sourcestamp_cache.add(ssid, ss)
        return ss

    def _txn_getSourceStampNumbered(self, t, ssid):
        assert isinstance(ssid, (int, long))
        t.execute(self.quoteq("SELECT branch,revision,patchid,project,repository"
                              " FROM sourcestamps WHERE id=?"),
                  (ssid,))
        r = t.fetchall()
        if not r:
            return None
        (branch_u, revision_u, patchid, project, repository) = r[0]
        branch = str_or_none(branch_u)
        revision = str_or_none(revision_u)

        patch = None
        if patchid is not None:
            t.execute(self.quoteq("SELECT patchlevel,patch_base64,subdir"
                                  " FROM patches WHERE id=?"),
                      (patchid,))
            r = t.fetchall()
            assert len(r) == 1
            (patch_level, patch_text_base64, subdir_u) = r[0]
            patch_text = base64.b64decode(patch_text_base64)
            if subdir_u:
                patch = (patch_level, patch_text, str(subdir_u))
            else:
                patch = (patch_level, patch_text)

        t.execute(self.quoteq("SELECT changeid FROM sourcestamp_changes"
                              " WHERE sourcestampid=?"
                              " ORDER BY changeid ASC"),
                  (ssid,))
        r = t.fetchall()
        changes = None
        if r:
            changes = [self.getChangeNumberedNow(changeid, t)
                       for (changeid,) in r]
        ss = SourceStamp(branch, revision, patch, changes, project=project, repository=repository)
        ss.ssid = ssid
        return ss

    # Properties methods

    def get_properties_from_db(self, tablename, idname, id, t=None):
        if t:
            return self._txn_get_properties_from_db(t, tablename, idname, id)
        else:
            return self.runInteractionNow(self._txn_get_properties_from_db,
                                          tablename, idname, id)

    def _txn_get_properties_from_db(self, t, tablename, idname, id):
        # apparently you can't use argument placeholders for table names. Don't
        # call this with a weird-looking tablename.
        q = self.quoteq("SELECT property_name,property_value FROM %s WHERE %s=?"
                        % (tablename, idname))
        t.execute(q, (id,))
        retval = Properties()
        for key, valuepair in t.fetchall():
            value, source = json.loads(valuepair)
            retval.setProperty(str(key), value, source)
        return retval

    # Scheduler manipulation methods

    def addSchedulers(self, added):
        raise NotImplementedError # FIXME
        for scheduler in added:
            name = scheduler.name
            assert name
            
            class_name = "%s.%s" % (scheduler.__class__.__module__,
                    scheduler.__class__.__name__)
            q = self.quoteq("""
                SELECT schedulerid, class_name FROM schedulers WHERE
                    name=? AND
                    (class_name=? OR class_name='')
                    """)
            t.execute(q, (name, class_name))
            row = t.fetchone()
            if row:
                sid, db_class_name = row
                if db_class_name == '':
                    # We're updating from an old schema where the class name
                    # wasn't stored.
                    # Update this row's class name and move on
                    q = self.quoteq("""UPDATE schedulers SET class_name=?
                        WHERE schedulerid=?""")
                    t.execute(q, (class_name, sid))
                elif db_class_name != class_name:
                    # A different scheduler is being used with this name.
                    # Ignore the old scheduler and create a new one
                    sid = None
            else:
                sid = None

            if sid is None:
                # create a new row, with the latest changeid (so it won't try
                # to process all of the old changes) new Schedulers are
                # supposed to ignore pre-existing Changes
                q = ("SELECT changeid FROM changes"
                     " ORDER BY changeid DESC LIMIT 1")
                t.execute(q)
                max_changeid = _one_or_else(t.fetchall(), 0)
                state = scheduler.get_initial_state(max_changeid)
                state_json = json.dumps(state)
                q = self.quoteq("INSERT INTO schedulers"
                                " (name, class_name, state)"
                                "  VALUES (?,?,?)")
                t.execute(q, (name, class_name, state_json))
                sid = t.lastrowid
            log.msg("scheduler '%s' got id %d" % (scheduler.name, sid))
            scheduler.schedulerid = sid

    def scheduler_get_state(self, schedulerid, t):
        q = self.quoteq("SELECT state FROM schedulers WHERE schedulerid=?")
        t.execute(q, (schedulerid,))
        state_json = _one_or_else(t.fetchall())
        assert state_json is not None
        return json.loads(state_json)

    def scheduler_set_state(self, schedulerid, t, state):
        state_json = json.dumps(state)
        q = self.quoteq("UPDATE schedulers SET state=? WHERE schedulerid=?")
        t.execute(q, (state_json, schedulerid))

    def get_sourcestampid(self, ss, t):
        """Given a SourceStamp (which may or may not have an ssid), make sure
        the contents are in the database, and return the ssid. If the
        SourceStamp originally came from the DB (and thus already has an
        ssid), just return the ssid. If not, create a new row for it."""
        if ss.ssid is not None:
            return ss.ssid
        patchid = None
        if ss.patch:
            patchlevel = ss.patch[0]
            diff = ss.patch[1]
            subdir = None
            if len(ss.patch) > 2:
                subdir = ss.patch[2]
            q = self.quoteq("INSERT INTO patches"
                            " (patchlevel, patch_base64, subdir)"
                            " VALUES (?,?,?)")
            t.execute(q, (patchlevel, base64.b64encode(diff), subdir))
            patchid = t.lastrowid
        t.execute(self.quoteq("INSERT INTO sourcestamps"
                              " (branch, revision, patchid, project, repository)"
                              " VALUES (?,?,?,?,?)"),
                  (ss.branch, ss.revision, patchid, ss.project, ss.repository))
        ss.ssid = t.lastrowid
        q2 = self.quoteq("INSERT INTO sourcestamp_changes"
                         " (sourcestampid, changeid) VALUES (?,?)")
        for c in ss.changes:
            t.execute(q2, (ss.ssid, c.number))
        return ss.ssid

    def create_buildset(self, ssid, reason, properties, builderNames, t,
                        external_idstring=None):
        # this creates both the BuildSet and the associated BuildRequests
        now = self._getCurrentTime()
        t.execute(self.quoteq("INSERT INTO buildsets"
                              " (external_idstring, reason,"
                              "  sourcestampid, submitted_at)"
                              " VALUES (?,?,?,?)"),
                  (external_idstring, reason, ssid, now))
        bsid = t.lastrowid
        for propname, propvalue in properties.properties.items():
            encoded_value = json.dumps(propvalue)
            t.execute(self.quoteq("INSERT INTO buildset_properties"
                                  " (buildsetid, property_name, property_value)"
                                  " VALUES (?,?,?)"),
                      (bsid, propname, encoded_value))
        brids = []
        for bn in builderNames:
            t.execute(self.quoteq("INSERT INTO buildrequests"
                                  " (buildsetid, buildername, submitted_at)"
                                  " VALUES (?,?,?)"),
                      (bsid, bn, now))
            brid = t.lastrowid
            brids.append(brid)
        self.notify("add-buildset", bsid)
        self.notify("add-buildrequest", *brids)
        return bsid

    def scheduler_classify_change(self, schedulerid, number, important, t):
        q = self.quoteq("INSERT INTO scheduler_changes"
                        " (schedulerid, changeid, important)"
                        " VALUES (?,?,?)")
        t.execute(q, (schedulerid, number, bool(important)))

    def scheduler_get_classified_changes(self, schedulerid, t):
        q = self.quoteq("SELECT changeid, important"
                        " FROM scheduler_changes"
                        " WHERE schedulerid=?")
        t.execute(q, (schedulerid,))
        important = []
        unimportant = []
        for (changeid, is_important) in t.fetchall():
            c = self.getChangeNumberedNow(changeid, t)
            if is_important:
                important.append(c)
            else:
                unimportant.append(c)
        return (important, unimportant)

    def scheduler_retire_changes(self, schedulerid, changeids, t):
        while changeids:
            # sqlite has a maximum of 999 parameters, but we'll try to come in far
            # short of that
            batch, changeids = changeids[:100], changeids[100:]
            t.execute(self.quoteq("DELETE FROM scheduler_changes"
                                  " WHERE schedulerid=? AND changeid IN ")
                      + self.parmlist(len(batch)),
                      (schedulerid,) + tuple(batch))

    def scheduler_subscribe_to_buildset(self, schedulerid, bsid, t):
        # scheduler_get_subscribed_buildsets(schedulerid) will return
        # information about all buildsets that were subscribed this way
        t.execute(self.quoteq("INSERT INTO scheduler_upstream_buildsets"
                              " (buildsetid, schedulerid, active)"
                              " VALUES (?,?,?)"),
                  (bsid, schedulerid, 1))

    def scheduler_get_subscribed_buildsets(self, schedulerid, t):
        # returns list of (bsid, ssid, complete, results) pairs
        t.execute(self.quoteq("SELECT bs.id, "
                              "  bs.sourcestampid, bs.complete, bs.results"
                              " FROM scheduler_upstream_buildsets AS s,"
                              "  buildsets AS bs"
                              " WHERE s.buildsetid=bs.id"
                              "  AND s.schedulerid=?"
                              "  AND s.active=1"),
                  (schedulerid,))
        return t.fetchall()

    def scheduler_unsubscribe_buildset(self, schedulerid, buildsetid, t):
        t.execute(self.quoteq("UPDATE scheduler_upstream_buildsets"
                              " SET active=0"
                              " WHERE buildsetid=? AND schedulerid=?"),
                  (buildsetid, schedulerid))

    # BuildRequest-manipulation methods

    def getBuildRequestWithNumber(self, brid, t=None):
        assert isinstance(brid, (int, long))
        if t:
            br = self._txn_getBuildRequestWithNumber(t, brid)
        else:
            br = self.runInteractionNow(self._txn_getBuildRequestWithNumber,
                                        brid)
        return br
    def _txn_getBuildRequestWithNumber(self, t, brid):
        assert isinstance(brid, (int, long))
        t.execute(self.quoteq("SELECT br.buildsetid, bs.reason,"
                              " bs.sourcestampid, br.buildername,"
                              " bs.submitted_at, br.priority"
                              " FROM buildrequests AS br, buildsets AS bs"
                              " WHERE br.id=? AND br.buildsetid=bs.id"),
                  (brid,))
        r = t.fetchall()
        if not r:
            return None
        (bsid, reason, ssid, builder_name, submitted_at, priority) = r[0]
        ss = self.getSourceStampNumberedNow(ssid, t)
        properties = self.get_properties_from_db("buildset_properties",
                                                 "buildsetid", bsid, t)
        br = BuildRequest(reason, ss, builder_name, properties)
        br.submittedAt = submitted_at
        br.priority = priority
        br.id = brid
        br.bsid = bsid
        return br

    def get_buildername_for_brid(self, brid):
        assert isinstance(brid, (int, long))
        return self.runInteractionNow(self._txn_get_buildername_for_brid, brid)
    def _txn_get_buildername_for_brid(self, t, brid):
        assert isinstance(brid, (int, long))
        t.execute(self.quoteq("SELECT buildername FROM buildrequests"
                              " WHERE id=?"),
                  (brid,))
        r = t.fetchall()
        if not r:
            return None
        return r[0][0]

    def get_unclaimed_buildrequests(self, buildername, old, master_name,
                                    master_incarnation, t, limit=None):
        q = ("SELECT br.id"
             " FROM buildrequests AS br, buildsets AS bs"
             " WHERE br.buildername=? AND br.complete=0"
             " AND br.buildsetid=bs.id"
             " AND (br.claimed_at<?"
             "      OR (br.claimed_by_name=?"
             "          AND br.claimed_by_incarnation!=?))"
             " ORDER BY br.priority DESC,bs.submitted_at ASC")
        if limit:
            q += " LIMIT %s" % limit
        t.execute(self.quoteq(q),
                (buildername, old, master_name, master_incarnation))
        requests = [self.getBuildRequestWithNumber(brid, t)
                    for (brid,) in t.fetchall()]
        return requests

    def claim_buildrequests(self, now, master_name, master_incarnation, brids,
                            t=None):
        if not brids:
            return
        if t:
            self._txn_claim_buildrequests(t, now, master_name,
                                          master_incarnation, brids)
        else:
            self.runInteractionNow(self._txn_claim_buildrequests,
                                   now, master_name, master_incarnation, brids)
    def _txn_claim_buildrequests(self, t, now, master_name, master_incarnation,
                                 brids):
        while brids:
            batch, brids = brids[:100], brids[100:]
            q = self.quoteq("UPDATE buildrequests"
                            " SET claimed_at = ?,"
                            "     claimed_by_name = ?, claimed_by_incarnation = ?"
                            " WHERE id IN " + self.parmlist(len(batch)))
            qargs = [now, master_name, master_incarnation] + list(batch)
            t.execute(q, qargs)

    def build_started(self, brid, buildnumber):
        return self.runInteractionNow(self._txn_build_started, brid, buildnumber)
    def _txn_build_started(self, t, brid, buildnumber):
        now = self._getCurrentTime()
        t.execute(self.quoteq("INSERT INTO builds (number, brid, start_time)"
                              " VALUES (?,?,?)"),
                  (buildnumber, brid, now))
        bid = t.lastrowid
        self.notify("add-build", bid)
        return bid

    def builds_finished(self, bids):
        return self.runInteractionNow(self._txn_build_finished, bids)
    def _txn_build_finished(self, t, bids):
        now = self._getCurrentTime()
        while bids:
            batch, bids = bids[:100], bids[100:]
            q = self.quoteq("UPDATE builds SET finish_time = ?"
                            " WHERE id IN " + self.parmlist(len(batch)))
            qargs = [now] + list(batch)
            t.execute(q, qargs)

    def get_build_info(self, bid):
        return self.runInteractionNow(self._txn_get_build_info, bid)
    def _txn_get_build_info(self, t, bid):
        # brid, buildername, buildnum
        t.execute(self.quoteq("SELECT b.brid,br.buildername,b.number"
                              " FROM builds AS b, buildrequests AS br"
                              " WHERE b.id=? AND b.brid=br.id"),
                  (bid,))
        res = t.fetchall()
        if res:
            return res[0]
        return (None,None,None)

    def get_buildnums_for_brid(self, brid):
        return self.runInteractionNow(self._txn_get_buildnums_for_brid, brid)
    def _txn_get_buildnums_for_brid(self, t, brid):
        t.execute(self.quoteq("SELECT number FROM builds WHERE brid=?"),
                  (brid,))
        return [number for (number,) in t.fetchall()]

    def resubmit_buildrequests(self, brids):
        return self.runInteraction(self._txn_resubmit_buildreqs, brids)
    def _txn_resubmit_buildreqs(self, t, brids):
        # the interrupted build that gets resubmitted will still have the
        # same submitted_at value, so it should be re-started first
        while brids:
            batch, brids = brids[:100], brids[100:]
            q = self.quoteq("UPDATE buildrequests"
                            " SET claimed_at=0,"
                            "     claimed_by_name=NULL, claimed_by_incarnation=NULL"
                            " WHERE id IN " + self.parmlist(len(batch)))
            t.execute(q, batch)
        self.notify("add-buildrequest", *brids)

    def retire_buildrequests(self, brids, results):
        return self.runInteractionNow(self._txn_retire_buildreqs, brids,results)
    def _txn_retire_buildreqs(self, t, brids, results):
        now = self._getCurrentTime()
        #q = self.db.quoteq("DELETE FROM buildrequests WHERE id IN "
        #                   + self.db.parmlist(len(brids)))
        while brids:
            batch, brids = brids[:100], brids[100:]

            q = self.quoteq("UPDATE buildrequests"
                            " SET complete=1, results=?, complete_at=?"
                            " WHERE id IN " + self.parmlist(len(batch)))
            t.execute(q, [results, now]+batch)
            # now, does this cause any buildsets to complete?
            q = self.quoteq("SELECT bs.id"
                            " FROM buildsets AS bs, buildrequests AS br"
                            " WHERE br.buildsetid=bs.id AND bs.complete=0"
                            "  AND br.id in "
                            + self.parmlist(len(batch)))
            t.execute(q, batch)
            bsids = [bsid for (bsid,) in t.fetchall()]
            for bsid in bsids:
                self._check_buildset(t, bsid, now)
        self.notify("retire-buildrequest", *brids)
        self.notify("modify-buildset", *bsids)

    def cancel_buildrequests(self, brids):
        return self.runInteractionNow(self._txn_cancel_buildrequest, brids)
    def _txn_cancel_buildrequest(self, t, brids):
        # TODO: we aren't entirely sure if it'd be safe to just delete the
        # buildrequest: what else might be waiting on it that would then just
        # hang forever?. _check_buildset() should handle it well (an empty
        # buildset will appear complete and SUCCESS-ful). But we haven't
        # thought it through enough to be sure. So for now, "cancel" means
        # "mark as complete and FAILURE".
        while brids:
            batch, brids = brids[:100], brids[100:]

            if True:
                now = self._getCurrentTime()
                q = self.quoteq("UPDATE buildrequests"
                                " SET complete=1, results=?, complete_at=?"
                                " WHERE id IN " + self.parmlist(len(batch)))
                t.execute(q, [FAILURE, now]+batch)
            else:
                q = self.quoteq("DELETE FROM buildrequests"
                                " WHERE id IN " + self.parmlist(len(batch)))
                t.execute(q, batch)

            # now, does this cause any buildsets to complete?
            q = self.quoteq("SELECT bs.id"
                            " FROM buildsets AS bs, buildrequests AS br"
                            " WHERE br.buildsetid=bs.id AND bs.complete=0"
                            "  AND br.id in "
                            + self.parmlist(len(batch)))
            t.execute(q, batch)
            bsids = [bsid for (bsid,) in t.fetchall()]
            for bsid in bsids:
                self._check_buildset(t, bsid, now)

        self.notify("cancel-buildrequest", *brids)
        self.notify("modify-buildset", *bsids)

    def _check_buildset(self, t, bsid, now):
        q = self.quoteq("SELECT br.complete,br.results"
                        " FROM buildsets AS bs, buildrequests AS br"
                        " WHERE bs.complete=0"
                        "  AND br.buildsetid=bs.id AND bs.id=?")
        t.execute(q, (bsid,))
        results = t.fetchall()
        is_complete = True
        bs_results = SUCCESS
        for (complete, r) in results:
            if not complete:
                # still waiting
                is_complete = False
            # mark the buildset as a failure if anything worse than
            # WARNINGS resulted from any one of the buildrequests
            if r not in (SUCCESS, WARNINGS):
                bs_results = FAILURE
        if is_complete:
            # they were all successful
            q = self.quoteq("UPDATE buildsets"
                            " SET complete=1, complete_at=?, results=?"
                            " WHERE id=?")
            t.execute(q, (now, bs_results, bsid))

    def get_buildrequestids_for_buildset(self, bsid):
        return self.runInteractionNow(self._txn_get_buildrequestids_for_buildset,
                                      bsid)
    def _txn_get_buildrequestids_for_buildset(self, t, bsid):
        t.execute(self.quoteq("SELECT buildername,id FROM buildrequests"
                              " WHERE buildsetid=?"),
                  (bsid,))
        return dict(t.fetchall())

    def examine_buildset(self, bsid):
        return self.runInteractionNow(self._txn_examine_buildset, bsid)
    def _txn_examine_buildset(self, t, bsid):
        # "finished" means complete=1 for all builds. Return False until
        # all builds are complete, then True.
        # "successful" means complete=1 and results!=FAILURE for all builds.
        # Returns None until the last success or the first failure. Returns
        # False if there is at least one failure. Returns True if all are
        # successful.
        q = self.quoteq("SELECT br.complete,br.results"
                        " FROM buildsets AS bs, buildrequests AS br"
                        " WHERE br.buildsetid=bs.id AND bs.id=?")
        t.execute(q, (bsid,))
        results = t.fetchall()
        finished = True
        successful = None
        for (c,r) in results:
            if not c:
                finished = False
            if c and r not in (SUCCESS, WARNINGS):
                successful = False
        if finished and successful is None:
            successful = True
        return (successful, finished)

    def get_active_buildset_ids(self):
        return self.runInteractionNow(self._txn_get_active_buildset_ids)
    def _txn_get_active_buildset_ids(self, t):
        t.execute("SELECT id FROM buildsets WHERE complete=0")
        return [bsid for (bsid,) in t.fetchall()]
    def get_buildset_info(self, bsid):
        return self.runInteractionNow(self._txn_get_buildset_info, bsid)
    def _txn_get_buildset_info(self, t, bsid):
        q = self.quoteq("SELECT external_idstring, reason, sourcestampid,"
                        "       complete, results"
                        " FROM buildsets WHERE id=?")
        t.execute(q, (bsid,))
        res = t.fetchall()
        if res:
            (external, reason, ssid, complete, results) = res[0]
            external_idstring = str_or_none(external)
            reason = str_or_none(reason)
            complete = bool(complete)
            return (external_idstring, reason, ssid, complete, results)
        return None # shouldn't happen

    def get_pending_brids_for_builder(self, buildername):
        return self.runInteractionNow(self._txn_get_pending_brids_for_builder,
                                      buildername)
    def _txn_get_pending_brids_for_builder(self, t, buildername):
        # "pending" means unclaimed and incomplete. When a build is returned
        # to the pool (self.resubmit_buildrequests), the claimed_at= field is
        # reset to zero.
        t.execute(self.quoteq("SELECT id FROM buildrequests"
                              " WHERE buildername=? AND"
                              "  complete=0 AND claimed_at=0"),
                  (buildername,))
        return [brid for (brid,) in t.fetchall()]

    # test/debug methods

    def has_pending_operations(self):
        return bool(self._pending_operation_count)

    def setChangeCacheSize(self, max_size):
        self._change_cache.setMaxSize(max_size)


threadable.synchronize(OERPConnector)
#eof