import csv
import datetime
import os
import jpype
import jaydebeapi

import dotenv
import pyodbc

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

class Filemaker:
    def __init__(self, dsn):
        self.dsn = dsn

    def __enter__(self):
        self.cursor = self.get_cursor()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.close()
        self.conn.close()

    def get_cursor(self):
        # Database connection to Filemaker
        try:
            self.conn = pyodbc.connect(self.dsn, timeout=10)
            self.conn.setencoding(encoding="utf8")
            self.cursor = self.conn.cursor()
            return self.cursor
        except Exception as e:
            print("Filemaker dsn connection failed: {}".format(e))

        URL = f"jdbc:filemaker://{os.getenv('FILEMAKER_SERVER')}:{os.getenv('FILEMAKER_PORT')}/{os.getenv('FILEMAKER_DATABASE')}"
        jar = os.path.abspath(os.path.join(os.path.dirname(__file__), "fmjdbc.jar"))
        jvm = jpype.getDefaultJVMPath()
        if not jpype.isJVMStarted():
            jpype.startJVM(jvm, f"-Djava.class.path={jar}")

        self.conn = jaydebeapi.connect(
            "com.filemaker.jdbc.Driver",
            URL,
            [os.getenv('FILEMAKER_USERNAME'), os.getenv('FILEMAKER_PASSWORD')]
        )
        self.conn.jconn.setReadOnly(True)
        self.cursor = self.conn.cursor()
        return self.cursor

    def fetch(self, query):
        self.cursor.execute(query)
        headers = [h[0] for h in self.cursor.description]
        rows = self.cursor.fetchall()
        rows = [
            [r.replace("\x00", "") if isinstance(r, str) else r for r in row]
            for row in rows
        ]
        result = [dict(zip(headers, row)) for row in rows]
        return result

    def get_product_numbers(self, active=True):
        """Get product numbers"""
        if active:
            self.query = "select AS400_NumberStripped AS number from Master where ToggleActive = 'Yes'"
        else:
            self.query = "select AS400_NumberStripped AS number from Master"

        self.cursor.execute(self.query)
        self.headers = self.cursor.description
        rows = self.cursor.fetchall()
        self.rows = []
        for row in rows:
            if row[0]:
                self.rows.append(row[0].strip())
        return self.rows
