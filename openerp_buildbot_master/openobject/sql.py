import psycopg2
from psycopg2.psycopg1 import cursor

class db_connection(object):
    def __init__(self, dbname, user='tiny'):
        self.dbname = dbname
        self.user = user
        self.dsn = self._dsn()
        self.cnx = self._get_cnx()
        self.cr = self.cnx.cursor()
    def _dsn(self):
        return 'user=%s dbname=%s' % (self.user, self.dbname)
    def _get_cnx(self):
        cnx = psycopg2.connect(dsn=self.dsn)
        return cnx
    def execute(self, query):
        self.cr.execute(query)
        self.cnx.commit()
    def get_only_rows(self, query):
        self.execute(query)
        return self.cr.fetchall()
    def get_only_columns(self, query):
        self.execute(query)
        return [col[0] for col in self.cr.description]
    def get_rows_and_columns(self, query):
        self.execute(query)
        rows = self.cr.fetchall()
        cols = [col[0] for col in self.cr.description]
        return rows, cols