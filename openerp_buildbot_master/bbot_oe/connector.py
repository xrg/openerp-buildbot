# -*- encoding: utf-8 -*-

from twisted.python import log
from twisted.internet import defer, threads
from twisted.internet import reactor
from twisted.application import internet,service
from buildbot import util

from buildbot.status.builder import SUCCESS, WARNINGS, FAILURE, SKIPPED, EXCEPTION, RETRY
from buildbot.util import json, datetime2epoch, epoch2datetime
from buildbot.db import base
from buildbot.db.buildrequests import NotClaimedError, AlreadyClaimedError

from openerp_libclient import rpc

from datetime import datetime
import time
import logging

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

def dict_str2time(ddict, fields, allow_none=False):
    """In a dict, convert (inline) string datetimes to time
    """
    assert fields
    for f in fields:
        if allow_none and f not in ddict:
            continue
        ddict[f] = str2time(ddict[f])


def mid0(m2o_res):
    """ return id only of a many2one result (tuple)
    """
    if m2o_res:
        return m2o_res[0]
    else:
        return None

def dict_mid0(ddict, fields, allow_none=False):
    """ Apply mid0 to fields of dict
    """
    for f in fields:
        if allow_none and f not in ddict:
            continue
        ddict[f] = mid0(ddict[f])

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

class OERPbaseComponent(base.DBConnectorComponent):
    orm_model = None
    _logger = logging.getLogger('connector')
    
    def __init__(self, connector):
        base.DBConnectorComponent.__init__(self, connector)
        assert self.orm_model
        self._proxy = rpc.RpcProxy(self.orm_model)

    def get_props_from_db(self, ids):
        single_mode = False
        if isinstance(ids, (long, int)):
            single_mode = True
            ids = [ids,]
        res = self._proxy.getProperties(ids)
        ret = {}
        if res:
            for kdic in res:
                if kdic['id'] not in ids:
                    continue
                value, source = json.loads(kdic['value'])
                ret.setdefault(kdic['id'], {})[str(kdic['name'])] = (value, source)
        if single_mode:
            return (ret and ret.values()[0]) or {}
        return ret

class OERPChangesConnector(OERPbaseComponent):
    """ Changes connector
        
        see software_dev.commit.getChanges() for dictionaries used during I/O
    """
    orm_model = 'software_dev.commit'
    
    def addChange(self, **kwargs):
        change = kwargs
        
        def _txn_addChangeToDatabase(change):
            cdict = change.copy()
            cleanupDict(cdict)
            self._logger.debug("Add change to db: %r", change.get('comments'))
            when_dt = cdict.pop('when_timestamp', None)
            if when_dt:
                cdict['when'] = datetime2epoch(when_dt)
            else:
                cdict['when'] = False
            try:
                prop_arr = []
                extra = cdict.setdefault('extra', {})
                for pname, pvalue in cdict.pop('properties', {}).items():
                    if pname == 'branch_id':
                        extra['branch_id'] = pvalue[0]
                    elif pname in ('hash', 'authors', 'filesb'):
                        # these ones must pop from the properties into cdict, they
                        # are extended attributes of the change
                        if isinstance(pvalue[0], dict):
                            cleanupDict(pvalue[0])
                        extra[pname] = pvalue[0]
                        
                    else:
                        prop_arr.append((pname, json.dumps(pvalue)))
                cdict.pop('files', None) #if not filesb ?
                change_id = self._proxy.submit_change(cdict)
                if prop_arr:
                    self._proxy.setProperties(change_id, prop_arr)
            except Exception, e:
                log.err("Cannot add change: %s" % e)
                raise
            return change_id

        d = threads.deferToThread(_txn_addChangeToDatabase, change)
        return d

    def _get_change_num(self, changeid):
        
        if isinstance(changeid, (list, tuple)):
            cids = changeid
        else:
            cids = [changeid,]
        if not cids:
            return []
        
        if not self._proxy.exists(cids):
            return None
        
        res = self._proxy.getChanges(cids)
        
        props = self.get_props_from_db(cids)
        for cdict in res:
            for k in cdict:
                if cdict[k] is False:
                    cdict[k] = None
            extra = cdict.pop('extra', {})
            cdict['properties'] = props.get(cdict['changeid'], {})
            cdict['files'] = [ f['filename'] for f in extra.get('filesb',[])]
            cdict['is_dir'] = 0
            cdict['when_timestamp'] = epoch2datetime(cdict['when'])
            
            for k, v in extra.items():
                cdict['properties'][k] = (v, 'Change-int')

        if isinstance(changeid, (list, tuple)):
            return res
        else:
            return res[0]

    def getChange(self, changeid):
        d = threads.deferToThread(self._get_change_num, changeid)
        return d

    def _getLatestChangeNumberNow(self, branch=None):
        args = []
        if branch:
            args = [('branch_id','=', branch)]
        res = self._proxy.search(args, 0, 1, "date desc")
        if (not res) or not res[0]:
            return None
        return res[0]

    def getLatestChangeid(self):
        d = threads.deferToThread(self._getLatestChangeNumberNow)
        return d

    def getRecentChanges(self, count):
        def thd(count):
            chgs = self._proxy.search([], order='id desc', limit=count)
            return self._get_change_num(chgs)
        return threads.deferToThread(thd, count)

    def pruneChanges(self, changeHorizon):
        if not changeHorizon:
            return defer.succeed(None)
        def thd(changeHorizon):
            chgs = self._proxy.search([], order='id desc', offset=changeHorizon)
            print "will prune these changes:", chgs
            #self._proxy.unlink(chgs) # keep that disabled for now.
        return threads.deferToThread(thd)

