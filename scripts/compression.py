import sqlite3
import zipfile
import os

def update_project_code(db_path, new_code):
    """
    Update the ProjectCode in the project_info and project_attributes tables of the database.
    
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
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=folder_path)
                    zipf.write(file_path, arcname)
                    print(f"Added {file_path} as {arcname}")
        print(f"Folder '{folder_path}' compressed into '{output_file}'.")
    except Exception as e:
        print(f"Error compressing folder: {e}")

def main(db_path, folder_to_zip, output_zip, new_project_code):
    """
    Main function to update the database and compress the folder into a .swmz file.
    
    Args:
        db_path (str): Path to the SQLite database file.
        folder_to_zip (str): Path to the folder to compress.
        output_zip (str): Path to the output .swmz file.
        new_project_code (str): New ProjectCode to set in the database.
    """
    # Step 1: Update the ProjectCode
    if not update_project_code(db_path, new_project_code):
        print("Failed to update the database. Exiting...")
        return

    # Step 2: Compress the folder into a .swmz file
    create_swmz_file(folder_to_zip, output_zip)

# Configure paths and ProjectCode
database_path = "./10604006_inv/Projects/10604006_inv.swm2"  # Update this path
folder_to_zip = "./10604006_inv"                            # Update this path
output_zip = "10604006_inv.swmz"
new_code = "10604006"

# Run the main function
if __name__ == "__main__":
    main(database_path, folder_to_zip, output_zip, new_code)
