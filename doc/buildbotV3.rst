Buildbot: 0.8.1+

class groups
    _order = 'sequence'
    sequence
    name

class branches (aka. build series)
    group_id: many2one
    type : server,addons
    url: lp:sdfsadfsadfsa/sdafasdf
    depends: many2many branch_id
    active : boolean
    testmode: 
    test_ids: one2many(build_test)
    revno: fields.related('test_ids', 'revno', 'Latest Revno')

class build_test (aka. build series commit)
    _order = 'date desc'
    date
    branch: many2one
    commiter: many2one
    date of commit
    revid
    revno
    commit message,  TESTALL
    failure reason
    buildbot URL:
    status: selection; pass, failed, pending
    status_change: nothing, red, green
    test_step_ids: one2many
         test name: char
         test type: lint, yaml, install, quality
         result: float
         result_delta: float
    original_developer_ids: one2many (contributions)
         lines_plus: integer
         lines_minus: integer
         developer: many2one
         branch: char
    review_lines_plus
    review_lines_minus
    review_developer: many2one
    review_green_commits
    review_green_lines_minus
    review_green_lines_plus

build_test_reports:
     buil_test
     buil_test left join contributions left join res.users
     buil_test left join test_steps

Test message - a line with:
    test:sale,purchase (or *)
    test-l10n:fr_BE (*)

