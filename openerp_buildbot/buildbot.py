from osv import fields
from osv import osv

class buildbot_lp_group(osv.osv): 
    _name = "buildbot.lp.group" 
    _columns = {
                'name': fields.char('Group Name', size=64, required=True),
                'sequence': fields.integer('Sequence'),
                'url': fields.char('Group URL', size=128, required=True),
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
                'lastest_rev_id': fields.char('Revision Id', size=128, required=True),
                'lastest_rev_no': fields.integer('Revision Number'),
                'active': fields.boolean('Active'),
                "is_test_branch": fields.boolean("Test Branch"),
                "is_root_branch": fields.boolean("Root Branch"),
                }
    _defaults = {
        'active': lambda *a: 1,
        }
buildbot_lp_branch()

class buildbot_lp_project(osv.osv):
    _name = "buildbot.lp.project"
    _columns = {
                'name': fields.char('Project Name', size=64, required=True),
                'url': fields.char('Project URL', size=128, required=True),
#                'branch_ids':fields.one2many('buildbot.lp.branch','lp_project_id','Branches'),
#                'test_branch_id': fields.many2one('buildbot.lp.branch', 'Tester Addons Branch'),
                'tester_addons_branch_id': fields.many2one('buildbot.lp.branch', 'Tester Addons Branch'),
                'tester_server_branch_id': fields.many2one('buildbot.lp.branch', 'Tester Server Branch'),
                'root_branch_id': fields.many2one('buildbot.lp.branch', 'Root Branch'),
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
                'lp_project_id': fields.many2one('buildbot.lp.project', 'LP Project'),
                }
buildbot_lp_branch()

class buildbot_test_environment(osv.osv):
    _name = "buildbot.test.environment"
    _columns = {
                'name': fields.char('Name', size=100, required=True),
                'version': fields.char('Version', size=64, required=True),  
                'revision_id': fields.char('Revision Id', size=64, required=True),
                'source_url': fields.char('Source Url', size=128), 
                'note': fields.text('Note'),
                } 
buildbot_test_environment()

class buildbot_test(osv.osv):
    _name = "buildbot.test" 
    _columns = {
              'name': fields.char('Test Name', size=64, required=True), 
              'create_date': fields.datetime('Date of Test'), 
              'tested_branch': fields.many2one('buildbot.lp.branch', 'Branch Tested'),  
              'environment_id': fields.many2one('buildbot.test.environment', 'Test Environment'), 
              'commiter_id': fields.many2one('buildbot.lp.user', 'Branch Committer'),        
              'commit_date': fields.datetime('Date Of Commit'), 
              'commit_comment': fields.text('Comment On Commit'), 
              'commit_rev_id': fields.char('Revision Id', size=128), 
              'commit_rev_no': fields.integer('Revision No.'),
              'new_files': fields.text('Files Added'), 
              'update_files': fields.text('Files Updated'), 
              'remove_files': fields.text('Files Removed'), 
              'rename_files': fields.text('Files Renamd'),
              'state': fields.selection([('fail', 'Fail'), ('pass', 'Pass')], "Test Result"), 
              }   
buildbot_test()

class buildbot_test_step(osv.osv): 
    _name = "buildbot.test.step" 
    _columns = {
                'name': fields.char('Name of Step', size=128),        
                'test_id': fields.many2one('buildbot.test', 'Test'), 
                'warning_log': fields.text('Warning Log'), 
                'error_log': fields.text('Error Log'), 
                'critical_log': fields.text('Critical Log'), 
                'info_log': fields.text('Info Log'),
                'yml_log': fields.text('YML-Test Log'),
                'traceback_detail': fields.text('Traceback'), 
                'state': fields.selection([('fail', 'Fail'), ('pass', 'Pass')], "Step Result"),
        }
buildbot_test_step()


class buildbot_directory(osv.osv):
    _name="buildbot.directory"
    _columns={
              'name': fields.char('Directory Name', size=128),
              'parent_id': fields.many2one('buildbot.directory', 'Buildbot Directory', select=True),
              'child_ids': fields.one2many('buildbot.directory', 'parent_id', 'Work Directories'),
              }
buildbot_directory()

class buildbot_step(osv.osv):
    _name="buildbot.step"
    _columns={
              'name': fields.char('Step Name', size=128)
              }
buildbot_step()   
class buildbot_builder(osv.osv):
    _name="buildbot.builder"
    _columns={
              'name': fields.char('Builder Name', size=128),
              'build_directory': fields.many2one('buildbot.directory','Build Directoy'),
              'dbname': fields.char('Database Name', size=128),
              'workdir': fields.many2one('buildbot.directory','Work Directoy'),
              'addons_dir': fields.many2one('buildbot.directory','Addons Directoy'),
              'build_steps': fields.many2many('buildbot.step', 'buildbot_builder_step_rel', 'builder_id', 'step_id', 'Steps')
              }
buildbot_builder()

class buildbot_scheduler(osv.osv):
    _name="buildbot.scheduler"
    _columns={
              'name': fields.char('Name of Scheduler', size=128),
              #'change_branch_ids': fields.many2many('buildbot.lp.branch', 'buildbot_scheduler_lp_branch_rel','scheduler_id', 'branch_id', 'Scheduler Changes Branch', help='Branches that trigger scheduler'),
              #'builder_ids': fields.many2many('buildbot.builder', 'buildbot_scheduler_builder_rel','scheduler_id', 'builder_id', 'Builders for Schedulers', help='Builders that are build when scheduler is triggered'),
              'change_branch_id': fields.many2one('buildbot.lp.branch', 'Change Branch'),
              'builder_id': fields.many2one('buildbot.builder', 'Builder'),
              'treestabletimer': fields.integer('Tree Stable Timer')
              }
buildbot_scheduler()