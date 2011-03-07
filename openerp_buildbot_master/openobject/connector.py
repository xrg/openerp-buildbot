# -*- encoding: utf-8 -*-

from twisted.python import log, threadable
from twisted.internet import defer, threads
from buildbot import util

from buildbot.util import collections as bbcollections
# from buildbot.changes.changes import Change
from poller import OpenObjectChange
from buildbot.sourcestamp import SourceStamp
from buildbot.buildrequest import BuildRequest
from buildbot.process.properties import Properties
from buildbot.status.builder import SUCCESS, WARNINGS, FAILURE, SKIPPED, EXCEPTION, RETRY
from buildbot.util.eventual import eventually
from buildbot.util import json
from buildbot.db import base

import rpc

from datetime import datetime
import time

def str2time(ddate):
    if isinstance(ddate, basestring):
        dt = ddate.rsplit('.',1)[0]
        tdate = time.mktime(time.strptime(dt, '%Y-%m-%d %H:%M:%S'))
    elif not ddate:
        tdate = 0
    else:
        tdate = time.mktime(ddate)
    return tdate
    
def time2str(ddate):
    tdate = datetime.fromtimestamp(ddate)
    return tdate.strftime('%Y-%m-%d %H:%M:%S')

class Token: # used for _start_operation/_end_operation
    pass

# Map from buildbot.status.builder states to 
res_state = { SUCCESS: 'pass', WARNINGS: 'warning', FAILURE: 'fail', \
            SKIPPED: 'skip', EXCEPTION: 'exception', RETRY: 'retry' }

def cleanupDict(cdict):
    for key in cdict:
        if cdict[key] is None:
            cdict[key] = False
        elif isinstance(cdict[key], dict):
            cleanupDict(cdict[key])

class OERPModel(base.DBConnectorComponent):
    def is_current(self):
        # always current
        return defer.succeed(True)

    def upgrade(self):
        return None

class OERPChangesConnector(base.DBConnectorComponent):
    def addChange(self, **kwargs):
        change = OpenObjectChange(**kwargs)
        d = threads.deferToThread(self.db.addChangeToDatabase, change)
        d.addCallback(lambda _ : change)
        return d

    def getChangeInstance(self, changeid):
        d = threads.deferToThread(self.db.getChangeNumberedNow,changeid)
        return d

    def getLatestChangeid(self):
        d = threads.deferToThread(self.db.getLatestChangeNumberNow)
        return d

    def changeEventGenerator(self, branches=[], categories=[], committers=[], minTime=0):
        change_obj = rpc.RpcProxy('software_dev.commit')
        domain = []

        if branches:
            domain.append( ('branch_id', 'in', branches) )
        # if categories: Not Implemented yet
        #    domain.append( ('category_id', 'in', categories) )

        if committers:
            domain.append( ('comitter_id', 'in', committers ) )
            
        if minTime:
            domain.append(('date', '>', time2str(minTime)))

        rows = change_obj.search(domain, 0, 300, 'id desc')

        while rows:
            rpart = rows[:100]
            rows = rows[100:]
            changes = self.db.runInteractionNow(self.db._get_change_num, rpart)
            print "changeEventGenerator: %d changes" % len(changes)
            for chg in changes:
                yield chg