class SourceStampsCCOE(OERPbaseComponent):
    """
    A DBConnectorComponent to handle source stamps in the database
    """
    orm_model = 'software_dev.commit'
    
    def addSourceStamp(self, branch, revision, repository, project,
                          patch_body=None, patch_level=0, patch_subdir=None,
                          changeids=[]):
        """
        Create a new SourceStamp instance with the given attributes, and return
        its sourcestamp ID, via a Deferred.
        """
        def thd():
            self._logger.debug('createSourceStamp: %s %r', branch, changeids)
            assert len(changeids) == 1, changeids
            # We don't support them:
            assert not patch_body
            assert not patch_level
            assert not patch_subdir
            return changeids[0]
            
        return threads.deferToThread(thd)

    def _getSStampNumberedNow(self, ssid, old_res=None):
        assert isinstance(ssid, (int, long))
        
        if not old_res:
            res = self._proxy.read(ssid, ['revno', 'hash', 'parent_id', 'merge_id', 'branch_id'])
            dict_mid0(res, 'parent_id', 'merge_id', 'branch_id')
        else:
            res = old_res
        if not res:
            self._logger.warning("Cannot read Change for sourcestamp: %d", ssid)
            return None

        branch = None # res['branch_url']
        revision = res.get('revno', False) or res.get('hash', '')
        
        if not revision:
            # it must be a merge "commit" that is not yet in VCS
            if not res.get('parent_id', False):
                log.msg('Commit %d without revision or parent found! Ignoring.' % ssid)
                return None
            par_res = self._proxy.read(res['parent_id'][0], ['revno','hash'])
            revision = par_res.get('revno', False) or par_res.get('hash', '')

        # patch = None
        #if patchid is not None:
        #    raise NotImplementedError

        changes = None
        
        changeid = ssid
        changes = set([changeid,])
        if res.get('merge_id', False):
            changes.add(res['merge_id'][0])

        ss = dict(ssid=ssid, branch=branch, revision=revision,
                    patch_body=None, patch_level=None, patch_subdir=None,
                    repository=str(res['branch_id']), project=None,
                    changeids=changes)
        self._logger.debug("returning sourceStamp %d", ssid)
        return ss

    def getSourceStamp(self, ssid):
        return threads.deferToThread(self._getSStampNumberedNow, ssid)

