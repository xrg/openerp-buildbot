# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2010 OpenERP SA. (http://www.openerp.com)
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

from tools.translate import _
from osv import fields, osv
from datetime import datetime
import time

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

class software_user(osv.osv):
    """ A VCS user is one identity that appears in VCS and we map to our users
    """
    _name = 'software_dev.vcs_user'
    _description = 'Developer in VCS'
    def _get_name(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            res[b.id] = b.userid
        return res


    _columns = {
        'name': fields.function(_get_name, string='Name', method=True, 
                    type='char', store=False, readonly=True),
        'userid': fields.char('User identity', size=1024, required=True, select=1,
                    help="The unique identifier of the user in this host. " \
                        "Sometimes the email or login of the user in the host." ),
        # 'employee_id': fields.many2one('hr.employee', 'Employee'),
    }

    _defaults = {
    }
    
    _sql_constraints = [ ('user_uniq', 'UNIQUE(userid)', 'User id must be unique.'), ]
   
    def get_user(self, cr, uid, userid, context=None):
        """Return the id of the user with that name, even create one
        """
        ud = self.search(cr, uid, [('userid', '=', userid)], context=context)
        if ud:
            return ud[0]
        else:
            return self.create(cr, uid, { 'userid': userid }, context=context)

software_user()

class propertyMix(object):
    """ A complementary class that adds properties to osv objects
    
        In principle, these properties could apply to any osv object,
        but we do only use them for the software_dev.* ones.
    """

    def getProperties(self, cr, uid, ids, names=None, context=None):
        """ Retrieve the properties for a range of ids.
        
            The object is the class inheriting this one.
            Due to a limitation of XML-RPC, we could not regroup the
            result by 'id', so the returning result is that of read() :
            [ { 'id': 1, 'name': prop, 'value': val }, ... ]
        """
        prop_obj = self.pool.get('software_dev.property')

        dom = [('model_id.model', '=', self._name), ('resid', 'in', list(ids)), ]
        if names:
            dom.append(('name', 'in', names))
        pids = prop_obj.search(cr, uid, dom, context=context)

        if not pids:
            return []
        res = prop_obj.read(cr, uid, pids, ['name', 'value'], context=context)

        return res

    def setProperties(self, cr, uid, id, vals, clear=False, context=None):
        """ Set properties for one object
        """
        prop_obj = self.pool.get('software_dev.property')
        imo_obj = self.pool.get('ir.model')
        
        imid = imo_obj.search(cr, uid, [('model', '=', self._name)])[0]

        if clear:
            dom = [('model_id.model', '=', self._name), ('resid', '=', id), ]
            pids = prop_obj.search(cr, uid, dom, context=context)
            if pids:
                prop_obj.unlink(cr, uid, pids)

        for name, value in vals: # yes, values must be a list of tuples
            prop_obj.create(cr, uid, { 'model_id': imid, 'resid': id,
                                        'name': name, 'value': value }, context=context)

        return True

class software_buildbot(osv.osv):
    _name = 'software_dev.buildbot'
    _description = 'Software Build Bot'
    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'tech_code': fields.char('Code', size=64, required=True, select=1),
        'http_port': fields.integer('Http port', help="Port to run the buildbot status server at"),
        'http_url': fields.char('Http URL', size=128, help="Base url of our buildbot server, for formatting the full link to results."),
        'attribute_ids': fields.one2many('software_dev.battr', 'bbot_id', 'Attributes'),
        'slave_ids': fields.one2many('software_dev.bbslave', 'bbot_id', 'Test Steps', 
                help="The test steps to perform."),
    }

    _sql_constraints = [ ('code_uniq', 'UNIQUE(tech_code)', 'The tech code must be unique.'), ]
    
    def get_polled_branches(self, cr, uid, ids, context=None):
        """Helper for the buildbot, list all the repos+branches it needs to poll.
        
        Since it is difficult to write RPC calls for browse(), we'd better return
        a very easy dictionary of values for the buildbot, that may configure
        its pollers.
        @return A list of dicts, with branch (or repo) information
        """
        
        ctx = context or {}
        
        ret = []
        found_branches = []   # ids of branches we have made so far

        bseries_obj = self.pool.get('software_dev.buildseries')
        series_ids = bseries_obj.search(cr, uid, [('builder_id','in',ids), ('is_build','=',True)], context=ctx)  # :(

        for bser in bseries_obj.browse(cr, uid, series_ids, context=ctx):
            dret = {}
            dret['branch_id'] = bser.id
            dret['branch_name'] = bser.name
            dret['rtype'] = 'bzr'
            dret['branch_path'] = bser.target_path
            dret['fetch_url'] = bser.branch_url
            dret['poll_interval'] = 600 # bser.poll_interval
            ret.append(dret)

        return ret

    def get_builders(self, cr, uid, ids, context=None):
        """ Return a complete dict with the builders for this bot
        
        Sample:
           name: name
           slavename
           build_dir
           branch_url
           tstimer
           steps [ (name, { props}) ]
        """
        ret = []
        bs_obj = self.pool.get('software_dev.buildseries')
        bids = bs_obj.search(cr, uid, [('builder_id', 'in', ids), ('is_build','=',True)], context=context)
        for bldr in bs_obj.browse(cr, uid, bids, context=context):
            dir_name = ''
            if bldr.group_id:
                dir_name += bldr.group_id.name + '_'
            if bldr.name:
                dir_name += bldr.name
            dir_name = dir_name.replace(' ', '_').replace('/','_')
            db_name = dir_name.replace('-','_')

            bret = { 'name': bldr.buildername,
                    'slavename': bldr.builder_id.slave_ids[0].tech_code,
                    'builddir': dir_name,
                    'steps': [],
                    'branch_url': bldr.branch_url,
                    'branch_name': bldr.name,
                    #'tstimer': None, # means one build per change
                    }
            # Now, build the steps:
            for bdep in bldr.dep_branch_ids:
                bret['steps'].append( ('OpenObjectBzr', {
                        'repourl': bdep.branch_url, 'mode':'update',
                        'workdir': bdep.target_path,
                        'alwaysUseLatest': True
                        }) )
            
            bret['steps'].append( ('OpenObjectBzr', {
                        'repourl': bldr.branch_url, 'mode':'update',
                        'workdir': bldr.target_path,
                        'alwaysUseLatest': False }) )
            for tstep in bldr.test_ids:
                rname = tstep.name
                rattr = {}
                for tattr in tstep.attribute_ids:
                    rattr[tattr['name']] = tattr['value'] #strings only, so far
                bret['steps'].append((rname, rattr))
        
            ret.append(bret)
        return ret

