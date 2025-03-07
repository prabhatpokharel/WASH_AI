import sqlite3
import zipfile
import os

def update_project_code(db_path, new_code):
    """
    Update the ProjectCode in the project_info, project_attributes, and attribute_values tables of the database.
    
    Args:
        db_path (str): Path to the SQLite database file.
        new_code (str): New ProjectCode to set.
        
    Returns:
        bool: True if the updates succeed, False otherwise.
    """
    conn = None
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Update the ProjectCode in the project_info table
        cursor.execute("""
            UPDATE project_info
            SET value = ?
            WHERE attr = 'ProjectCode';
        """, (new_code,))
        
        # Update the Project Code in the project_attributes table
        cursor.execute("""
            UPDATE project_attributes
            SET value = ?
            WHERE attr = 'Project Code';
        """, (new_code,))

        # Update the Project Code in the attribute_values table
        cursor.execute("""
            UPDATE attribute_values
            SET value = ?
            WHERE field_id = (
                SELECT uuid FROM attribute_fields WHERE field_name = 'Project Code'
            );
        """, (new_code,))

        # Commit the changes
        conn.commit()
        print(f"ProjectCode successfully updated to {new_code}.")
        return True

    except sqlite3.OperationalError as e:
        print(f"Error updating ProjectCode: {e}")
        return False

    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

    finally:
        # Close the connection if it was successfully created
        if conn:
            conn.close()

def rename_photo_files_and_update_db(photos_path, db_path, new_code):
    """
    Rename photo files in the Photos directory to replace the old code with the new code before the '_inv' part
    and update the corresponding records in the attribute_values table in the database.
    
    Args:
        photos_path (str): Path to the Photos directory.
        db_path (str): Path to the SQLite database file.
        new_code (str): New ProjectCode to set in the filenames and database.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all filenames from the Photos directory
        photo_files = os.listdir(photos_path)
        renamed_files = []

        for file_name in photo_files:
            if '_inv' in file_name:
                parts = file_name.split('_inv', 1)
                new_name = f"{new_code}_inv{parts[1]}"

                # Rename the file
                old_file_path = os.path.join(photos_path, file_name)
                new_file_path = os.path.join(photos_path, new_name)
                os.rename(old_file_path, new_file_path)
                print(f"Renamed: {file_name} -> {new_name}")

                # Add to renamed files list
                renamed_files.append((file_name, new_name))

        # Update the database for each renamed file
        for old_name, new_name in renamed_files:
            cursor.execute("""
                UPDATE attribute_values
                SET value = ?
                WHERE value = ?;
            """, (new_name, old_name))

            if cursor.rowcount == 0:
                print(f"No matching record found in attribute_values for: {old_name}")

        # Verify that all database entries match existing files
        cursor.execute("SELECT value FROM attribute_values WHERE data_type = 'Photo';")
        db_files = [row[0] for row in cursor.fetchall()]

        for db_file in db_files:
            if db_file not in os.listdir(photos_path):
                print(f"Warning: File referenced in database not found in Photos directory: {db_file}")

        # Commit changes
        conn.commit()

    except Exception as e:
        print(f"Error renaming photo files and updating database: {e}")

    finally:
        if conn:
            conn.close()

def create_swmz_file(folder_path, output_file):
    """
    Compress the specified folder into a .swmz file.
    
    Args:
        folder_path (str): Path to the folder to compress.
        output_file (str): Name of the resulting .swmz file.
    """
    try:
        with zipfile.ZipFile(output_file, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    # Include only relevant files
                    if ('Photos' in root and file.endswith('.jpg')) or ('Projects' in root and file.endswith('.swm2')):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=folder_path)
                        zipf.write(file_path, arcname)
                        print(f"Added {file_path} as {arcname}")
        print(f"Folder '{folder_path}' compressed into '{output_file}'.")
    except Exception as e:
        print(f"Error compressing folder: {e}")

def main(db_path, folder_to_zip, output_zip, new_project_code):
    """
    Main function to update the database, rename photo files, and compress the folder into a .swmz file.
    
    Args:
        db_path (str): Path to the SQLite database file.
        folder_to_zip (str): Path to the folder to compress.
        output_zip (str): Path to the output .swmz file.
        new_project_code (str): New ProjectCode to set in the database and photo filenames.
    """
    # Step 1: Update the ProjectCode
    if not update_project_code(db_path, new_project_code):
        print("Failed to update the database. Exiting...")
        return

    # Step 2: Rename photo files and update the database
    photos_path = os.path.join(folder_to_zip, "Photos")
    if os.path.exists(photos_path):
        rename_photo_files_and_update_db(photos_path, db_path, new_project_code)
    else:
        print(f"Photos directory not found at {photos_path}.")

    # Step 3: Create the .swmz file
    create_swmz_file(folder_to_zip, output_zip)

# Configure paths and ProjectCode
database_path = "./10604006_inv/Projects/10604006_inv.swm2"  # Update this path
folder_to_zip = "./10604006_inv"                            # Update this path
output_zip = "10604006_inv.swmz"
new_code = "10604006"

# Run the main function
if __name__ == "__main__":
    main(database_path, folder_to_zip, output_zip, new_code)
