# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
#    Copyright (C) 2011 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

# from tools.translate import _
from osv import fields, osv
from properties import propertyMix, bbot_results
import time
from tools.func import virtual

class software_group(osv.osv):
    _name = 'software_dev.buildgroup'
    _description = 'Software Build Group'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'public': fields.boolean('Public', required=True,
                help="If true, the results will be at the main page"),
        'sequence': fields.integer('Sequence', required=True),
    }

    _defaults = {
        'public': True,
        'sequence': 10,
    }
software_group()

class software_test(osv.osv):
    """A scenario that has to be tested on some package
    """
    _name = 'software_dev.test'
    _description = 'Software test'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'predef_test': fields.char('Fixed test', size=64,
                help="A special name which causes a predefined test"),
        'step_ids':  fields.one2many('software_dev.teststep', 'test_id', 'Steps'),
    }

    _defaults = {
    }
    
software_test()

class software_teststep(osv.osv):
    """A scenario that has to be tested on some package
    """
    _name = 'software_dev.teststep'
    _description = 'Software Test Step'
    _order = "sequence, id"
    _columns = {
        'test_id': fields.many2one('software_dev.test', 'Test', 
                required=True, on_delete="cascade", select=1),
        'sequence': fields.integer('Sequence', required=True),
        'name': fields.char('Name', required=True, size=64),
        'attribute_ids': fields.one2many('software_dev.tsattr', 'tstep_id', 'Attributes'),
    }

    _defaults = {
    }
    
software_teststep()

class software_tsattr(osv.osv):
    """ Test step attribute
    
        Raw name-value pairs for the test step
    """
    _name = 'software_dev.tsattr'
    _columns = {
        'tstep_id': fields.many2one('software_dev.teststep', 'Test Step', required=True, select=1, ondelete="cascade"),
        'name': fields.char('Name', size=64, required=True),
        'value': fields.char('Value', size=256),
        }

software_tsattr()

