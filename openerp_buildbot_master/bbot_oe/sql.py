import psycopg2
from psycopg2.psycopg1 import cursor

class db_connection(object):
    def __init__(self, dbname, user='tiny'):
        self.dbname = dbname
        self.user = user
        self.dsn = self._dsn()        
    def _dsn(self):
        return 'user=%s dbname=%s' % (self.user, self.dbname)
    def _get_cnx(self):
        cnx = psycopg2.connect(dsn=self.dsn)
        return cnx
    def executemany(self, query, args):
        cnx = self._get_cnx()
        cr = cnx.cursor()
        cr.executemany(query, args)
        cnx.commit()
        q="SELECT MAX(id) from buildbot_test"
        cr.execute(q)
        id=cr.fetchone()[0]
        cnx.close()
        return id
    def execute(self, query):
        cnx = self._get_cnx()
        cr = cnx.cursor()
        cr.execute(query)
        cnx.commit()
        q="SELECT MAX(id) from buildbot_test_step"
        cr.execute(q)
        id=cr.fetchone()[0]
        cnx.close()
        return id
    def get_only_rows(self, query):
        cnx = self._get_cnx()
        cr = cnx.cursor()
        cr.execute(query)
        return cr.fetchall()
    def get_only_columns(self, query):
        cnx = self._get_cnx()
        cr = cnx.cursor()
        cr.execute(query)
        return [col[0] for col in cr.description]
    def get_rows_and_columns(self, query):
        cnx = self._get_cnx()
        cr = cnx.cursor()
        cr.execute(query)
        rows = cr.fetchall()
        cols = [col[0] for col in cr.description]
        return rows, cols