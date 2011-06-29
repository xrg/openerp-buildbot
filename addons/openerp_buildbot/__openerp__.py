{
    "name" : "Integration Server",
    "version" : "2.5",
    "depends" : [
                    "base",
                ],
     'description': """
    This module keeps track of all the branches to be tested.
""",
    "author" : "Tiny",
    'category': 'Generic Modules/Others',
    'website': 'http://test.openobject.com/',
    "init_xml" : [ ],
    "demo_xml" : [
                  # 'software_dev_demo.xml',
                  ],
    "update_xml" : [
                    'security/software_security.xml',
                    'security/ir.model.access.csv',
                    'buildbot_view.xml',
                    'software_dev_view.xml',
                    # 'report/buildbot_report_view.xml'
                    ],
    "installable" : True,
    "active" : False,
}
