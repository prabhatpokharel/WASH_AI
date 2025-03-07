import sqlite3

def initialize_database():
    """
    Initialize the database by creating necessary tables and default admin user.
    """
    conn = sqlite3.connect('NWASH_VALIDATION.db')
    cursor = conn.cursor()

    # Create the users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT NOT NULL
        )
    ''')

    # Add the 'permission' column to users table if it doesn't exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'permission' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN permission TEXT DEFAULT 'operator'")

    # Insert default admin user with administrator permission
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password, email, phone, full_name, department, permission)
        VALUES ('admin', 'Admin@12345', 'admin@example.com', '1234567890', 'Admin User', 'Admin', 'administrator')
    ''')

    # Create the raw_data table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raw_data (
            uploaded_file_number INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            user TEXT NOT NULL,
            status TEXT DEFAULT 'not_extracted',
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    initialize_database()
    print("Database initialized successfully.")
