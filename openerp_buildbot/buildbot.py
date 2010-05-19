from osv import fields
from osv import osv

class buildbot_lp_group(osv.osv):
    _name = "buildbot.lp.group"
    _columns = {
                'name': fields.char('Team Name', size=64, required=True),
                'sequence': fields.integer('Sequence'),
                'url': fields.char('Team URL', size=128, required=True),
                }
buildbot_lp_group()

class buildbot_lp_user(osv.osv):
    _name = "buildbot.lp.user"
    _columns = {
                'name': fields.char('LP User Name', size=64, required=True),
                'url': fields.char('User Url', size=128, required=True),
                'user_id': fields.many2one('res.users', 'User'),
                'lp_group_ids': fields.many2many('buildbot.lp.group', 'buildbot_lp_users_groups_rel', 'lp_user_id', 'lp_group_id', 'Buildbot Groups')
                }
buildbot_lp_user()

class buildbot_lp_branch(osv.osv):
    _name = "buildbot.lp.branch"
    _columns = {
                'name': fields.char('LP Branch', size=128, required=True),
                'lp_group_id': fields.many2one('buildbot.lp.group', 'LP Group'),
                'lp_user_id': fields.many2one('buildbot.lp.user', 'LP User'),
                'url': fields.char('Source Url', size=128, required=True),
                'lastest_rev_id': fields.char('Revision Id', size=128),
                'lastest_rev_no': fields.integer('Revision Number'),
                'active': fields.boolean('Active'),
                "is_test_branch": fields.boolean("Test Branch"),
                "is_root_branch": fields.boolean("Root Branch"),
                'treestabletimer': fields.integer('Tree Stable Timer'),
                'build_directory': fields.char('Build Directoy', size=128),
                'dbname': fields.char('Database Name', size=128),
                'port':fields.integer('port'),
                'netport':fields.integer('net-port'),

                }
    _defaults = {
        'active': lambda *a: 1,
        }
    _sql_constraints = [
        ('dbname_build_dir_uniq', 'unique (dbname, build_directory)', 'The database name and build directory must be unique !')
    ]
buildbot_lp_branch()

class buildbot_lp_project(osv.osv):
    _name = "buildbot.lp.project"
    _columns = {
                'name': fields.char('Project Name', size=64, required=True),
                'url': fields.char('Project URL', size=128, required=True),
                'tester_addons_branch_id': fields.many2one('buildbot.lp.branch', 'Tester Addons Branch', required=True),
                'tester_server_branch_id': fields.many2one('buildbot.lp.branch', 'Tester Server Branch', required=True),
                'root_branch_id': fields.many2one('buildbot.lp.branch', 'Root Branch', required=True),
                }
buildbot_lp_project()

class buildbot_lp_project(osv.osv):
    _name = "buildbot.lp.project"
    _inherit = "buildbot.lp.project"
    _columns = {
                'branch_ids':fields.one2many('buildbot.lp.branch','lp_project_id','Branches'),
                }
buildbot_lp_project()

class buildbot_lp_branch(osv.osv):
    _name = "buildbot.lp.branch"
    _inherit = "buildbot.lp.branch"
    _columns = {
                'lp_project_id': fields.many2one('buildbot.lp.project', 'LP Project',),
                }
buildbot_lp_branch()

class buildbot_test_environment(osv.osv):
    _name = "buildbot.test.environment"
    _columns = {
                'name': fields.char('Name', size=100, required=True),
                'version': fields.char('Version', size=64,),
                'revision_id': fields.char('Revision Id', size=64,),
                'source_url': fields.char('Source Url', size=128),
                'note': fields.text('Note'),
                }
buildbot_test_environment()

class buildbot_test(osv.osv):
    _name = "buildbot.test"

    def _get_test_result(self, cr, uid, ids, name, args, context=None):
        if ids:
            return {ids[0]:'pass'}
        return {}

    _columns = {
              'name': fields.char('Test Name', size=500, required=True),
              'test_date': fields.datetime('Date of Test', required=True),
              'tested_branch': fields.many2one('buildbot.lp.branch', 'Branch', required=True),
              'environment_id': fields.many2many('buildbot.test.environment','buildbot_test_evironment_rel','test_id','env_id','Test Environment'),
              'commiter_id': fields.many2one('buildbot.lp.user', 'Branch Committer',required=True),
              'commit_date': fields.datetime('Date Of Commit', required=True),
              'commit_comment': fields.text('Comment On Commit'),
              'commit_rev_id': fields.char('Revision Id', size=128),
              'commit_rev_no': fields.integer('Revision No.'),
              'new_files': fields.text('Files Added'),
              'update_files': fields.text('Files Updated'),
              'remove_files': fields.text('Files Removed'),
              'rename_files': fields.text('Files Renamd'),
              'state': fields.function(_get_test_result, method=True, type='char', size=8, string="Test Result"),
              'test_step_ids':fields.one2many('buildbot.test.step', 'test_id', 'Test Steps'),
              }
buildbot_test()

class buildbot_test_step(osv.osv):
    _name = "buildbot.test.step"

    def _get_step_result(self, cr, uid, ids, name, args, context=None):
        if ids:
            return {ids[0]:'pass'}
        return {}

    _columns = {
                'name': fields.char('Name of Step', size=128),
                'test_id': fields.many2one('buildbot.test', 'Test'),
                'warning_log': fields.text('Warning Log'),
                'error_log': fields.text('Error Log'),
                'critical_log': fields.text('Critical Log'),
                'info_log': fields.text('Info Log'),
                'yml_log': fields.text('YML-Test Log'),
                'traceback_detail': fields.text('Traceback'),
                'state': fields.function(_get_step_result, method=True, type='char', size=8, string="Step Result"),
        }
buildbot_test_step()