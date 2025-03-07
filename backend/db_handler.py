import sqlite3
from datetime import datetime
#from backend.utils import standardize_file_name


DATABASE = 'NWASH_VALIDATION.db'


def initialize_database():
    """Ensure the required tables exist in the database and standardize file names."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

        # Ensure the `users` table exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            full_name TEXT NOT NULL,
            department TEXT,
            permission TEXT DEFAULT 'operator'
        )
    ''')

    # Ensure the `file_name` column exists in the `users` table
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'file_name' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN file_name TEXT")
        print("Added 'file_name' column to the 'users' table.")

    # Ensure other required tables exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS raw_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            user TEXT NOT NULL,
            status TEXT DEFAULT 'not_extracted',
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_data (
            saved_file_number INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            user TEXT NOT NULL,
            status TEXT DEFAULT 'saved',
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pushed_data (
            saved_file_number INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            user TEXT NOT NULL,
            status TEXT DEFAULT 'pushed',
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracking (
            last_count INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS owners (
            uploaded_owner_number INTEGER PRIMARY KEY AUTOINCREMENT,
            file TEXT NOT NULL,
            users TEXT NOT NULL,
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

    # Standardize file names across tables
    standardize_file_names_in_tables()


    # Create `owners` table if it doesn't exist
    create_owners_table()

    # Synchronize `owners` with `raw_data`
    sync_owners_with_raw_data()



def authenticate_user(username, password):
    """Authenticate a user by username and password."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT full_name, department, permission FROM users WHERE username=? AND password=?
    ''', (username, password))

    user = cursor.fetchone()
    conn.close()

    if user:
        return {'full_name': user[0], 'department': user[1], 'permission': user[2]}
    return None


def add_user(username, password, email, phone, full_name, department, permission='operator'):
    """Add a new user to the database."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO users (username, password, email, phone, full_name, department, permission)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, password, email, phone, full_name, department, permission))
        conn.commit()
    except sqlite3.IntegrityError:
        return False  # Username already exists
    finally:
        conn.close()
    return True


def fetch_all_users():
    """Fetch all users from the database."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, username, email, phone, full_name, department, permission FROM users')
    users = cursor.fetchall()
    conn.close()
    return users


def delete_user(user_id):
    """Delete a user from the database by their ID."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()


def fetch_user_by_id(user_id):
    """Fetch a single user's details by their ID."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, username, email, phone, full_name, department, permission FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_details(user_id, username, email, phone, full_name, department, permission):
    """Update a user's details in the database."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE users
        SET username=?, email=?, phone=?, full_name=?, department=?, permission=?
        WHERE id=?
    ''', (username, email, phone, full_name, department, permission, user_id))

    conn.commit()
    conn.close()