class software_buildseries(propertyMix, osv.osv):
    """ A series is a setup of package+test scenaria
    
        This is equivalent to the 'builder' entity of buildbot.
    """
    _name = 'software_dev.buildseries'
    _description = 'Build Series'
    def _get_buildername(self, cr, uid, ids, name, args, context=None):
        """ A builder name is a unique str of something being built at the bbot
        """
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            comps = []
            if b.group_id:
                comps.append(b.group_id.name)
            if b.builder_id:
                comps.append(b.builder_id.tech_code)
            comps.append(b.name)
            res[b.id] = '-'.join(comps)
        return res
        
    def _search_buildername(self, cr, uid, obj, name, args, context=None):
        """ Reverse search the buildername
        """
        #make sure the API behaves
        assert name == 'buildername', name
        assert len(args) == 1, args
        
        # We cannot do that directly in SQL, because we need to compose the
        # name again and check (won't fit today's domain syntax), so we try
        # to locate the closest set (superset) of the series we want, and
        # then narrow it down in the second step
        
        def _fmt_expr(bname):
            """ consider the case of a buildername like:
                
                    a-b-c-d-e
                
                This could be one of:
                
                    (group, builder, series) = (False, False, 'a-b-c-d-e')
                    (group, builder, series) = (False, 'a-b', 'c-d-e')
                    (group, builder, series) = ('a', 'b', 'c-d-e')
                    (group, builder, series) = ('a-b', 'c-d', 'e')
                    
                So, we can tell just 2 things:
                
                    - group, if set, starts with 'a'
                    - series ends with 'e'
                    
                Hopefully, a buildername like 'a-b-c', or better 'b-c' will
                closely match 'c' and perhaps 'a'
            """
            bparts = bname.split('-')
            
            domain = []
            if len(bparts) > 1:
                domain += ['|', ('group_id', '=', False), 
                    ('group_id', 'in', [('name', '=like', bparts[0]+'%')])]
            else:
                domain += [('group_id', '=', False),]
            domain += [('name','=like', '%' + bparts[-1])]
            
            return domain
            
        matches = []
        if args[0][1] == '=':
            for res in self.search_read(cr, uid, _fmt_expr(args[0][2]), fields=['buildername'], context=context):
                if res['buildername'] == args[0][2]:
                    matches.append(res['id'])
            
        elif args[0][1] == 'in':
            for bname in args[0][2]:
                for res in self.search_read(cr, uid, _fmt_expr(bname), fields=['buildername'], context=context):
                    if res['buildername'] == bname:
                        matches.append(res['id'])
        else:
            raise NotImplementedError("no %s operator for buildername" % args[0][1])

        if not matches:
            return [('id', '=', 0 ),]
        elif len(matches) == 1:
            return [('id', '=', matches[0]),]
        else:
            return [('id', 'in', tuple(matches)),]

    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'group_id': fields.many2one('software_dev.buildgroup', 'Group', ),
        'is_distinct': fields.boolean('Distinct builds', required=True,
                help="If set, this series has random builds, not commits that follow each other"),
        
        'package_id': fields.many2one('software_dev.package', 'Package', required=True),
        'branch_id': fields.many2one('software_dev.branch', 'Rolling branch', required=True,
                help="One branch, that is used to test against different commits.",
                ),
        'builder_id': fields.many2one('software_dev.buildbot',
                string='BuildBot', required=True,
                help="Machine that will build this series"),
        'buildername': fields.function(_get_buildername, string='Builder name',
                method=True, type='char', readonly=True, fnct_search=_search_buildername),
        'sequence': fields.integer('Sequence', required=True),
        # 'attribute_ids': fields.one2many('software_dev.attr.bseries', '' TODO)
        'test_id': fields.many2one('software_dev.test', 'Test', 
                help="The test to perform. Steps are configured in the test."),
    }

    _defaults = {
        'is_distinct': False,
        'sequence': 10,
    }

    @virtual
    def get_builders(self, cr, uid, ids, context=None):
        """ Format list of dicts for builders to send to buildbot
        """
        ret = []
        for bldr in self.browse(cr, uid, ids, context=context):
            dir_name = ''
            if bldr.group_id:
                dir_name += bldr.group_id.name + '_'
            if bldr.name:
                dir_name += bldr.name
            dir_name = dir_name.replace(' ', '_').replace('/','_')
            #db_name = dir_name.replace('-','_') # FIXME unused

            bret = { 'name': bldr.buildername,
                    'slavename': bldr.builder_id.slave_ids[0].tech_code,
                    'builddir': dir_name,
                    'steps': [],
                    'branch_url': bldr.branch_id.fetch_url,
                    'branch_name': bldr.name,
                    'properties': { 'sequence': bldr.sequence, }
                    #'tstimer': None, # means one build per change
                    }

            if bldr.group_id:
                bret['properties'].update( {'group': bldr.group_id.name,
                                            'group_seq': bldr.group_id.sequence,
                                            'group_public': bldr.group_id.public,})
            # Now, build the steps:
            
            # before any explicitly defined steps, prepend the VCS steps
            # for each of the components
            for comp in bldr.package_id.component_ids:
                is_rolling = False
                use_latest = False
                if comp.branch_id.id == bldr.branch_id:
                    is_rolling = True
                elif comp.update_rev:
                    use_latest = True
                rtype = comp.branch_id.repo_id.rtype
                if rtype == 'bzr':
                    bret['steps'].append(('OpenObjectBzr', {
                        'repourl': comp.branch_id.fetch_url, 'mode':'update',
                        'workdir': comp.dest_path,
                        'alwaysUseLatest': use_latest,
                        }) )
                elif rtype == 'git':
                    bret['steps'].append(('GitStep', {
                        'repourl': comp.branch_id.fetch_url, 'mode':'update',
                        'workdir': comp.dest_path,
                        'alwaysUseLatest': use_latest,
                        }) )
                else:
                    raise NotImplementedError("Cannot handle %s repo" % rtype)
            

            # Set a couple of builder-wide properties TODO revise
            # bret['properties'].update( { 'orm_id': bldr.id, 'repo_mode': bldr.target_path })

            if bldr.test_id:
                for tstep in bldr.test_id.step_ids:
                    rname = tstep.name
                    rattr = {}
                    for tattr in tstep.attribute_ids:
                        rattr[tattr['name']] = tattr['value'] #strings only, so far
                    bret['steps'].append((rname, rattr))

            ret.append(bret)
        return ret

software_buildseries()

class software_buildset(osv.osv):
    _name = 'software_dev.buildset'

    _columns = {
        'external_idstring': fields.char('Ext ID', size=256),
        'reason': fields.char('Reason', size=256),

        'commit_id': fields.many2one('software_dev.commit', 'Commit', required=True),
        'submitted_at': fields.datetime('Submitted at', required=False, select=True),
        'complete': fields.boolean('Complete', required=True, select=True),
        'complete_at': fields.datetime('Complete At'),
        'results': fields.selection(bbot_results, 'Results'),
    }

    _defaults = {
        'complete': False,
    }

    def createBuildRequests(self, cr, uid, id, builderNames, context=None):
        """ Create buildrequests for this buildset (id), for each of builderNames

            This completes the functionality needed by db.buildset.addBuildset()
            in the master connector.

            @param id a single buildset id, strictly
            @return a dictionary mapping builderNames to buildrequest ids.
        """

        assert isinstance(id, (int, long)), id
        breq_obj = self.pool.get('software_dev.buildrequest')
        bser_obj = self.pool.get('software_dev.buildseries')

        bset_rec = self.browse(cr, uid, id, context=context)
        vals = dict(buildsetid=id, complete=False, submitted_at=bset_rec.submitted_at)
        ret = {}
        for b in bser_obj.search_read(cr, uid,
                    [('buildername', 'in', builderNames)],
                    fields=['buildername']):

            vals['builder_id'] = b['id']
            ret[b['buildername']] = breq_obj.create(vals)

        return ret