class BuildsetsCCOE(OERPbaseComponent):
    """
    A DBConnectorComponent to handle getting buildsets into and out of the
    database
    
    see BuildsetsConnectorComponent

    """
    orm_model = 'software_dev.buildset'
    
    def _add_buildset(self, ssid, reason, properties, builderNames,
                        external_idstring=None, _reactor=reactor):
        # this creates both the BuildSet and the associated BuildRequests
        now = _reactor.seconds()
        
        self._logger.debug("_add_buildset %s %r", ssid, builderNames)
        vals = { 'commit_id': ssid, 'complete': False,
                'submitted_at': time2str(now),
                }
        if external_idstring:
            vals['external_idstring'] = external_idstring
        if reason:
            vals['reason'] = reason
        bsid = self._proxy.create(vals)
        
        self._proxy.setProperties(bsid, [ (pn, json.dumps(pv))
                                for pn, pv in properties.items()]) # FIXME
        brids = {}
        if builderNames:
            brids = self._proxy.createBuildRequests(bsid, builderNames)
        
        self._logger.debug("added buildset %d, with requests: %r", bsid, brids)
        return bsid, brids

    def addBuildset(self, ssid, reason, properties, builderNames,
                   external_idstring=None):
        """
        Add a new Buildset to the database, along with the buildrequests for
        each named builder, returning the resulting bsid via a Deferred.
        Arguments should be specified by keyword.

        @returns: buildset ID via a Deferred
        """
        return threads.deferToThread(self._add_buildset, ssid, reason, properties, builderNames,
                   external_idstring)

    def subscribeToBuildset(self, schedulerid, buildsetid):
        """
        Add a row to C{scheduler_upstream_buildsets} indicating that
        C{schedulerid} is interested in buildset C{bsid}.

        @param schedulerid: downstream scheduler
        @type schedulerid: integer

        @param buildsetid: buildset id the scheduler is subscribing to
        @type buildsetid: integer

        @returns: Deferred
        """
        self.logger.warning('subscribeToBuildset')
        raise NotImplementedError

    def unsubscribeFromBuildset(self, schedulerid, buildsetid):
        """
        The opposite of L{subscribeToBuildset}, this removes the subcription
        row from the database, rather than simply marking it as inactive.

        @param schedulerid: downstream scheduler
        @type schedulerid: integer

        @param buildsetid: buildset id the scheduler is subscribing to
        @type buildsetid: integer

        @returns: Deferred
        """
        self.logger.warning('unsubscribeFromBuildset')
        raise NotImplementedError

    def getSubscribedBuildsets(self, schedulerid):
        """
        Get the set of buildsets to which this scheduler is subscribed, along
        with the buildsets' current results.  This will exclude any rows marked
        as not active.

        The return value is a list of tuples, each containing a buildset ID, a
        sourcestamp ID, a boolean indicating that the buildset is complete, and
        the buildset's result.

        @param schedulerid: downstream scheduler
        @type schedulerid: integer

        @returns: list as described, via Deferred
        """
        self.logger.warning('getSubscribedBuildsets')
        raise NotImplementedError
        
    def completeBuildset(self, bsid, results, _reactor=reactor):
        print 'completeBuildset'
        return defer.succeed(None)
    
    def _db2bset(self, res):
        """Transform an orm_model result to a buildset dict
        """
        return { 'bsid': res['id'],
                'sourcestampid': res['id'],
                'external_idstring': res['external_idstring'],
                'complete': bool(res['complete']),
                'complete_at': str2time(res['complete_at']),
                'results': res['results'],
                'reason': res['reason'],
                'submitted_at': str2time(res['submitted_at']) 
                }

    def getBuildset(self, bsid):
        """
        Get a dictionary representing the given buildset, or None
        if no such buildset exists.
        """
        def thd():
            res = self._proxy.read(bsid)
            return self._db2bset(res)

        return threads.deferToThread(thd)

    def getBuildsets(self, complete=None):
        
        def thd():
            domain = []
            if complete is not None:
                domain.append(('complete', '=', complete))
            ress = self._proxy.search_read(domain, fields=self._read_fields)
            
            self._logger.debug("Get buildsets %r: %r", complete, [ r['id'] for r in ress])
            return map(self._db2bset, ress)

        return threads.deferToThread(thd)

    def getBuildsetProperties(self, buildsetid):
        """
        Return the properties for a buildset, in the same format they were
        given to L{addBuildset}.
        """
        def thd():
            props = self.get_props_from_db(buildsetid)
            return props
        return threads.deferToThread(thd)

