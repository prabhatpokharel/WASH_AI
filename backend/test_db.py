import sqlite3
import os

def inspect_database(db_path):
    """
    Inspect the database to list all tables and columns for debugging.

    Args:
        db_path (str): Path to the SQLite database file.
    """
    if not os.path.exists(db_path):
        print(f"Error: Database file does not exist at path: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables in the database: {[table[0] for table in tables]}")

        # Inspect the project_info table, if it exists
        if ('project_info',) in tables:
            cursor.execute("PRAGMA table_info(project_info);")
            columns = cursor.fetchall()
            print(f"Columns in 'project_info' table: {columns}")
        else:
            print("The 'project_info' table does not exist in the database.")
    except sqlite3.Error as e:
        print(f"Error while inspecting the database: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


db_path = './temp_uploads/extracted_data_temp/40908163_inv/Projects/40908163_inv.swm2'
inspect_database(db_path)