class OERPConnector(util.ComparableMixin):
    # this will refuse to create the database: use 'create-master' for that
    compare_attrs = ["args", "kwargs"]
    synchronized = ["notify", "_end_operation"]

    def __init__(self, spec, basedir):
        # self._query_times = collections.deque()
        self._spec = spec
        self._basedir = basedir # is it ever needed to us?

        # this is for synchronous calls: runQueryNow, runInteractionNow
        self._nonpool = None
        self._nonpool_lastused = None
        
        self._change_cache = util.LRUCache(max_size=500)
        self._sourcestamp_cache = util.LRUCache(max_size=500)
        self._active_operations = set() # protected by synchronized=
        self._pending_notifications = []
        self._subscribers = bbcollections.defaultdict(set)

        self._pending_operation_count = 0

        self._started = False
        self.model = OERPModel(self)
        self.changes = OERPChangesConnector(self)
        self._unclaimed_brs_stamp = None
        self._unclaimed_brs = []    # cache for get_unclaimed_buildrequests

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

    def runInteraction(self, interaction, *args, **kwargs):
        assert self._started
        self._pending_operation_count += 1
        start = self._getCurrentTime()
        t = self._start_operation()
        
        d = threads.deferToThread(self._runInteraction,
                                    interaction, *args, **kwargs)
        d.addBoth(self._runInteraction_done, start, t)
        return d

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

    def runInteractionNow(self, interaction, *args, **kwargs):
        # synchronous+blocking version of runInteraction()
        assert self._started
        t = self._start_operation()
        try:
            return self._runInteraction(interaction, *args, **kwargs)
        finally:
            self._end_operation(t)

    def notify(self, category, *args):
        # this is wrapped by synchronized= and threadable.synchronous(),
        # since it will be invoked from runInteraction threads
        self._pending_notifications.append( (category,args) )

    def send_notification(self, category, args):
        # in the distributed system, this will be invoked by lineReceived()
        for observer in self._subscribers[category]:
            eventually(observer, category, *args)

    def subscribe_to(self, category, observer):
        self._subscribers[category].add(observer)

    def _runInteraction(self, interaction, *args, **kwargs):
        trans = Token()
        result = interaction(trans, *args, **kwargs)
        return result

    def _runInteraction_done(self, res, start, t):
        self._end_operation(t)
        self._pending_operation_count -= 1
        return res

    # ChangeManager methods

    def addChangeToDatabase(self, change):
        # TODO: cleanup, perhaps move to OERPChangesConnector
        self.runInteractionNow(self._txn_addChangeToDatabase, change)
        self._change_cache.add(change.number, change)

    def _txn_addChangeToDatabase(self, t, change):
        change_obj = rpc.RpcProxy('software_dev.commit')
        cdict = change.asDict()
        cleanupDict(cdict)
        for f in cdict['files']:
            cleanupDict(f)
        try:
            change.number = change_obj.submit_change(cdict)
            prop_arr = []
            for propname,propvalue in change.properties.properties.items():
                prop_arr.append((propname, json.dumps(propvalue)))
            if prop_arr:
                change_obj.setProperties(change.number, prop_arr)

            self._unclaimed_brs_stamp = None # trigger a refresh
            self.notify("add-change", change.number)
        except Exception, e:
            log.err("Cannot add change: %s" % e)

    def getLatestChangeNumberNow(self, branch=None, t=None):
        change_obj = rpc.RpcProxy('software_dev.commit')
        args = []
        if branch:
            args = [('branch_id','=', branch)]
        res = change_obj.search(args, 0, 1, "date desc")
        if (not res) or not res[0]:
            return None
        return res[0]

    def getChangeNumberedNow(self, changeid, t=None):
        # this is a synchronous/blocking version of getChangeByNumber
        assert changeid >= 0
        c = self._change_cache.get(changeid)
        if c:
            return c
        
        return self.runInteractionNow(self._get_change_num, changeid)

    def getChangeByNumber(self, changeid):
        # return a Deferred that fires with a Change instance, or None if
        # there is no Change with that number
        assert changeid >= 0
        c = self._change_cache.get(changeid)
        if c:
            return defer.succeed(c)
        
        return self.runInteraction(self._get_change_num, changeid)

    def _get_change_num(self, trans, changeid):
        change_obj = rpc.RpcProxy('software_dev.commit')
        if isinstance(changeid, (list, tuple)):
            cids = changeid
        else:
            cids = [changeid,]
        if not cids:
            return []
        
        ret = []
        tmp_cids = []
        for id in cids:
            c = self._change_cache.get(id)
            if c:
                ret.append(c)
            else:
                tmp_cids.append(id)
        # print "Found %d of %d changes in cache, %d remaining" % (len(ret), len(cids), len(tmp_cids))

        cids = tmp_cids
        res = change_obj.getChanges(cids)
        
        props = self.get_properties_from_db(change_obj, cids)
        for cdict in res:
            for k in cdict:
                if cdict[k] is False:
                    cdict[k] = None
            c = OpenObjectChange(**cdict)

            p = props.get(cdict['id'], Properties())
            c.properties.updateFromProperties(p)
            
            self._change_cache.add(cdict['id'], c)
            ret.append(c)
        if isinstance(changeid, (list, tuple)):
            return ret
        else:
            return ret[0]

    def getChangesGreaterThan(self, last_changeid, t=None):
        """Return a Deferred that fires with a list of all Change instances
        with numbers greater than the given value, sorted by number. This is
        useful for catching up with everything that's happened since you last
        called this function."""
        assert last_changeid >= 0
        
        change_obj = rpc.RpcProxy('software_dev.commit')
        cids = change_obj.search([('id', '>', last_changeid)])
        # FIXME: defer
        changes = self.runInteractionNow(self._get_change_num, cids)
        changes.sort(key=lambda c: c.number)
        return changes

    def getChangeIdsLessThanIdNow(self, new_changeid):
        """Return a list of all extant change id's less than the given value,
        sorted by number."""
        change_obj = rpc.RpcProxy('software_dev.commit')
        cids = change_obj.search([('id', '<', new_changeid)])
        t = Token()
        changes = self.runInteractionNow(self._get_change_num, cids)
        changes.sort(key=lambda c: c.number)
        return changes

    def removeChangeNow(self, changeid):
        """Thoroughly remove a change from the database, including all dependent
        tables"""
        change_obj = rpc.RpcProxy('software_dev.commit')
        change_obj.unlink([changeid,])
        return None

    def getChangesByNumber(self, changeids):
        return defer.gatherResults( self.runInteraction(
                                        self._get_change_num, changeids))

    # SourceStamp-manipulating methods

    def getSourceStampNumberedNow(self, ssid, t=None, old_res=None):
        assert isinstance(ssid, (int, long))
        ss = self._sourcestamp_cache.get(ssid)
        if ss:
            return ss
        
        assert isinstance(ssid, (int, long))
        sstamp_obj = rpc.RpcProxy('software_dev.commit')
        
        if not old_res:
            res = sstamp_obj.read(ssid)
        else:
            res = old_res
        if not res:
            return None

        branch = None # res['branch_url']
        revision = res.get('revno', False) or res.get('hash', '')
        
        if not revision:
            # it must be a merge "commit" that is not yet in VCS
            if not res.get('parent_id', False):
                log.msg('Commit %d without revision or parent found! Ignoring.' % ssid)
                return None
            par_res = sstamp_obj.read(res['parent_id'][0])
            revision = par_res.get('revno', False) or par_res.get('hash', '')

        patch = None
        #if patchid is not None:
        #    raise NotImplementedError

        changes = None
        
        changeid = ssid
        changes = [self.getChangeNumberedNow(changeid, t), ]
        if res.get('merge_id', False):
            changes.insert(0, self.getChangeNumberedNow(res['merge_id'][0], t))
        ss = SourceStamp(branch, revision, patch, changes )
            # project=project, repository=repository)
        ss.ssid = ssid
        self._sourcestamp_cache.add(ssid, ss)
        return ss

    def saveCommit(self, change):
        """ Save revision from Change object back into db
        
            Used after a merge happening in buildslave
        """
        assert change.revision and change.number
        commit_obj = rpc.RpcProxy('software_dev.commit')
        vals = { 'revno': change.revision }
        if change.hash:
            vals['hash'] = change.hash
        commit_obj.write([change.number], vals)

    # Properties methods

    def get_properties_from_db(self, rpc_obj, ids, t=None):
        
        single_mode = False
        if isinstance(ids, (long, int)):
            single_mode = True
            ids = [ids,]
        res = rpc_obj.getProperties(ids)
        ret = {}
        if res:
            for kdic in res:
                if kdic['id'] not in ids:
                    continue
                value, source = json.loads(kdic['value'])
                ret.setdefault(kdic['id'], Properties()).\
                        setProperty(str(kdic['name']), value, source)
        if single_mode:
            return (ret and ret.values()[0]) or Properties()
        return ret

    # Scheduler manipulation methods

    def addSchedulers(self, added):
        sched_obj = rpc.RpcProxy('software_dev.buildscheduler')
        change_obj = rpc.RpcProxy('software_dev.commit')
        for scheduler in added:
            name = scheduler.name
            assert name
            
            
            class_name = "%s.%s" % (scheduler.__class__.__module__,
                    scheduler.__class__.__name__)
            
            sids = sched_obj.search([('name', '=', name), ('class_name','=', class_name)])
            if sids:
                sid = sids[0]
            else:
                sid = None

            if sid is None:
                # create a new row, with the latest changeid (so it won't try
                # to process all of the old changes) new Schedulers are
                # supposed to ignore pre-existing Changes
                max_ids = change_obj.search([], 0, 1, 'id desc')
                # TODO: really all changes?
                
                if max_ids:
                    max_changeid = max_ids[0]
                else:
                    max_changeid = 0
                state = scheduler.get_initial_state(max_changeid)
                state_json = json.dumps(state)
                sid = sched_obj.create( { 'name': name,
                                'class_name': class_name,
                                'state_dic': state_json } )

            log.msg("scheduler '%s' got id %d" % (scheduler.name, sid))
            scheduler.schedulerid = sid

    def scheduler_get_state(self, schedulerid, t):
        sched_obj = rpc.RpcProxy('software_dev.buildscheduler')
        res = sched_obj.read(schedulerid, ['state_dic'])
        state_json = res['state_dic']
        assert state_json is not None
        return json.loads(state_json)

    def scheduler_set_state(self, schedulerid, t, state):
        sched_obj = rpc.RpcProxy('software_dev.buildscheduler')
        state_json = json.dumps(state)
        sched_obj.write([schedulerid,], {'state_dic': state_json })

    def get_sourcestampid(self, ss, t):
        """Given a SourceStamp (which may or may not have an ssid), make sure
        the contents are in the database, and return the ssid. If the
        SourceStamp originally came from the DB (and thus already has an
        ssid), just return the ssid. If not, create a new row for it."""
        if ss.ssid is not None:
            return ss.ssid
        patchid = None
        # the sourcestamp is crippled to equal the change
        ss.ssid = ss.changes[0].number
        return ss.ssid

    def create_buildset(self, ssid, reason, properties, builderNames, t,
                        external_idstring=None):
        # this creates both the BuildSet and the associated BuildRequests
        now = self._getCurrentTime()
        bset_obj = rpc.RpcProxy('software_dev.commit')
        
        vals = { # sourcestamp:
                'submitted_at': time2str(now),
                }
        if external_idstring:
            vals['external_idstring'] = external_idstring
        if reason:
            vals['reason'] = reason
        bsid = ssid  # buildset == sourcestamp == change
        bset_obj.write(bsid, vals)
        for propname, propvalue in properties.properties.items():
            bset_obj.setProperties(bsid, [ (pn, json.dumps(pv))
                                    for pn, pv in properties.properties.items()])
        # TODO: respect builderNames
        brids = []
        brid = ssid     # buildrequest == sourcestamp
        brids.append(brid)
        self.notify("add-buildset", bsid)
        self.notify("add-buildrequest", *brids)
        return bsid

    def scheduler_classify_change(self, schedulerid, number, important, t):
        scha_obj = rpc.RpcProxy('software_dev.sched_change')
        # print "Classify change %s at %s as important=%s" %( number, schedulerid, important)
        scha_obj.create({'commit_id': number, 'sched_id': schedulerid, 'important': important})

    def scheduler_get_classified_changes(self, schedulerid, t):
        scha_obj = rpc.RpcProxy('software_dev.sched_change')
        
        # one time for important ones
        sids = scha_obj.search([('sched_id','=', schedulerid), ('important','=',True)])
        res = scha_obj.read(sids, ['commit_id'])
        
        important = self._get_change_num(Token(), [ r['commit_id'][0] for r in res])

        # And one more time for unimportant ones
        sids = scha_obj.search([('sched_id','=', schedulerid), ('important','=', False)])
        res = scha_obj.read(sids, ['commit_id'])
        unimportant = self._get_change_num(Token(), [ r['commit_id'][0] for r in res])
        
        return (important, unimportant)

    def scheduler_retire_changes(self, schedulerid, changeids, t):
        scha_obj = rpc.RpcProxy('software_dev.sched_change')
        
        # one time for important ones
        sids = scha_obj.search([('sched_id','=', schedulerid), 
                        ('commit_id','in',changeids)])
        res = scha_obj.unlink(sids)

    def scheduler_subscribe_to_buildset(self, schedulerid, bsid, t):
        # scheduler_get_subscribed_buildsets(schedulerid) will return
        # information about all buildsets that were subscribed this way
        raise NotImplementedError
        t.execute(self.quoteq("INSERT INTO scheduler_upstream_buildsets"
                              " (buildsetid, schedulerid, active)"
                              " VALUES (?,?,?)"),
                  (bsid, schedulerid, 1))

    def scheduler_get_subscribed_buildsets(self, schedulerid, t):
        print "Get subscribed buildsets"
        raise NotImplementedError
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
        print "Unsubscribe buildset"
        raise NotImplementedError
        t.execute(self.quoteq("UPDATE scheduler_upstream_buildsets"
                              " SET active=0"
                              " WHERE buildsetid=? AND schedulerid=?"),
                  (buildsetid, schedulerid))

    # BuildRequest-manipulation methods

    def getBuildRequestWithNumber(self, brid, t=None):
        assert isinstance(brid, (int, long))
        
        breq_obj = rpc.RpcProxy('software_dev.commit')
        res = breq_obj.read(brid)
        
        if not res:
            return None
        ssid = brid # short-wire
        ss = self.getSourceStampNumberedNow(ssid, t, res)
        properties = self.get_properties_from_db(breq_obj, brid, t)
        bsid = brid
        br = BuildRequest(res['reason'], ss, res['buildername'], properties)
        br.submittedAt = str2time(res['submitted_at'])
        br.priority = res['priority']
        br.id = brid
        br.bsid = bsid
        return br

    def get_buildername_for_brid(self, brid):
        breq_obj = rpc.RpcProxy('software_dev.commit')
        
        res = breq_obj.read(brid, ['buildername'])
        if not res:
            return None
        return res['buildername']

    def get_unclaimed_buildrequests(self, buildername, old, master_name,
                                    master_incarnation, t, limit=None):
        breq_obj = rpc.RpcProxy('software_dev.commit')
        
        old = int(round(old-1)) # 10 sec resolution

        if (old, master_name, master_incarnation) != self._unclaimed_brs_stamp:
            #our cache is out of date, refresh it!
            self._unclaimed_brs_stamp = (old, master_name, master_incarnation)
            self._unclaimed_brs = {}

            # Read unclaimed buildrequests for *all* buildernames at one go
            domain = [ ('complete', '=', False),
                            '|', '|' , ('claimed_at','=', False), ('claimed_at', '<', time2str(old)),
                            '&', ('claimed_by_name', '=', master_name),
                            ('claimed_by_incarnation', '!=', master_incarnation)]
            tmp_bids = breq_obj.search(domain, 0, False, 'priority DESC, submitted_at')
            
            while tmp_bids:
                bids_res = breq_obj.read(tmp_bids[:200], ['buildername'])
                tmp_bids = tmp_bids[200:]
                for br in bids_res:
                    self._unclaimed_brs.setdefault(br['buildername'],[]).append(br['id'])
            
        # in buildbot v2.5 we cannot have a buildrequest that is not a commit,
        # so we hack around that and create pseydo-requests for all merge records
        if buildername and buildername not in self._unclaimed_brs:
            # The queue for this is empty. Let's see if we have any pending merges
            # to do.
            mreq_obj = rpc.RpcProxy('software_dev.mergerequest')
            self._unclaimed_brs[buildername] = mreq_obj.prepare_commits(buildername)
            # even if prepare_commits returns [], we will mark the buildername in
            # the dict, causing this step to skip while this cache is in effect.

        bids = self._unclaimed_brs.get(buildername, [])

        log.msg("Get %d unclaimed buildrequests for %s after %s" % \
                    (len(bids), buildername, time2str(old)))
        requests = [self.getBuildRequestWithNumber(bid, t)
                    for bid in bids]
        
        return requests

    def claim_buildrequests(self, now, master_name, master_incarnation, brids,
                            t=None):
        if not brids:
            return
        breq_obj = rpc.RpcProxy('software_dev.commit')
        
        vals = { 'claimed_at': time2str(now),
                'claimed_by_name': master_name,
                'claimed_by_incarnation': master_incarnation,
                }
        breq_obj.write(list(brids), vals)

    def build_started(self, brid, buildnumber):
        return self.runInteractionNow(self._txn_build_started, brid, buildnumber)

    def _txn_build_started(self, t, brid, buildnumber):
        now = self._getCurrentTime()
        build_obj = rpc.RpcProxy('software_dev.commit')
        vals = { 'build_number': buildnumber, 'build_start_time': time2str(now) }
        build_obj.write(brid, vals)
        bid = brid  # one table is used for everything
        self.notify("add-build", bid)
        return bid

    def builds_finished(self, bids):
        return self.runInteractionNow(self._txn_build_finished, bids)
    def _txn_build_finished(self, t, bids):
        now = self._getCurrentTime()
        build_obj = rpc.RpcProxy('software_dev.commit')
        vals = { 'build_finish_time': time2str(now) }
        build_obj.write(list(bids), vals)

    def get_build_info(self, bid):
        # brid, buildername, buildnum
        build_obj = rpc.RpcProxy('software_dev.commit')
        res = build_obj.read(bid, ['buildername', 'build_number' ])
        if res:
            return (res['id'], res['buildername'], res['build_number'])
        return (None,None,None)

    def get_buildnums_for_brid(self, brid):
        build_obj = rpc.RpcProxy('software_dev.commit')
        # remember: buildrequest == build in our schema
        res = build_obj.read(brid, ['build_number' ])
        return [res['build_number'],]

    def resubmit_buildrequests(self, brids):
        return self.runInteraction(self._txn_resubmit_buildreqs, brids)

    def _txn_resubmit_buildreqs(self, t, brids):
        # the interrupted build that gets resubmitted will still have the
        # same submitted_at value, so it should be re-started first
        breq_obj = rpc.RpcProxy('software_dev.commit')
        # remember: buildrequest == build in our schema
        vals = { 'claimed_at': False, 'claimed_by_name': False,
                'claimed_by_incarnation': False }
        breq_obj.write(list(brids), vals)
        self.notify("add-buildrequest", *brids)

    def retire_buildrequests(self, brids, results):
        return self.runInteractionNow(self._txn_retire_buildreqs, brids,results)

    def _txn_retire_buildreqs(self, t, brids, results):
        now = self._getCurrentTime()
        breq_obj = rpc.RpcProxy('software_dev.commit')
        # remember: buildrequest == build in our schema
        vals = { 'complete': 1, 'results': results,
                'complete_at': time2str(now) }
        breq_obj.write(brids, vals)
        
        if True:
            # now, does this cause any buildsets to complete?
            # - Yes, since buildset == buildrequests (still)
            
            bsids = brids
            
            t = None
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
        now = self._getCurrentTime()
        breq_obj = rpc.RpcProxy('software_dev.commit')
        vals = { 'complete': True, 'results': FAILURE,
                'complete_at': time2str(now) }
        breq_obj.write(brids, vals)
        # now, does this cause any buildsets to complete?
        
        bsids = brids
        for bsid in bsids:
             self._check_buildset(t, bsid, now)

        self.notify("cancel-buildrequest", *brids)
        self.notify("modify-buildset", *bsids)
        
    def saveTResults(self, build_id, name, build_result, t_results):
        bld_obj = rpc.RpcProxy('software_dev.commit')
        tsum_obj = rpc.RpcProxy('software_dev.test_result')
        
        for seq, tr in enumerate(t_results):
            vals = { 'build_id': build_id,
                'name': name,
                'substep': '.'.join(tr.name), # it is a tuple in TestResult
                'state': res_state.get(tr.results,'unknown'),
                'sequence': seq,
                'blame_log': tr.text, }
                
            tsum_obj.create(vals)
         
        return

    def saveStatResults(self, changes, file_stats):
        """ Try to save file_stats inside the filechanges of commits
        
        @param changes is the list of changes (as in allChanges() )
        @param file_stats is a dict of { fname:, { lines_add:,  lines_rem: }}
        """

        # commit_obj = rpc.RpcProxy('software_dev.commit')
        fchange_obj = rpc.RpcProxy('software_dev.filechange')
        
        commit_ids = []
        for chg in changes:
            if not chg.number:
                continue
            commit_ids.append(chg.number)
        
        while len(commit_ids) and len(file_stats):
            cid = commit_ids.pop() # so, we attribute the stats to the
                                   # last commit that matches their files
            fc_ids = fchange_obj.search([('commit_id','=', cid)])
            fcres = fchange_obj.read(fc_ids, ['filename'])
            # We read all the filenames that belong to the commit and
            # then try to see if we have any stats for them.
            if not fcres:
                continue
            for fcd in fcres:
                fcstat = file_stats.pop(fcd['filename'], False)
                if not fcstat:
                    continue
                # now, we have a filechange.id and stats
                fchange_obj.write(fcd['id'], fcstat)

    def saveCStats(self, cid, cstats):
        """ Try to save commit stats of change(s)
        
        @param cstats is list of tuples of ( change_id:, { lines_add:,  lines_rem:, ... })
        """
        commit_obj = rpc.RpcProxy('software_dev.commit')
        try:
            commit_obj.saveCStats(cid, cstats)
        except rpc.RpcException, e:
            log.err("Cannot save commit stats: %s" % e)
            return False
        return True

    def _check_buildset(self, t, bsid, now):
        # Since there is no difference from buildset->buildrequest, 
        # nothing to do.
        return True

    def get_buildrequestids_for_buildset(self, bsid):
        raise NotImplementedError
        return self.runInteractionNow(self._txn_get_buildrequestids_for_buildset,
                                      bsid)
    def _txn_get_buildrequestids_for_buildset(self, t, bsid):
        t.execute(self.quoteq("SELECT buildername,id FROM buildrequests"
                              " WHERE buildsetid=?"),
                  (bsid,))
        return dict(t.fetchall())

    def examine_buildset(self, bsid):
        print "examine buildset"
        return True

    def get_active_buildset_ids(self):
        bset_obj = rpc.RpcProxy('software_dev.commit')
        bsids = bset_obj.search([('complete', '=', False)])
        return list(bsids)

    def get_buildset_info(self, bsid):
        bset_obj = rpc.RpcProxy('software_dev.commit')
        res = bset_obj.read(bsid, ['external_idstring', 'reason', 'complete', 'results'])
        if res:
            external_idstring = res['external_idstring'] or None
            reason = res['reason'] or None
            complete = bool(res['complete'])
            return (external_idstring, reason, bsid, complete, res['results'])
        return None # shouldn't happen

    def get_pending_brids_for_builder(self, buildername):
        breq_obj = rpc.RpcProxy('software_dev.commit')
        bids = breq_obj.search([('buildername', '=',  buildername), 
                        ('complete', '=', False), ('claimed_at', '=', False)])
        
        return list(bids)

    # test/debug methods

    def has_pending_operations(self):
        return bool(self._pending_operation_count)

    def setChangeCacheSize(self, max_size):
        self._change_cache.setMaxSize(max_size)

    # Other functions
    def requestMerge(self, commit, target, target_path):
        """ Request a merge of commit into target branch
        
        @param commit commit number
        @param target name of target branch
        @param target_path one of 'server', 'addons' etc.
        """
        branch_obj = rpc.RpcProxy('software_dev.buildseries')
        try:
            branch_ids = branch_obj.search([('name','=', target), ('target_path','=', target_path)])
            if not branch_ids:
                log.err('No branch for %s/%s found! Will not place merge!' % (target_path, target))
                return False
            # if we have several similar names, the first by buildseries.order wins
            mr_obj = rpc.RpcProxy('software_dev.mergerequest')
            mr_obj.create({'commit_id': commit, 'branch_id': branch_ids[0]})
            
            # Find the corresponding scheduler of branch_id to trigger it
            bres =  branch_obj.read(branch_ids[:1], ['buildername'])
            if bres:
                return {'trigger': bres[0]['buildername']}

        except rpc.RpcException, e:
            log.err("Cannot place merge request: %s" % e)
            return False
        return None

threadable.synchronize(OERPConnector)
#eof