class BuildRequestsCCOE(OERPbaseComponent):
    orm_model = 'software_dev.buildrequest'
    qnum = 0

    def _db2br(self, res):
        """Transform an orm_model result to a buildrequest dict
        """
        return { 'brid': res['id'],
                'buildsetid': res['id'],
                'buildername': res['buildername'],
                'priority': res['priority'],
                'claimed': bool(res['claimed_at']),
                'claimed_at': str2time(res['claimed_at']),
                'mine': True,
                'complete': res['complete'],
                'results': res['results'],
                'submitted_at': str2time(res['submitted_at']) 
                }

    def getBuildRequest(self, brid):
        def thd():
            res = self._proxy.read(brid, self._read_fields)
            
            return self._commit2br(res)

        return threads.deferToThread(thd)

    def getBuildRequests(self, buildername=None, complete=None, claimed=None,
        bsid=None):
        def thd():
            domain = []
            if bsid is not None:
                domain.append(('id','=', bsid))
            if complete is not None:
                domain.append(('complete', '=', bool(complete)))
            if buildername is not None:
                domain.append(('buildername', '=', buildername))
                pass
            if claimed is True:
                domain.append(('claimed_at', '!=', False))
            elif claimed is False:
                domain.append(('claimed_at', '=', False))
                domain.append(('complete', '=', False))
            elif claimed == 'mine':
                master_name = self.db.master.master_name
                master_incarnation = self.db.master.master_incarnation
                domain.append(('claimed_at', '!=', False))
                domain.append(('claimed_by_name', '=', master_name))
                domain.append(('claimed_by_incarnation', '=', master_incarnation))
            
            # RFC order?
            self._logger.debug('Get buildrequests: %r', domain)
            res = self._proxy.search_read(domain)
            # FIXME
            return [self._commit2br(r) for r in res if (buildername is None or r['buildername'] == buildername)]
        
        return threads.deferToThread(thd)

    def claimBuildRequests(self, brids, _reactor=reactor, _race_hook=None):
        brids = list(brids)
        def thd():
            master_name = self.db.master.master_name
            master_incarnation = self.db.master.master_incarnation
            now = _reactor.seconds()
            
            #domain_aclaimed = [('id', 'in', brids),
            #    ('claimed_at', '!=', False), ('claimed_by_name', '=', master_name),
            #    ('claimed_by_incarnation', '=', master_incarnation)]
            
            if not self._proxy.claim(brids, master_name, master_incarnation, time2str(now)):
                raise AlreadyClaimedError
            else:
                return True

        return threads.deferToThread(thd)

    def unclaimBuildRequests(self, brids):
        def thd():
            master_name = self.db.master.master_name
            master_incarnation = self.db.master.master_incarnation
            
            domain = [('id', 'in', brids),
                ('complete','=', False), ('claimed_at', '!=', False),
                ('claimed_by_name', '=', master_name),
                ('claimed_by_incarnation', '=', master_incarnation)]
            
            brids2 = self._proxy.search(domain)
            
            assert brids2, "Some of %r requests are not valid to unclaim" % brids
            
            self._proxy.write(brids2, {'claimed_at': False, 
                        'claimed_by_name': False, 'claimed_by_incarnation': False })

        return threads.deferToThread(thd)

    def completeBuildRequests(self, brids, results, _reactor=reactor):
        def thd():
            master_name = self.db.master.master_name
            master_incarnation = self.db.master.master_incarnation
            now = _reactor.seconds()
            
            domain = [('id', 'in', brids), ('claimed_at', '!=', False),
                ('claimed_by_name', '=', master_name),
                ('claimed_by_incarnation', '=', master_incarnation),
                ('complete', '=', False)]
            
            brids2 = self._proxy.search(domain)
            if len(brids) != len(brids2):
                raise NotClaimedError
            self._proxy.write(brids2, {'complete': True, 'results': results,
                        'complete_at': time2str(now) })
            
        return threads.deferToThread(thd)

    def unclaimOldIncarnationRequests(self):
        def thd():
            master_name = self.db.master.master_name
            master_incarnation = self.db.master.master_incarnation
            
            domain = [ ('claimed_by_name', '=', master_name),
                    ('claimed_by_incarnation', '!=', master_incarnation),
                    ('complete', '=', False)]
            brids = self._proxy.search(domain)
            if brids:
                log.msg("unclaimed %d buildrequests for an old instance of "
                        "this master" % (len(brids),))
                self._proxy.write(brids, {'claimed_at': False, 
                        'claimed_by_name': False, 'claimed_by_incarnation': False })
            else:
                print "no brids for", domain

        print "unclaimOldIncarnationRequests"
        return threads.deferToThread(thd)

    def unclaimExpiredRequests(self, old, _reactor=reactor):
        def thd():
            old_epoch = _reactor.seconds() - old
            
            domain = [('claimed_at', '!=', False), ('claimed_at', '<', time2str(old_epoch)),
                ('complete', '=', False)]
            brids = self._proxy.search(domain)
            if brids:
                log.msg("unclaimed %d expired buildrequests (over %d seconds old)" % \
                    (len(brids), old))
                self._proxy.write(brids, {'claimed_at': False, 
                        'claimed_by_name': False, 'claimed_by_incarnation': False })
            
        return threads.deferToThread(thd)

