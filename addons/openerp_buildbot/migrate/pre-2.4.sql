CREATE SCHEMA old_bbot;

ALTER TABLE buildbot_lp_branch set SCHEMA old_bbot;
ALTER TABLE buildbot_lp_user SET SCHEMA old_bbot;
ALTER TABLE buildbot_test_step SET SCHEMA old_bbot;
ALTER TABLE buildbot_lp_group SET SCHEMA old_bbot;
ALTER TABLE buildbot_lp_users_groups_rel SET SCHEMA old_bbot;
ALTER TABLE buildbot_lp_project SET SCHEMA old_bbot;
ALTER TABLE buildbot_test SET SCHEMA old_bbot;

-- ALTER TABLE  SET SCHEMA old_bbot
