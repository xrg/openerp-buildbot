SELECT tstep.name, ta.name, ta.value 
    from software_dev_tsattr AS ta, software_dev_teststep AS tstep 
    WHERE ta.tstep_id = tstep.id  
      AND tstep.name = 'OpenERP-Test' ;


UPDATE software_dev_tsattr AS ta
   SET value = replace(ta.value, 'document_ftp', 'document')
    FROM software_dev_teststep AS tstep
    WHERE ta.tstep_id = tstep.id
      AND ta.name = 'force_modules'
      AND ta.value like '%document_ftp%'
      AND tstep.name = 'OpenERP-Test' ;
      
UPDATE software_dev_tsattr AS ta
    SET value = value || ' document_ftp'
    from software_dev_teststep AS tstep 
    WHERE ta.tstep_id = tstep.id
      AND ta.name = 'black_modules'
      AND ta.value not like '%document_ftp%'
      AND tstep.name = 'OpenERP-Test' ;

INSERT INTO software_dev_tsattr(tstep_id, name, value)
    SELECT tstep.id, 'black_modules', 'document_ftp'
	FROM software_dev_teststep AS tstep 
	WHERE tstep.name = 'OpenERP-Test' 
	AND NOT EXISTS ( SELECT id FROM software_dev_tsattr AS ta 
                    WHERE ta.tstep_id = tstep.id
                      AND ta.name = 'black_modules');


SELECT bseries.id
    FROM software_dev_buildseries AS bseries
    WHERE target_path = 'addons'
      AND group_id = 4
      AND NOT EXISTS (SELECT id FROM software_dev_teststep 
                        WHERE test_id = bseries.id
                          AND name = 'ProposeMerge');

INSERT INTO software_dev_teststep(test_id, name, "sequence")
    SELECT bseries.id, 'ProposeMerge', 90
    FROM software_dev_buildseries AS bseries
    WHERE target_path in ( 'addons', 'server')
      AND group_id = 4
      AND NOT EXISTS (SELECT id FROM software_dev_teststep 
                        WHERE test_id = bseries.id
                          AND name = 'ProposeMerge');

-- target_branch=target_branch, workdir=workdir, watch_lp=watch_lp, alt_branch=alt_branch
INSERT INTO software_dev_tsattr(tstep_id, name, value)
    SELECT tstep.id, attrs.name, replace(attrs.value, 'tpath', bseries.target_path)
        FROM software_dev_teststep AS tstep, software_dev_buildseries AS bseries,
            unnest(ARRAY[   ROW('target_branch'::VARCHAR, 'staging-tpath-trunk'::VARCHAR), 
                            ROW('alt_branch'::VARCHAR, '*'::VARCHAR),
                            ROW('watch_lp'::VARCHAR, 'true'::VARCHAR)]) 
                    AS attrs(name VARCHAR, value VARCHAR)
        WHERE tstep.name = 'ProposeMerge'
          AND bseries.group_id = 4
          AND bseries.id = tstep.test_id
          AND NOT EXISTS ( SELECT id FROM software_dev_tsattr AS ta 
                    WHERE ta.tstep_id = tstep.id
                      AND ta.name = attrs.name);