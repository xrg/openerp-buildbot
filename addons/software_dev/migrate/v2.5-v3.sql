CREATE SCHEMA soft_dev;


ALTER TABLE software_dev_branch_dep_rel SET SCHEMA soft_dev ;
ALTER TABLE software_dev_buildscheduler SET SCHEMA soft_dev ;
ALTER TABLE software_dev_buildseries SET SCHEMA soft_dev ;
ALTER TABLE software_dev_build SET SCHEMA soft_dev ;
ALTER TABLE software_dev_changestats SET SCHEMA soft_dev ;
ALTER TABLE software_dev_commit_authors_rel SET SCHEMA soft_dev ;
ALTER TABLE software_dev_commit SET SCHEMA soft_dev ;
ALTER TABLE software_dev_filechange SET SCHEMA soft_dev ;
ALTER TABLE software_dev_mergerequest SET SCHEMA soft_dev ;
ALTER TABLE software_dev_property SET SCHEMA soft_dev ;
ALTER TABLE software_dev_sched_change SET SCHEMA soft_dev ;
ALTER TABLE software_dev_test_result SET SCHEMA soft_dev ;
ALTER TABLE software_dev_teststep SET SCHEMA soft_dev ;
ALTER TABLE software_dev_tsattr SET SCHEMA soft_dev ;
ALTER TABLE software_dev_vcs_user SET SCHEMA soft_dev ;


-- ALTER TABLE software_dev_bbslave SET SCHEMA soft_dev ;
-- ALTER TABLE software_dev_buildbot SET SCHEMA soft_dev ;
-- ALTER TABLE software_dev_battr SET SCHEMA soft_dev ;
CREATE TABLE software_dev_builder (
    id SERIAL PRIMARY KEY,
    create_uid INTEGER REFERENCES res_users(id),
    create_date TIMESTAMP WITHOUT TIME ZONE,
    write_date TIMESTAMP WITHOUT TIME ZONE,
    write_uid INTEGER REFERENCES res_users(id),
    description TEXT,
    name VARCHAR(64) NOT NULL);

INSERT INTO software_dev_builder (id, create_uid, create_date, write_date, write_uid, name, description)
    SELECT id, create_uid, create_date, write_date, write_uid, name, description
	FROM software_dev_buildbot;

*-* sequence 

ALTER TABLE software_dev_buildbot ADD
    builder_id INTEGER REFERENCES software_dev_builder(id);

UPDATE software_dev_buildbot SET builder_id = id;
ALTER TABLE software_dev_buildbot ALTER builder_id SET NOT NULL;

ALTER TABLE software_dev_buildbot DROP COLUMN name, DROP COLUMN description;


-- ALTER TABLE software_dev_buildgroup SET SCHEMA soft_dev ;


-- eof