software_buildset()

class software_buildrequest(osv.osv):
    _name = 'software_dev.buildrequest'

    _columns = {
        'builder_id': fields.many2one('software_dev.buildseries', 'Builder', required=True, select=True),
        'buildername': fields.related('builder_id', 'buildername', type='char', size=256),
        # every BuildRequest has a BuildSet
        # the sourcestampid and reason live in the BuildSet
        'buildsetid': fields.many2one('software_dev.buildset', 'Build Set', required=True, select=True),
        'priority': fields.integer('Priority', required=True),

        # claimed_at is the time at which a master most recently asserted that
        # it is responsible for running the build: this will be updated
        # periodically to maintain the claim
        'claimed_at': fields.datetime('Claimed at', select=True),

        # claimed_by indicates which buildmaster has claimed this request. The
        # 'name' contains hostname/basedir, and will be the same for subsequent
        # runs of any given buildmaster. The 'incarnation' contains bootime/pid,
        # and will be different for subsequent runs. This allows each buildmaster
        # to distinguish their current claims, their old claims, and the claims
        # of other buildmasters, to treat them each appropriately.
        'claimed_by_name': fields.char('Claimed by name',size=256, select=True),
        'claimed_by_incarnation': fields.char('Incarnation',size=256),

        'complete': fields.boolean('Complete', required=True), # index?

        # results is only valid when complete==1
        'submitted_at': fields.datetime('Submitted at', required=True),
        'complete_at': fields.datetime('Complete At'),
        'results': fields.selection(bbot_results, 'Results'),
    }

    _defaults = {
        'priority': 0,
    }

    def reschedule(self, cr, uid, ids, context=None):
        """Reset completion status, so that this buildset gets rebuilt
        """
        self.write(cr, uid, ids, { 'claimed_at': False, 'complete': False,
                'claimed_by_name': False })
        return True

software_buildrequest()

class software_bbuild(osv.osv):
    """A buildbot build
    """
    _name = "software_dev.build"

    _columns = {
        'build_number': fields.integer('Build number', select=1),
        'buildrequest_id': fields.many2one('software_dev.buildrequest', 'Request', required=True, select=1),
        'build_start_time': fields.datetime('Build start time', required=True),
        'build_finish_time': fields.datetime('Build finish time'),
        'buildername': fields.related('branch_id', 'buildername', type='char', string='Builder name',
                        readonly=True, size=512, store=True, select=True),

        # FIXME: review if they're needed
        'build_summary': fields.text('Result', help="A summary of the build results"),
        'test_results': fields.one2many('software_dev.test_result', 'build_id',
                string='Test results'),
    }

software_bbuild()

class software_dev_mergereq(osv.osv):
    """ This represents scheduled merges, of one commit onto a branch.

        Once the scheduler is ready to merge, it will /transform/ this
        records into commits, where com.merge_id = this.commit_id and
        com.parent_id = this.branch_id.latest-commit.id. It will then
        delete the mergerequest. All merge/test results will be recorded
        at the generated commit.
    """
    _order = 'id'
    _name = 'software_dev.mergerequest'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit', 'Commit',
                        required=True, select=True),
        'branch_id': fields.many2one('software_dev.buildseries', 'Target Branch',
                        required=True, select=True),
        }

    def prepare_commits(self, cr, uid, buildername, context=None):
        """Turn first merge request for buildername into commit.
           @return [commit.id,] or empty list []
        """

        ids = self.search(cr, uid, [('branch_id.buildername', '=', buildername)],
                limit=1, order='id', context=context)
        if ids:
            commit_obj = self.pool.get('software_dev.commit')
            bro = self.browse(cr, uid, ids[0], context=context)
            bot_user = self.pool.get('software_dev.vcs_user').get_user(cr, uid, 'mergebot@openerp', context=context)
            latest_commits = commit_obj.search(cr, uid, [('branch_id', '=', bro.branch_id.id), ('revno', '!=', False)],
                    order='id DESC', limit=1, context=context)

            vals = {
                    'subject': 'Merge %s into %s' % ( bro.commit_id.revno, bro.branch_id.name),
                    'date': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'branch_id': bro.branch_id.id,
                    'comitter_id': bot_user,
                    'parent_id': latest_commits[0],
                    'merge_id': bro.commit_id.id,
                    }
            new_id = commit_obj.create(cr, uid, vals, context=context)
            self.unlink(cr, uid, ids[:1])
            return [new_id,]
        else:
            return []

software_dev_mergereq()

#eof