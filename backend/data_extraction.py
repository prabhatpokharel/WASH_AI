import zipfile
import os
import sqlite3
import pandas as pd


def extract_data(file_path, output_folder):
    """
    Extract a .swmz file into a dedicated folder within the specified output folder.

    Args:
        file_path (str): The full path to the .swmz file to be extracted.
        output_folder (str): The parent folder where extracted contents will be saved.

    Returns:
        str: The path of the folder where the file is extracted, or None if failed.
    """
    try:
        file_name_without_ext = os.path.splitext(os.path.basename(file_path))[0]
        file_output_folder = os.path.join(output_folder, file_name_without_ext)
        os.makedirs(file_output_folder, exist_ok=True)

        with zipfile.ZipFile(file_path, 'r') as zipf:
            zipf.extractall(file_output_folder)

        print(f"'{file_path}' has been successfully extracted to '{file_output_folder}'")
        return file_output_folder
    except zipfile.BadZipFile:
        print(f"Error: The file '{file_path}' is not a valid zip file.")
        return None
    except Exception as e:
        print(f"An error occurred during extraction: {e}")
        return None


def process_extracted_swmz(project_folder):
    """
    Process the extracted .swmz file and populate a table in its SQLite database.

    Args:
        project_folder (str): The folder containing the extracted .swmz contents.
    """
    projects_subfolder = 'Projects'
    photos_subfolder = 'Photos'

    # Define paths
    projects_folder = os.path.join(project_folder, projects_subfolder)
    photos_folder = os.path.join(project_folder, photos_subfolder)

    # Ensure the Projects folder exists
    if not os.path.isdir(projects_folder):
        print(f"No Projects folder found in {project_folder}. Skipping...")
        return

    # Find the .swm2 file within the Projects folder
    swm2_files = [f for f in os.listdir(projects_folder) if f.endswith('.swm2')]
    if not swm2_files:
        print(f"No .swm2 files found in {projects_folder}. Skipping...")
        return

    db_path = os.path.join(projects_folder, swm2_files[0])
    table_name = os.path.basename(project_folder)

    # Connect to the SQLite database
    conn = sqlite3.connect('NWASH_VALIDATION.db')

    try:
        # Read necessary tables
        df_fields = pd.read_sql("SELECT * FROM attribute_fields", conn)
        df_values = pd.read_sql("SELECT * FROM attribute_values", conn)
        df_features = pd.read_sql("SELECT * FROM features", conn)

        # Merge data
        df_merged = pd.merge(df_values, df_fields[['uuid', 'field_name']], left_on='field_id', right_on='uuid')

        # Drop and create table
        cursor = conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        cursor.execute(f"""
            CREATE TABLE {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT,
                field_name TEXT,
                field_value TEXT,
                feature_name TEXT,
                remarks TEXT,
                photo_path TEXT
            )
        """)

        # Insert data
        for item_id, group in df_merged.groupby('item_id'):
            for _, row in group.iterrows():
                field_name = row['field_name']
                field_value = row['value']

                # Feature info
                feature_data = df_features[df_features['uuid'] == item_id]
                feature_name = feature_data['name'].iloc[0] if not feature_data.empty else None
                remarks = feature_data['remarks'].iloc[0] if not feature_data.empty else None

                # Photo path
                photo_path = os.path.join(photos_folder, field_value) if field_value.endswith('.jpg') else None
                if photo_path and not os.path.exists(photo_path):
                    photo_path = None

                cursor.execute(f"""
                    INSERT INTO {table_name} (item_id, field_name, field_value, feature_name, remarks, photo_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (item_id, field_name, field_value, feature_name, remarks, photo_path))

        conn.commit()
        print(f"Table '{table_name}' created and populated successfully in the SQLite database.")
    except Exception as e:
        print(f"Error processing database: {e}")
    finally:
        conn.close()
