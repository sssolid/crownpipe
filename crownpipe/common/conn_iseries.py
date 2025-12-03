import os

import jaydebeapi
import jpype
from typing import Optional


class Iseries:
    def __init__(self, server: str, user: str, password: str, database: str, jt400_jar_path: str = "jt400.jar"):
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        if not os.path.exists(jt400_jar_path):
            self.jt400_jar_path = jt400_jar_path
        else:
            try:
                self.jt400_jar_path = os.path.join(os.path.abspath(__file__), "jt400.jar")
                assert os.path.exists(self.jt400_jar_path)
                assert os.path.isfile(self.jt400_jar_path)
                print(f"Using default JT400 jar: {self.jt400_jar_path}")
            except Exception as e:
                raise Exception(f"Invalid JT400 jar path: {e}")
        self.conn: Optional[jaydebeapi.Connection] = None
        self.cursor: Optional[jaydebeapi.Cursor] = None
        self._start_jvm()

    def _start_jvm(self):
        if not jpype.isJVMStarted():
            jpype.startJVM(classpath=[self.jt400_jar_path], convertStrings=True)

    def __enter__(self):
        self.cursor = self.get_cursor()
        if self.cursor is None:
            raise RuntimeError("Failed to obtain AS400 cursor — connection or driver failed.")
        print("Connection established.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def get_cursor(self):
        try:
            driver = "com.ibm.as400.access.AS400JDBCDriver"
            jdbc_url = f"jdbc:as400://{self.server};naming=system;libraries={self.database};errors=full;date format=iso;access=read only"

            self.conn = jaydebeapi.connect(driver,
                                           jdbc_url,
                                           [self.user, self.password],
                                           self.jt400_jar_path)
            self.cursor = self.conn.cursor()
        except Exception as e:
            raise Exception(f"Iseries connection failed: {e}")
        return self.cursor
