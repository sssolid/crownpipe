"""IBM iSeries (AS/400) database connection via JDBC."""
import os
from typing import Optional

import jaydebeapi
import jpype


class Iseries:
    """
    IBM iSeries (AS/400) database connection manager.
    
    Uses JT400 JDBC driver for connectivity.
    """
    
    def __init__(self, server: str, user: str, password: str, database: str, jt400_jar_path: str = "jt400.jar"):
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        
        if not os.path.exists(jt400_jar_path):
            # Try default location
            try:
                self.jt400_jar_path = os.path.join(os.path.dirname(__file__), "jt400.jar")
                assert os.path.exists(self.jt400_jar_path)
                assert os.path.isfile(self.jt400_jar_path)
                print(f"Using JT400 jar: {self.jt400_jar_path}")
            except Exception as e:
                raise Exception(f"Invalid JT400 jar path: {e}")
        else:
            self.jt400_jar_path = jt400_jar_path
            
        self.conn: Optional[jaydebeapi.Connection] = None
        self.cursor: Optional[jaydebeapi.Cursor] = None
        self._start_jvm()

    def _start_jvm(self):
        """Start JVM if not already started."""
        if not jpype.isJVMStarted():
            jpype.startJVM(classpath=[self.jt400_jar_path], convertStrings=True)

    def __enter__(self):
        self.cursor = self.get_cursor()
        if self.cursor is None:
            raise RuntimeError("Failed to obtain AS400 cursor — connection or driver failed.")
        print("AS/400 connection established.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        """Close cursor and connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def get_cursor(self):
        """Get database cursor."""
        try:
            driver = "com.ibm.as400.access.AS400JDBCDriver"
            jdbc_url = f"jdbc:as400://{self.server};naming=system;libraries={self.database};errors=full;date format=iso;access=read only"

            self.conn = jaydebeapi.connect(
                driver,
                jdbc_url,
                [self.user, self.password],
                self.jt400_jar_path
            )
            self.cursor = self.conn.cursor()
        except Exception as e:
            raise Exception(f"iSeries connection failed: {e}")
        return self.cursor