class BuildsCCOE(OERPbaseComponent):
    """ Builds
    """
    orm_model = 'software_dev.build'
    
    def getBuild(self, bid):
        def thd():
            res = self._proxy.read(bid, ['buildrequest_id', 'build_number', 'build_start_time', 'build_finish_time' ])
            if not res:
                return None
            dict_str2time(res, ['build_start_time', 'build_finish_time'])
            res['brid'] = mid0(res.pop('buildrequest_id', None))
            return res
            
        return threads.deferToThread(thd)

    def getBuildsForRequest(self, brid):
        def thd():
            res = self._proxy.search_read(brid, [('buildrequest_id', '=', brid)],
                    fields=['buildrequest_id','build_number', 'build_start_time', 'build_finish_time' ])
            if not res:
                return None
            for r in res:
                dict_str2time(r, ['build_start_time', 'build_finish_time'])
                r['brid'] = mid0(r.pop('buildrequest_id', None))
            return res
        
        return threads.deferToThread(thd)

    def addBuild(self, brid, number, _reactor=reactor):
        def thd():
            now = _reactor.seconds()
            bid = self._proxy.create({ 'buildrequest_id': brid, 'build_number': number,
                    'build_start_time': time2str(now)} )
            return bid
        return threads.deferToThread(thd)

    def finishBuilds(self, bids, _reactor=reactor):
        def thd():
            now = _reactor.seconds()
            
            self._proxy.write(bids, {'build_finish_time': time2str(now)})
        
        return threads.deferToThread(thd)


