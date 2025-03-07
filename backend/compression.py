import zipfile
import os
import sqlite3
import json
import shutil
from backend.db_handler import standardize_file_name

def update_database_with_json(json_file_path, db_path):
    """
    Update the SQLite database with values from the JSON file.

    Args:
        json_file_path (str): Path to the JSON file containing updated data.
        db_path (str): Path to the SQLite database to update.
    """
    print(f"Updating database using JSON file: {json_file_path}")
    print(f"Target database: {db_path}")

    if not os.path.exists(json_file_path):
        raise FileNotFoundError(f"JSON file '{json_file_path}' does not exist.")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file '{db_path}' does not exist.")

    # Load JSON data
    with open(json_file_path, 'r', encoding='utf-8') as json_file:
        data = json.load(json_file)

    taps = data.get("items", {}).get("Taps", [])
    if not taps:
        print("No 'Taps' data found in JSON. Skipping database update.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Fetch the UUID for "Tap No" and "Tap Condition" from the attribute_fields table
        cursor.execute("SELECT uuid FROM attribute_fields WHERE field_name = 'Tap No';")
        tap_no_uuid = cursor.fetchone()
        
        cursor.execute("SELECT uuid FROM attribute_fields WHERE field_name = 'Tap Condition';")
        tap_condition_uuid = cursor.fetchone()

        if not tap_no_uuid or not tap_condition_uuid:
            print("Required fields ('Tap No' or 'Tap Condition') not found in attribute_fields table. Skipping database update.")
            return

        tap_no_uuid = tap_no_uuid[0]
        tap_condition_uuid = tap_condition_uuid[0]

        print(f"Tap No UUID: {tap_no_uuid}")
        print(f"Tap Condition UUID: {tap_condition_uuid}")

        # Build a mapping of Tap No to item_id from the database
        cursor.execute("SELECT item_id, value FROM attribute_values WHERE field_id = ?;", (tap_no_uuid,))
        db_tap_mapping = {row[1]: row[0] for row in cursor.fetchall()}  # Map Tap No to item_id

        changed_records = []

        for tap in taps:
            tap_no = tap.get("Tap No")
            tap_condition = tap.get("Tap Condition")

            if tap_no and tap_condition:
                item_id = db_tap_mapping.get(str(tap_no))  # Find corresponding item_id for the Tap No
                if item_id:
                    # Check current value in the database
                    cursor.execute(
                        "SELECT value FROM attribute_values WHERE field_id = ? AND item_id = ?;",
                        (tap_condition_uuid, item_id),
                    )
                    current_value = cursor.fetchone()

                    if current_value and current_value[0] != tap_condition:
                        print(f"Updating Tap No: {tap_no} from '{current_value[0]}' to '{tap_condition}'")
                        cursor.execute(
                            "UPDATE attribute_values SET value = ? WHERE field_id = ? AND item_id = ?;",
                            (tap_condition, tap_condition_uuid, item_id),
                        )
                        changed_records.append((tap_no, current_value[0], tap_condition))
                    else:
                        print(f"No change needed for Tap No: {tap_no}")
                else:
                    print(f"Tap No: {tap_no} not found in the database.")
            else:
                print(f"Skipping Tap No: {tap_no} due to missing data.")

        conn.commit()

        if changed_records:
            print("\nChanged Records:")
            for record in changed_records:
                print(f"Tap No: {record[0]}, Old Value: {record[1]}, New Value: {record[2]}")
        else:
            print("No records were changed in the database.")
    except sqlite3.Error as e:
        print(f"SQLite error during database update: {e}")
        raise
    finally:
        conn.close()



def compress_project_folder(project_code, extracted_data_folder, saved_data_folder, json_file_path=None):
    """
    Compress a project folder into a .swmz file, including updates from a JSON file.
    """
    try:
        # Ensure project_code does not end with '_inv' twice
        standardized_project_code = (
            project_code[:-4] if project_code.endswith("_inv") and project_code[-8:-4] == "_inv" else project_code
        )

        # Define the folder to compress and the target .swmz file
        folder_to_compress = os.path.join(extracted_data_folder, standardized_project_code)
        target_zip_file = os.path.join(saved_data_folder, f"{standardized_project_code}.swmz")

        print(f"Compressing project: {standardized_project_code}")
        print(f"Folder to compress: {folder_to_compress}")
        print(f"Target ZIP file: {target_zip_file}")

        # Resolve database path early in the function to avoid redundancy
        db_path = os.path.join(folder_to_compress, "Projects", f"{standardized_project_code}.swm2")

        # Check if the folder exists
        if not os.path.exists(folder_to_compress):
            raise FileNotFoundError(f"Project folder '{folder_to_compress}' does not exist.")

        # If a JSON file is provided, integrate it into the database (if applicable)
        if json_file_path:
            print(f"JSON file path provided: {json_file_path}")
            print(f"Database path resolved: {db_path}")

            if os.path.exists(db_path) and os.path.exists(json_file_path):
                print(f"Both JSON file and database file exist. Proceeding with update.")
                update_database_with_json(json_file_path, db_path)
            else:
                print(f"JSON file or database file does not exist. Skipping update.")

        # Compress the folder into the .swmz file
        with zipfile.ZipFile(target_zip_file, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for root, dirs, files in os.walk(folder_to_compress):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=folder_to_compress)
                    zipf.write(file_path, arcname)

        print(f"Project compressed successfully: {target_zip_file}")
        return target_zip_file, True

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise



