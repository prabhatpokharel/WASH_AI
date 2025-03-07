import os
import zipfile
import sqlite3
import shutil


def extract_data_temporarily(file_path, temp_output_folder):
    """
    Extract the content of the uploaded .swmz file into a temporary folder.

    Args:
        file_path (str): Path to the .swmz file.
        temp_output_folder (str): Temporary folder to extract the contents.

    Returns:
        str: Path to the extracted temporary folder or None if extraction fails.
    """
    try:
        file_name_without_ext = os.path.splitext(os.path.basename(file_path))[0]
        temp_folder = os.path.join(temp_output_folder, file_name_without_ext)
        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)  # Clean any existing temp folder
        os.makedirs(temp_folder, exist_ok=True)

        # Extract the file into the temporary folder
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_folder)

        print(f"Extracted '{file_path}' temporarily to '{temp_folder}'.")
        print(f"Contents of extracted folder: {os.listdir(temp_folder)}")  # Debugging log
        return temp_folder
    except zipfile.BadZipFile:
        print(f"Error: The file '{file_path}' is not a valid zip file.")
        return None
    except Exception as e:
        print(f"An error occurred during temporary extraction: {e}")
        return None



def validate_project_code_and_structure(extracted_folder, uploaded_file_name):
    """
    Validate the ProjectCode and folder structure of the extracted file.

    Args:
        extracted_folder (str): Path to the extracted temporary folder.
        uploaded_file_name (str): Name of the uploaded .swmz file.

    Returns:
        bool: True if validation is successful, False otherwise.
    """
    try:
        # Extract the project code from the file name
        project_code_from_file = uploaded_file_name.split('_')[0]  # Example: 40908162_inv.swmz -> 40908162

        # Validate the structure directly in the extracted folder
        photos_folder = os.path.join(extracted_folder, "Photos")
        projects_folder = os.path.join(extracted_folder, "Projects")
        if not os.path.isdir(photos_folder) or not os.path.isdir(projects_folder):
            print(f"Validation error: Required subfolders 'Photos' and 'Projects' are missing in '{extracted_folder}'.")
            return False

        # Find and validate the .swm2 database file
        swm2_files = [f for f in os.listdir(projects_folder) if f.endswith('.swm2')]
        if not swm2_files:
            print(f"Validation error: No '.swm2' database file found in '{projects_folder}'.")
            return False
        db_path = os.path.join(projects_folder, swm2_files[0])

        # Validate the database and ProjectCode
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Ensure the table `project_info` exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_info';")
        if not cursor.fetchone():
            print("Validation error: Table 'project_info' is missing in the database.")
            return False

        # Fetch the ProjectCode from the database
        cursor.execute("SELECT value FROM project_info WHERE attr = 'ProjectCode' LIMIT 1")
        project_code_from_db = cursor.fetchone()

        if not project_code_from_db or project_code_from_db[0] != project_code_from_file:
            print(f"Validation error: ProjectCode mismatch. Expected '{project_code_from_file}', found '{project_code_from_db[0] if project_code_from_db else 'None'}'.")
            return False

        print(f"Validation successful: ProjectCode matches and folder structure is correct.")
        return True

    except Exception as e:
        print(f"Validation error: {e}")
        return False

    finally:
        if 'conn' in locals():
            conn.close()


def validate_database_schema_and_project_code(db_path, expected_project_code):
    """
    Validate the schema and ProjectCode in the .swm2 database file.

    Args:
        db_path (str): Path to the .swm2 database.
        expected_project_code (str): The ProjectCode expected from the file name.

    Raises:
        ValueError: If validation fails.
    """
    required_tables = ["project_info", "another_required_table"]  # Add all required table names here

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Validate the presence of required tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]
        for table in required_tables:
            if table not in existing_tables:
                raise ValueError(f"Table '{table}' is missing in the database '{db_path}'.")

        # Validate the ProjectCode
        cursor.execute("SELECT value FROM project_info WHERE attr = 'ProjectCode' LIMIT 1")
        project_code_from_db = cursor.fetchone()
        if not project_code_from_db or project_code_from_db[0] != expected_project_code:
            raise ValueError(
                f"ProjectCode mismatch: expected '{expected_project_code}', found '{project_code_from_db[0] if project_code_from_db else 'None'}'."
            )

        print(f"Database validation successful: ProjectCode '{expected_project_code}' matches.")
    finally:
        conn.close()


def cleanup_temporary_folder(temp_folder):
    """
    Remove the temporary folder after validation.

    Args:
        temp_folder (str): Path to the temporary folder.
    """
    try:
        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)
            print(f"Temporary folder '{temp_folder}' cleaned up successfully.")
    except Exception as e:
        print(f"Error while cleaning up temporary folder: {e}")


# Add this logic in your `upload_file` function in `app.py` to invoke the validation
def validate_and_process_upload(file_path, temp_upload_folder, raw_data_folder, extracted_data_folder):
    """
    Validate the uploaded SWMZ file and process it.

    Args:
        file_path (str): Path to the uploaded .swmz file.
        temp_upload_folder (str): Temporary folder to extract the contents for validation.
        raw_data_folder (str): Folder where valid files are stored.
        extracted_data_folder (str): Folder where the file is extracted for further use.

    Returns:
        str: Message indicating the result of validation and processing.
    """
    extracted_temp_folder = None
    try:
        # Extract temporarily
        extracted_temp_folder = extract_data_temporarily(file_path, temp_upload_folder)
        if not extracted_temp_folder:
            return "File extraction failed. Invalid .swmz file."

        # Validate project structure and ProjectCode
        if not validate_project_code_and_structure(extracted_temp_folder, os.path.basename(file_path)):
            return "Validation failed. Incorrect file structure or ProjectCode mismatch."

        # Move valid file to raw_data and extract again
        raw_file_path = os.path.join(raw_data_folder, os.path.basename(file_path))
        shutil.move(file_path, raw_file_path)
        extract_data(raw_file_path, extracted_data_folder)
        return "File validated and processed successfully."
    except Exception as e:
        return f"An error occurred: {e}"
    finally:
        cleanup_temporary_folder(extracted_temp_folder)