class StateCCOE(OERPbaseComponent):
    """
    A DBConnectorComponent to handle maintaining arbitrary key/value state for
    Buildbot objects.  Objects are identified by their (user-visible) name and
    their class.  This allows e.g., a 'nightly_smoketest' object of class
    NightlyScheduler to maintain its state even if it moves between masters,
    but avoids cross-contaminating state between different classes.

    Note that the class is not interpreted literally, and can be any string
    that will uniquely identify the class for the object; if classes are
    renamed, they can continue to use the old names.
    
    taken from state.StateConnectorComponent
    """

    orm_model = 'software_dev.state_obj'

    def __init__(self, connector):
        OERPbaseComponent.__init__(self, connector)
        self._vals_proxy = rpc.RpcProxy('software_dev.state_val')
    
    def getObjectId(self, name, class_name):
        """
        Get the object ID for this combination of a name and a class.  This
        will add a row to the 'objects' table if none exists already.

        @param name: name of the object
        @param class_name: object class name
        @returns: the objectid, via a Deferred.
        """
        def thd():
            obj_id = self._proxy.search([('name','=', name), ('class_name', '=', class_name)])
            if obj_id:
                obj_id = obj_id[0]
            else:
                obj_id = self._proxy.create({'name': name, 'class_name': class_name})
            
            return obj_id
        
        return threads.deferToThread(thd)

    class Thunk: pass
    def getState(self, objectid, name, default=Thunk):
        """
        Get the state value for C{name} for the object with id C{objectid}.

        @param objectid: objectid on which the state should be checked
        @param name: name of the value to retrieve
        @param default: (optional) value to return if C{name} is not present
        @returns: state value via a Deferred
        @raises KeyError: if C{name} is not present and no default is given
        """
        def thd():
            res = self._vals_proxy.search_read([('object_id', '=', objectid), ('name', '=', name)],
                    limit=1, fields=['value'])
            if not res:
                if default is self.Thunk:
                    raise KeyError("no such state value '%s' for object %d" %
                                    (name, objectid))
                return default
            else:
                return res[0]['value']
        
        return threads.deferToThread(thd)

    def setState(self, objectid, name, value):
        """
        Set the state value for C{name} for the object with id C{objectid},
        overwriting any existing value.

        @param objectid: the objectid for which the state should be changed
        @param name: the name of the value to change
        @param value: the value to set
        @param returns: Deferred
        """
        def thd():
            old_ids = self._vals_proxy.search([('object_id', '=', objectid), ('name', '=', name)])
            if old_ids:
                assert len(old_ids) == 1
                self._vals_proxy.write(old_ids, {'value': value})
            else:
                self._vals_proxy.create({'object_id': objectid, 'name': name, 'value': value})
        
        return threads.deferToThread(thd)