software_buildbot()

class software_battr(osv.osv):
    """ Build bot attribute
    
        Raw name-value pairs that are fed to the buildbot
    """
    _name = 'software_dev.battr'
    _columns = {
        'bbot_id': fields.many2one('software_dev.buildbot', 'BuildBot', required=True, select=1),
        'name': fields.char('Name', size=64, required=True, select=1),
        'value': fields.char('Value', size=256),
        }

software_battr()


class software_bbot_slave(osv.osv):
    """ A buildbot slave
    """
    _name = 'software_dev.bbslave'
    
    _columns = {
        'bbot_id': fields.many2one('software_dev.buildbot', 'Master bot', required=True),
        'name': fields.char('Name', size=64, required=True, select=1),
        'tech_code': fields.char('Code', size=64, required=True, select=1),
        'password': fields.char('Secret', size=128, required=True,
                    help="The secret code used by the slave to connect to the master"),
        #'property_ids': fields.one2many('software_dev.bsattr', 'bslave_id', 'Properties'),
    }

    _sql_constraints = [ ('code_uniq', 'UNIQUE(tech_code)', 'The tech code must be unique.'), ]

software_bbot_slave()


# Tests...
_target_paths = [('server', 'Server'), ('addons', 'Addons'), ('extra_addons', 'Extra addons')]
class software_buildseries(propertyMix, osv.osv):
    """ A series is a setup of package+test+branch+result+dependencies+bot scenaria
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

    _columns = {
        'name': fields.char('Name', required=True, size=64),
        'description': fields.text('Description'),
        'group_id': fields.many2one('software_dev.buildgroup', 'Group', ),
        'is_distinct': fields.boolean('Distinct builds', required=True,
                help="If set, this series has random builds, not commits that follow each other"),
        'is_build': fields.boolean('Perform test', required=True,
                help="If checked, this branch will be built. Otherwise, just followed"),
        'target_path': fields.selection(_target_paths, 'Branch Type' ),
        'branch_url': fields.char('Branch Url', size=512, required=True,
                help="The place of the branch in Launchpad (only).",
                ),
        'builder_id': fields.many2one('software_dev.buildbot', 
                string='Buildbot', required=True,
                help="Machine that will build this series"),
        'sequence': fields.integer('Sequence', required=True),
        # 'attribute_ids': fields.one2many('software_dev.attr.bseries', '' TODO)
        'test_ids': fields.one2many('software_dev.teststep', 'test_id', 'Test Steps', 
                help="The test steps to perform."),
        'dep_branch_ids': fields.many2many('software_dev.buildseries', 
            'software_dev_branch_dep_rel', 'end_branch_id', 'dep_branch_id',
            string="Dependencies",
            help="Branches that are built along with this branch"),
        'buildername': fields.function(_get_buildername, string='Builder name',
                method=True, type='char', readonly=True),
    }

    _defaults = {
        'is_distinct': False,
        'is_build': True,
        'sequence': 10,
    }

software_buildseries()

class software_teststep(propertyMix, osv.osv):
    """A scenario that has to be tested on some package
    """
    _name = 'software_dev.teststep'
    _description = 'Software Test Step'
    _order = "sequence, id"
    _columns = {
        'test_id': fields.many2one('software_dev.buildseries', 'Test', 
                required=True, select=1),
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
        'tstep_id': fields.many2one('software_dev.teststep', 'Test Step', required=True, select=1),
        'name': fields.char('Name', size=64, required=True),
        'value': fields.char('Value', size=256),
        }

software_tsattr()


commit_types = [ ('reg', 'Regular'), ('merge', 'Merge'), ('single', 'Standalone'), 
            ]

class software_commit(propertyMix, osv.osv):
    """ An entry in the VCS
    """
    _name = 'software_dev.commit'
    _description = 'Code Commit'
    
    def _get_name(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            name = ''
            if b.revno:
                name += '#%s ' % b.revno
            elif b.hash:
                name += '%s ' % b.hash[:8]
            name += b.subject
            res[b.id] = name
        return res

    def name_search(self, cr, uid, name='', args=None, operator='ilike',  context=None, limit=None):
        if args is None:
            args = []
        if operator in ('ilike', 'like'):
            op2 = '='
        elif operator in ('not ilike', 'not like'):
            op2 = '!='
        else:
            op2 = operator
        domain = args + ['|', '|', ('hash', operator, name), ('revno', op2, name),
                        ('subject', operator, name)]
        return super(software_commit, self).name_search(cr, uid, None, domain,
                        operator=operator, limit=limit, context=context)

    _columns = {
        'name': fields.function(_get_name, string='Name', size=512,
                method=True, type='char', readonly=True),
        'subject': fields.char('Subject', required=True, size=256),
        'description': fields.text('Description'),
        'date': fields.datetime('Date', required=True),
        'branch_id': fields.many2one('software_dev.buildseries', 'Branch', required=True, select=1),
        'hash': fields.char('Hash', size=1024, select=1,
                help="In repos that support it, a unique hash of the commit"),
        'revno': fields.char('Revision', size=128, select=1,
                help="Sequential revision number, in repos that have one"),
        'ctype': fields.selection(commit_types, 'Commit type', required=True),
        'comitter_id': fields.many2one('software_dev.vcs_user', 'Committer', required=True),
        'author_ids': fields.many2many('software_dev.vcs_user', 
                'software_dev_commit_authors_rel', 'commit_id', 'author_id', 'Authors',
                help="Developers who have authored the code"),
        'change_ids': fields.one2many('software_dev.filechange', 'commit_id', 'Changes'),
        'parent_id': fields.many2one('software_dev.commit', 'Parent commit'),
        #'contained_commit_ids': fields.many2many('software_dev.commit', 
        #    'software_dev_commit_cont_rel', 'end_commit_id', 'sub_commit_id',
        #    help="Commits that are contained in this, but not the parent commit"),
    }
    
    _sql_constraints = [ ('branch_hash_uniq', 'UNIQUE(branch_id, hash)', 'Hash must be unique. (per branch)'),
                # ('branch_revno_uniq', 'UNIQUE(branch_id, revno)', 'Revision no. must be unique in branch'),
                ]

    _defaults = {
        'ctype': 'reg',
    }
    
    def submit_change(self, cr, uid, cdict, context=None):
        """ Submit full info for a commit, in a dictionary
        """
        assert isinstance(cdict, dict)
        user_obj = self.pool.get('software_dev.vcs_user')
        fchange_obj = self.pool.get('software_dev.filechange')
        
        clines = cdict['comments'].split('\n',1)
        subj = clines[0]
        descr = '\n'.join(clines[1:])
        new_vals = {
            'subject': subj,
            'description': descr,
            'date': datetime.fromtimestamp(cdict['when']),
            'branch_id': cdict['branch_id'],
            'comitter_id': user_obj.get_user(cr, uid, cdict['who'], context=context),
            'revno': cdict['rev'],
            'hash': cdict.get('hash', False),
            'authors': [ user_obj.get_user(cr, uid, usr, context=context)
                            for usr in cdict.get('authors', []) ],
            }
        cid = self.create(cr, uid, new_vals, context=context)
         
        if cdict.get('filesb'):
            # try to submit from the detailed files member
            for cf in cdict['filesb']:
                fval = { 'commit_id': cid,
                    'filename': cf['filename'],
                    'ctype': cf.get('ctype', 'm'),
                    'lines_add': cf.get('lines_add', 0),
                    'lines_rem': cf.get('lines_rem', 0),
                    }
                fchange_obj.create(cr, uid, fval, context=context)
                
        else: # use the compatible list, eg. when migrating
            for cf in cdict['files']:
                fval = { 'commit_id': cid,
                    'filename': cf['name'],
                    }
                fchange_obj.create(cr, uid, fval, context=context)
        return cid

    def getChanges(self, cr, uid, ids, context=None):
        """ Format the commits into a dictionary
        """
        ret = []
        for cmt in self.browse(cr, uid, ids, context=context):
            if isinstance(cmt.date, basestring):
                dt = cmt.date.rsplit('.',1)[0]
                tdate = time.mktime(time.strptime(dt, '%Y-%m-%d %H:%M:%S'))
            else:
                tdate = time.mktime(cmt.date)
            cdict = {
                'id': cmt.id,
                'comments': cmt.name,
                'when': tdate,
                'branch_id': cmt.branch_id.id,
                'branch': cmt.branch_id.branch_url,
                'who': cmt.comitter_id.userid,
                'revision': cmt.revno,
                'hash': cmt.hash,
                'filesb': [],
                }
            for cf in cmt.change_ids:
                cdict['filesb'].append( {
                        'filename': cf.filename,
                        'ctype': cf.ctype,
                        'lines_add': cf.lines_add,
                        'lines_rem': cf.lines_rem,
                        })
            
            ret.append(cdict)
        return ret

software_commit()

change_types = [ ('a', 'Add'), ('m', 'Modify'), ('d', 'Delete'), 
                ('c', 'Copy'), ('r', 'Rename') ]

class software_filechange(osv.osv):
    """ Detail of commit: change to a file
    """
    _name = 'software_dev.filechange'
    _description = 'Code File Change'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit','Commit', 
                required=True, ondelete='cascade'),
        'filename': fields.char('File Name', required=True, size=1024, select=1),
        'ctype': fields.selection(change_types, 'Change type', required=True,
                help="The type of change that occured to the file"),
        'lines_add': fields.integer('Lines added'),
        'lines_rem': fields.integer('Lines removed'),
    }
    _defaults = {
        'ctype': 'm',
    }
    
    _sql_constraints = [( 'commit_file_uniq', 'UNIQUE(commit_id, filename)', 'Commit cannot contain same file twice'), ]

software_filechange()

class software_buildseries2(osv.osv):
    _inherit = 'software_dev.buildseries'
    
    _columns = {
        'latest_commit_id': fields.many2one('software_dev.commit', string='Latest commit'),
        }

software_buildseries2()

class software_buildscheduler(propertyMix, osv.osv):
    _name = 'software_dev.buildscheduler'
    _description = 'Build Scheduler'
    _columns = {
        'name': fields.char('Name', required=True, size=256, select=1),
        'class_name': fields.char('Class name', size=256, required=True),
        'state_dic': fields.text('State'),
        'change_ids': fields.one2many('software_dev.sched_change', 'sched_id', 'Changes'),
    }

    _sql_constraints = [( 'name_class_uniq', 'UNIQUE(class_name, name)', 'Cannot reuse name at the same scheduler class.'), ]

software_buildscheduler()

class software_schedchange(osv.osv):
    """ Connect a commit to a scheduler and if the sched is interested in it
    """
    _name = 'software_dev.sched_change'
    _description = 'Commit at Scheduler'
    _columns = {
        'commit_id': fields.many2one('software_dev.commit','Commit', required=True),
        'sched_id': fields.many2one('software_dev.buildscheduler','Scheduler', required=True, select=1),
        'important': fields.boolean('Is important', required=True, 
                    help="If true, this change will trigger a build, else just recorded."),
    }
    _defaults = {
        'important': True,
    }
    
    _sql_constraints = [( 'commit_sched_uniq', 'UNIQUE(commit_id, sched_id)', 'A commit can only be at a scheduler once'), ]

software_schedchange()


class software_buildset(osv.osv):
    _inherit = 'software_dev.commit'
    
    _columns = {
        'external_idstring': fields.char('Ext ID', size=256),
        'reason': fields.char('Reason', size=256),
        
        #`sourcestampid` INTEGER NOT NULL,
        'submitted_at': fields.datetime('Submitted at', required=False),
        'complete': fields.boolean('Complete', required=True),
        'complete_at': fields.datetime('Complete At'),
        'results': fields.integer('Results'),
    }

    _defaults = {
        'complete': False,
    }

software_buildset()

class software_buildrequest(osv.osv):
    _inherit = 'software_dev.commit'
    
    _columns = {
        # every BuildRequest has a BuildSet
        # the sourcestampid and reason live in the BuildSet
        # 'buildsetid': ...

        # 'buildername': ...

        'priority': fields.integer('Priority', required=True),

        # claimed_at is the time at which a master most recently asserted that
        # it is responsible for running the build: this will be updated
        # periodically to maintain the claim
        'claimed_at': fields.datetime('Claimed at'),

        # claimed_by indicates which buildmaster has claimed this request. The
        # 'name' contains hostname/basedir, and will be the same for subsequent
        # runs of any given buildmaster. The 'incarnation' contains bootime/pid,
        # and will be different for subsequent runs. This allows each buildmaster
        # to distinguish their current claims, their old claims, and the claims
        # of other buildmasters, to treat them each appropriately.
        'claimed_by_name': fields.char('Claimed by name',size=256),
        'claimed_by_incarnation': fields.char('Incarnation',size=256),

        # 'complete': fields.integer()

        # results is only valid when complete==1
        # 'results': fields.integer('Results'),
        # 'submitted_at': fields.datetime('Submitted at', required=True),
        # 'complete_at': fields.datetime('Complete At'),
    }

    _defaults = {
        'priority': 0,
    }

    def reschedule(self, cr, uid, ids, context=None):
        """Reset completion status, so that this buildset gets rebuilt
        """
        self.write(cr, uid, ids, { 'claimed_at': False, 'complete': False,
                'claimed_by_name': False })

software_buildrequest()

class software_bbuild(osv.osv):
    """A buildbot build
    """
    _inherit = "software_dev.commit"

    def _get_buildername(self, cr, uid, ids, name, args, context=None):
        res = {}
        for b in self.browse(cr, uid, ids, context=context):
            res[b.id] = b.branch_id.buildername
        return res

    _columns = {
        'build_number': fields.integer('Build number', select=1),
        # 'number' is scoped to both the local buildmaster and the buildername
        # 'br_id' matches buildrequests.id
        'build_start_time': fields.datetime('Build start time'),
        'build_finish_time': fields.datetime('Build finish time'),
        'buildername': fields.function(_get_buildername, string='Builder name',
                method=True, type='char', readonly=True, size=512, store=True),
        'build_summary': fields.text('Result', help="A summary of the build results"),
        'test_results': fields.one2many('software_dev.test_result', 'build_id', 
                string='Test results'),
    }
    
software_bbuild()

class software_test_result(osv.osv):
    """ This is the unit of results for software tests
    """
    
    _name = "software_dev.test_result"
    _columns = {
                'name': fields.char('Name of Step', size=128, help="Name of the Test step"),
                'sequence': fields.integer('Sequence', required=True),
                # TODO 'teststep_id':
                'build_id': fields.many2one('software_dev.commit', 'Build', ondelete='cascade',
                        select=1,
                        help="Build on which the result was taken"),
                'blame_log': fields.text("Summary", help="Quick blame info of thing(s) that failed"),
                'substep': fields.char('Substep', size=256, help="Detailed substep"),
                'rate_pc': fields.float('Score', help='A measure of success, marked as a percentage'),
                
                'state': fields.selection([('unknown','Unknown'), ('fail', 'Failed'), 
                                            ('warning','Warning'), ('exception', 'Exception'),
                                            ('pass', 'Passed'),('skip', 'Skipped'),
                                            ('retry', 'Retry'),
                                            ('debug','Debug')], 
                                            "Test Result", readonly=True, required=True,
                                            help="Final State of the Test Step"),
        }
    _defaults = {
                 'state':'unknown',
                 'sequence': 0,
                }
    _order = 'build_id, sequence, id'
software_test_result()

class software_dev_property(osv.osv):
    """ A class for generic properties on buildbot classes
    """
    
    _name = 'software_dev.property'
    
    _columns = {
        'model_id': fields.many2one('ir.model', 'Model', required=True,
                        select=1,
                        domain= [('model', 'like','software_dev.')],
                        help="The model to have the property"),
        'resid': fields.integer('Res ID', required=True, select=1),
        'name': fields.char('Name', size=256, required=True),
        'value': fields.text('Value', required=True),
    }
    
software_dev_property()

#eof
