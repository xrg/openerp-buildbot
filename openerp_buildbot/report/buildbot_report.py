import time
import datetime
import mx.DateTime

import pooler
import tools
from osv import fields,osv

class report_buildbot_branch_test_result_ratio(osv.osv):
    _name="report.buildbot.branch.test.result.ratio"
    _description="Branch test result in ratio"
    _auto = False
    _columns={
              'name': fields.char("Branch Name", size=128),
              'success_ratio': fields.float("Success Ratio"),
              'failure_ratio': fields.float("Failure Ratio"),
              'total_tests': fields.integer("Total Tests"),
              }
    def init(self, cr):
        cr.execute("""
        create or replace view report_buildbot_branch_test_result_ratio as (
            select min(buildbot_lp_branch.id) as id,
            buildbot_lp_branch.name as name,
            ((sum(CASE WHEN state='pass' THEN 1 ELSE 0 END)))/count(buildbot_test.id)::float(1) as success_ratio,
           ((sum(CASE WHEN state='fail' THEN 1 ELSE 0 END)))/count(buildbot_test.id)::float(1) as failure_ratio,
           count(buildbot_test.id) as total_tests
           from buildbot_test join buildbot_lp_branch on buildbot_lp_branch.id = buildbot_test.tested_branch group by buildbot_lp_branch.name)
        """)

report_buildbot_branch_test_result_ratio()

class report_branch_test_statistics(osv.osv):
    _name="report.branch.test.statistics"
    _description="Branch test results statistics"
    _auto=False
    _columns={
              'name': fields.char("Branch Name", size=8),
              'curr_rev': fields.char("Active revision(R)", size=8),
              'rev1': fields.char("R+1", size=8),
              'rev2': fields.char("R+2", size=8),
              'rev3': fields.char("R+3", size=8),
              'rev4': fields.char("R-3", size=8),
              'rev5': fields.char("R-2", size=8),
              'rev6': fields.char("R-1", size=8),
              }
    def init(self, cr):
        cr.execute("""
        create or replace view report_branch_test_statistics as (
            select br.name as name,
            test.id as id,
            test4.state as rev4,
            test5.state as rev5,
            test6.state as rev6,
            test.state as curr_rev,
            test1.state as rev1,
            test2.state as rev2,
            test3.state as rev3
            from buildbot_lp_branch as br join buildbot_test as test on br.id = test.tested_branch
            left join buildbot_test as test4 on test.commit_rev_no=test4.commit_rev_no+3
            left join buildbot_test as test5 on test.commit_rev_no=test5.commit_rev_no+2
            left join buildbot_test as test6 on test.commit_rev_no=test6.commit_rev_no+1
            left join buildbot_test as test1 on test.commit_rev_no=test1.commit_rev_no-1
            left join buildbot_test as test2 on test.commit_rev_no=test2.commit_rev_no-2
            left join buildbot_test as test3 on test.commit_rev_no=test3.commit_rev_no-3)
        """)
report_branch_test_statistics()