def get_new_records_count():
    """
    Check if there are new records in the raw_data table.

    Returns:
        int: The number of new records since the last check.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch the count of all records
    cursor.execute("SELECT COUNT(*) FROM raw_data")
    current_count = cursor.fetchone()[0]

    # Check the last saved count
    cursor.execute("CREATE TABLE IF NOT EXISTS tracking (last_count INTEGER)")
    conn.commit()

    cursor.execute("SELECT last_count FROM tracking LIMIT 1")
    result = cursor.fetchone()

    if result is None:
        # No previous count found, initialize the count
        cursor.execute("INSERT INTO tracking (last_count) VALUES (?)", (current_count,))
        conn.commit()
        new_records = 0  # All records are considered 'old' at initialization
    else:
        last_count = result[0]
        new_records = current_count - last_count

        # Update the last count
        cursor.execute("UPDATE tracking SET last_count = ?", (current_count,))
        conn.commit()

    conn.close()
    return new_records


def create_owners_table():
    """Create the `owners` table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS owners (
            uploaded_owner_number INTEGER PRIMARY KEY AUTOINCREMENT,
            file TEXT NOT NULL,
            users TEXT NOT NULL,  -- Stored as a comma-separated list
            date_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def sync_owners_with_raw_data():
    """
    Synchronize the `owners` table with the `raw_data` table.
    Ensures every file in `raw_data` has an entry in `owners`.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch all files from raw_data
    cursor.execute('SELECT file_name, user FROM raw_data')
    raw_data_files = cursor.fetchall()

    for file_name, uploader in raw_data_files:
        # Standardize the file name
        standardized_file_name = standardize_file_name(file_name)

        # Check if the file exists in the owners table
        cursor.execute('SELECT users FROM owners WHERE file = ?', (standardized_file_name,))
        result = cursor.fetchone()

        if not result:
            # If the file doesn't exist, insert it with the uploader as the first owner
            cursor.execute(
                'INSERT INTO owners (file, users) VALUES (?, ?)',
                (standardized_file_name, uploader)
            )
        else:
            # Ensure the uploader is included in the users list
            users = result[0].split(',')
            if uploader not in users:
                users.append(uploader)
                cursor.execute(
                    'UPDATE owners SET users = ? WHERE file = ?',
                    (','.join(users), standardized_file_name)
                )

    conn.commit()
    conn.close()


def add_owner(file_name, owner):
    """
    Add an owner for a file. If the file already exists, append the owner.

    Args:
        file_name (str): The file name to associate with the owner.
        owner (str): The username of the owner.

    Returns:
        bool: True if successful, False otherwise.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Standardize the file name
    standardized_file_name = standardize_file_name(file_name)

    # Check if the file exists in the owners table
    cursor.execute("SELECT users FROM owners WHERE file = ?", (standardized_file_name,))
    result = cursor.fetchone()

    if result:
        users = result[0].split(',')
        if owner not in users:
            users.append(owner)
            cursor.execute(
                "UPDATE owners SET users = ? WHERE file = ?",
                (','.join(users), standardized_file_name)
            )
    else:
        # Insert a new record with the standardized file name
        cursor.execute(
            "INSERT INTO owners (file, users) VALUES (?, ?)",
            (standardized_file_name, owner)
        )

    conn.commit()
    conn.close()



def check_user_permission(file_name, user):
    """
    Check if a user has access to a file.

    Args:
        file_name (str): The file name to check.
        user (str): The username to verify.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT users FROM owners WHERE file = ?", (file_name,))
    result = cursor.fetchone()
    conn.close()

    if result:
        users = result[0].split(',')
        return user in users
    return False


def sync_owners_with_raw_data():
    """
    Synchronize the `owners` table with the `raw_data` table.
    Ensures every file in `raw_data` has an entry in `owners`, and file names are standardized.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch all files from raw_data
    cursor.execute('SELECT file_name, user FROM raw_data')
    raw_data_files = cursor.fetchall()

    for file_name, uploader in raw_data_files:
        # Standardize the file name
        standardized_file_name = standardize_file_name(file_name)

        # Update the `raw_data` table to use the standardized file name
        cursor.execute(
            'UPDATE raw_data SET file_name = ? WHERE file_name = ?',
            (standardized_file_name, file_name)
        )

        # Check if the file exists in the owners table
        cursor.execute('SELECT users FROM owners WHERE file = ?', (standardized_file_name,))
        result = cursor.fetchone()

        if not result:
            # If the file doesn't exist, insert it with the uploader as the first owner
            cursor.execute(
                'INSERT INTO owners (file, users) VALUES (?, ?)',
                (standardized_file_name, uploader)
            )
        else:
            # Ensure the uploader is included in the users list
            users = result[0].split(',')
            if uploader not in users:
                users.append(uploader)
                cursor.execute(
                    'UPDATE owners SET users = ? WHERE file = ?',
                    (','.join(users), standardized_file_name)
                )

    conn.commit()
    conn.close()


def standardize_file_name(file_name):
    """
    Standardize file names by removing only known extensions.

    Args:
        file_name (str): The file name to standardize.

    Returns:
        str: The standardized file name without extensions.
    """
    return file_name.split('_inv.swmz')[0] if '_inv.swmz' in file_name else file_name


def remove_file_extension(file_name):
    """
    Standardize file names by removing known extensions and ensuring consistent formatting.

    Args:
        file_name (str): The file name to standardize.

    Returns:
        str: The standardized file name without extensions.
    """
    known_extensions = ['.swmz', '.json', '.swm2']
    for ext in known_extensions:
        if file_name.endswith(ext):
            file_name = file_name.rsplit(ext, 1)[0]
    return file_name


def standardize_file_names_in_tables():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Update file names in `raw_data` table
    cursor.execute("SELECT id, file_name FROM raw_data")
    raw_data_records = cursor.fetchall()
    for record_id, file_name in raw_data_records:
        standardized_name = standardize_file_name(file_name)
        if file_name != standardized_name:
            cursor.execute(
                "UPDATE raw_data SET file_name = ? WHERE id = ?",
                (standardized_name, record_id)
            )

    # Update file names in `saved_data` table
    cursor.execute("SELECT saved_file_number, file_name FROM saved_data")
    saved_data_records = cursor.fetchall()
    for record_id, file_name in saved_data_records:
        standardized_name = standardize_file_name(file_name)
        if file_name != standardized_name:
            cursor.execute(
                "UPDATE saved_data SET file_name = ? WHERE saved_file_number = ?",
                (standardized_name, record_id)
            )

    # Update file names in `owners` table
    cursor.execute("SELECT uploaded_owner_number, file FROM owners")
    owners_records = cursor.fetchall()
    for record_id, file_name in owners_records:
        standardized_name = standardize_file_name(file_name)
        if file_name != standardized_name:
            cursor.execute(
                "UPDATE owners SET file = ? WHERE uploaded_owner_number = ?",
                (standardized_name, record_id)
            )

    conn.commit()
    conn.close()


# def save_data(file_name, user, status='saved'):
#     """
#     Add or update a record in the saved_data table.

#     Args:
#         file_name (str): The file name to save or update.
#         user (str): The user saving the data.
#         status (str): The status of the file. Default is 'saved'.
#     """
#     conn = sqlite3.connect(DATABASE)
#     cursor = conn.cursor()

#     # Standardize the file name
#     standardized_file_name = standardize_file_name(file_name)
#     print(f"save_data called with standardized_file_name: {standardized_file_name}, user: {user}, status: {status}")

#     # Check if the file already exists in the table
#     cursor.execute("SELECT saved_file_number FROM saved_data WHERE file_name = ?", (standardized_file_name,))
#     existing_record = cursor.fetchone()

#     if existing_record:
#         # Update existing record
#         print(f"Updating existing record in saved_data for file_name: {standardized_file_name}")
#         cursor.execute("""
#             UPDATE saved_data
#             SET user = ?, status = ?, date_time = CURRENT_TIMESTAMP
#             WHERE file_name = ?
#         """, (user, status, standardized_file_name))
#     else:
#         # Insert new record
#         print(f"Inserting new record into saved_data for file_name: {standardized_file_name}")
#         cursor.execute("""
#             INSERT INTO saved_data (file_name, user, status, date_time)
#             VALUES (?, ?, ?, CURRENT_TIMESTAMP)
#         """, (standardized_file_name, user, status))

#     conn.commit()
#     conn.close()
#     print(f"save_data completed for file_name: {standardized_file_name}")

def save_data(file_name, user, status='saved'):
    """
    Add or update a record in the saved_data table.

    Args:
        file_name (str): The file name to save or update.
        user (str): The user saving the data.
        status (str): The status of the file. Default is 'saved'.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Standardize the file name (removing the .json extension)
    standardized_file_name = remove_file_extension(file_name)
    print(f"save_data called with standardized_file_name: {standardized_file_name}, user: {user}, status: {status}")

    # Check if the file already exists in the table
    cursor.execute("SELECT saved_file_number FROM saved_data WHERE file_name = ?", (standardized_file_name,))
    existing_record = cursor.fetchone()

    if existing_record:
        # Update existing record
        print(f"Updating existing record in saved_data for file_name: {standardized_file_name}")
        cursor.execute("""
            UPDATE saved_data
            SET user = ?, status = ?, date_time = CURRENT_TIMESTAMP
            WHERE file_name = ?
        """, (user, status, standardized_file_name))
    else:
        # Insert new record
        print(f"Inserting new record into saved_data for file_name: {standardized_file_name}")
        cursor.execute("""
            INSERT INTO saved_data (file_name, user, status, date_time)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (standardized_file_name, user, status))

    conn.commit()
    conn.close()
    print(f"save_data completed for file_name: {standardized_file_name}")


def save_file_for_user(user_full_name, file_name):
    print(f"Saving file '{file_name}' for user '{user_full_name}'")  # Debug log
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        # Update the file_name for the user
        cursor.execute('''
            UPDATE users
            SET file_name = ?
            WHERE full_name = ?
        ''', (file_name, user_full_name))
        conn.commit()
        print(f"File '{file_name}' successfully saved for user '{user_full_name}'")  # Debug log
    except Exception as e:
        print(f"Error while saving file: {e}")  # Debug log
    finally:
        conn.close()




# Initialize the database tables
initialize_database()
