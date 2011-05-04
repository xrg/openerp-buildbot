INSERT INTO  software_dev_buildbot (name, tech_code ) values ('Buildbot', 'buildbot');

INSERT INTO software_dev_buildseries(name, branch_url, 
				builder_id, 
				target_path, is_build, is_distinct, sequence )
	
	SELECT br.name, br.url, 
		(SELECT id from software_dev_buildbot WHERE tech_code = 'buildbot' LIMIT 1),
		substr(pr.name, 12), False, False, 0
	    FROM old_bbot.buildbot_lp_branch AS br,
		old_bbot.buildbot_lp_project as pr 
	    WHERE pr.id = br.lp_project_id;


INSERT INTO software_dev_commit(
select commit_rev_no, commit_rev_id, branch_id, commit_comment from buildbot_test ;