class SchedulersCCOE(OERPbaseComponent):
    """
    A DBConnectorComponent to handle maintaining schedulers' state in the db.
    
    taken from schedulers.SchedulersConnectorComponent
    """
    orm_model = 'software_dev.buildscheduler'
    
    def getState(self, schedulerid):
        """Get this scheduler's state, as a dictionary.
        
        Returns a Deferred
        """
        def thd():
            res = self._proxy.read(schedulerid, ['state_dic'])
            state_json = res['state_dic']
            assert state_json is not None
            return json.loads(state_json)

        return threads.deferToThread(thd)

    def setState(self, schedulerid, state):
        """Set this scheduler's stored state, represented as a JSON-able dict.
        
        Returs a Deferred.
        Note that this will overwrite any
        existing state; be careful with updates!
        """
        
        def thd():
            state_json = json.dumps(state)
            self._proxy.write([schedulerid,], {'state_dic': state_json })
        
        return threads.deferToThread(thd)

    # TODO: maybe only the singular is needed?
    def classifyChanges(self, schedulerid, classifications):
        """Record a collection of classifications in the scheduler_changes table.
        @var classifications is a dictionary mapping CHANGEID to IMPORTANT
        (boolean).  Returns a Deferred."""
        
        def thd():
            scha_obj = rpc.RpcProxy('software_dev.sched_change')
            for number, important in classifications.items():
                scha_obj.create({'commit_id': number, 'sched_id': schedulerid, 
                        'important': bool(important) } )
        
        return threads.deferToThread(thd)

    def flushChangeClassifications(self, schedulerid, less_than=None):
        """
        Flush all scheduler_changes for L{schedulerid}, limiting to those less
        than C{less_than} if the parameter is supplied.  Returns a Deferred.
        """
        def thd():
            scha_obj = rpc.RpcProxy('software_dev.sched_change')
            domain = [('sched_id','=', schedulerid),]
            if less_than is not None:
                domain.append(('commit_id', '<', less_than))
            scha_ids = scha_obj.search(domain)
            if scha_ids:
                scha_obj.unlink(scha_ids)

        return threads.deferToThread(thd)

    class Thunk: pass
    def getChangeClassifications(self, schedulerid, branch=Thunk):
        """
        Return the scheduler_changes rows for this scheduler, in the form of a
        dictionary mapping changeid to a boolean (important).  Returns a
        Deferred.

        @param schedulerid: scheduler to look up changes for
        @type schedulerid: integer

        @param branch: limit to changes with this branch
        @type branch: string or None (for default branch)

        @returns: dictionary via Deferred
        """
        
        def thd():
            scha_obj = rpc.RpcProxy('software_dev.sched_change')
            domain = [('sched_id','=', schedulerid),]
            if branch is not self.Thunk:
                domain.append(('commit_id.branch_id.name', '=', branch))
            
            ret = {}
            scha_ids = scha_obj.search(domain)
            if not scha_ids:
                return {}
            for sch in scha_obj.read(scha_ids, ['commit_id', 'important']):
                ret[sch['commit_id'][0] ] = sch['important']
            return ret
        return threads.deferToThread(thd)

    def getSchedulerId(self, sched_name, sched_class):
        """
        Get the schedulerid for the given scheduler, creating a new schedulerid
        if none is found.
        
        @returns: schedulerid, via a Deferred
        """
        def thd():
            bsid = self._proxy.search([('name', '=', sched_name), ('class_name','=', sched_class)])
            if bsid:
                return bsid[0]
            
            change_obj = rpc.RpcProxy(OERPChangesConnector.orm_model)
            max_ids = change_obj.search([], 0, 1, 'id desc')
            # TODO: really all changes?
                
            if max_ids:
                max_changeid = max_ids[0]
            else:
                max_changeid = 0
                
            state = { 'last_processed': max_changeid }
            state_json = json.dumps(state)
            bsid = self._proxy.create( { 'name': sched_name,
                            'class_name': sched_class,
                            'state_dic': state_json } )
            return bsid
        
        d = threads.deferToThread(thd)
        return d

class OERPConnector(util.ComparableMixin, service.MultiService):
    # Period, in seconds, of the cleanup task.  This master will perform
    # periodic cleanup actions on this schedule.
    CLEANUP_PERIOD = 3600
    
    def __init__(self, master, spec, basedir):
        service.MultiService.__init__(self)
        # self._query_times = collections.deque()
        self.master = master
        self._spec = spec
        self._basedir = basedir # is it ever needed to us?

        # set up components
        self.model = OERPModel(self)
        self.changes = OERPChangesConnector(self)
        self.schedulers = SchedulersCCOE(self)
        self.sourcestamps = SourceStampsCCOE(self)
        self.buildsets = BuildsetsCCOE(self)
        self.state = StateCCOE(self)
        self.buildrequests = BuildRequestsCCOE(self)
        self.builds = BuildsCCOE(self)

        self.cleanup_timer = internet.TimerService(self.CLEANUP_PERIOD, self.doCleanup)
        self.cleanup_timer.setServiceParent(self)

        self.changeHorizon = None # default value; set by master

    def doCleanup(self):
        """
        Perform any periodic database cleanup tasks.

        @returns: Deferred
        """
        d = self.changes.pruneChanges(self.changeHorizon)
        d.addErrback(log.err, 'while pruning changes')
        self.master.botmaster.maybeStartBuildsForAllBuilders()
        return d

    def saveTResults(self, build_id, name, build_result, t_results):
        # bld_obj = rpc.RpcProxy('software_dev.commit')
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

    # TODO must go to results obj.
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
                # return {'trigger': bres[0]['buildername']} # won't work, TODO
                return True

        except rpc.RpcException, e:
            log.err("Cannot place merge request: %s" % e)
            return False
        return None

#eof
