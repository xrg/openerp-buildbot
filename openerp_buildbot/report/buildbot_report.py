import tools
from osv import fields,osv

class report_buildbot_data(osv.osv):
    _name = "report.buildbot.data"
    _description = "Buildbot Data"
    _auto = False
    _columns = {
        'tester_server_br': fields.char('Tester Server Name', size=128, required=True),
        'tester_server_br_url': fields.char('Tester Server Url', size=128, required=True),
        'tester_addons_br':fields.char('Tester Addons Name', size=128, required=True),
        'tester_addons_br_url':fields.char('Tester Server Url', size=128, required=True),
        'testing_br_id':fields.integer('Testing Branch Id'),
        'testing_br_name': fields.char('Testing Server Name', size=128, required=True),
        'testing_br_url': fields.char('Testing Server Url', size=128, required=True),
        'stabletimer': fields.integer('TreeStableTimer'),
        'databasename': fields.char('Database name', size=64, required=True),
        'builddir': fields.char('Build Directory', size=64, required=True),
        'pr_name': fields.char('Project Name', size=64, required=True),
    }
    _order = 'testing_br_name'

    def init(self, cr):
        tools.drop_view_if_exists(cr, 'report_buildbot_data')
        cr.execute("""create or replace view report_buildbot_data as (
            select min(BR.id) as id ,PR.name as pr_name,
       test_server_BR.name as tester_server_br, test_server_BR.url as tester_server_br_url,
       test_addons_BR.name as tester_addons_br, test_addons_BR.url as tester_addons_br_url,
       BR.id as testing_br_id, BR.name as testing_br_name, BR.url as testing_br_url,
       BR.treestabletimer as stabletimer,
       BR.dbname as databasename,
       BR.build_directory as builddir
from buildbot_lp_branch as BR
join buildbot_lp_project as PR on BR.lp_project_id = PR.id
join buildbot_lp_branch as test_addons_BR on test_addons_BR.id = PR.tester_addons_branch_id
join buildbot_lp_branch as test_server_BR on test_server_BR.id = PR.tester_server_branch_id
where BR.active = true
group by pr_name, tester_server_br, tester_server_br_url, tester_addons_br, tester_addons_br_url, testing_br_id, testing_br_name, testing_br_url, stabletimer, databasename, builddir)""")

report_buildbot_data()