import os
import sqlite3
import pandas as pd
import json
from datetime import datetime
from backend.data_extraction import extract_data


class FileManager:
    RAW_DATA_FOLDER = './raw_data'
    EXTRACTED_DATA_FOLDER = './extracted_data'
    JSON_FOLDER = './json_reports'
    DATABASE = 'NWASH_VALIDATION.db'

    def __init__(self):
        os.makedirs(self.RAW_DATA_FOLDER, exist_ok=True)
        os.makedirs(self.EXTRACTED_DATA_FOLDER, exist_ok=True)
        os.makedirs(self.JSON_FOLDER, exist_ok=True)
        print(f"JSON folder initialized at: {self.JSON_FOLDER}")

    def handle_upload(self, file, uploaded_by):
        """Handle a new file upload."""
        file_path = os.path.join(self.RAW_DATA_FOLDER, file.filename)
        print(f"Handling upload for file: {file.filename}")

        if os.path.exists(file_path):
            print(f"File '{file.filename}' already exists at {file_path}.")
            return {
                "status": "exists",
                "message": f"File '{file.filename}' already exists. Would you like to overwrite it?",
            }

        # Save the file
        try:
            file.save(file_path)
            print(f"File '{file.filename}' successfully saved at {file_path}.")
        except Exception as e:
            print(f"Error saving file '{file.filename}': {e}")
            return {
                "status": "error",
                "message": f"Failed to save file '{file.filename}'.",
            }

        conn = sqlite3.connect(self.DATABASE)
        cursor = conn.cursor()

        try:
            # Save record in the database
            cursor.execute("""
                INSERT INTO raw_data (file_name, user, status, date_time)
                VALUES (?, ?, ?, ?)
            """, (file.filename, uploaded_by, "not_extracted", datetime.now()))
            conn.commit()
            print(f"Database record added for file: {file.filename}.")

            # Extract the file
            extracted_folder = extract_data(file_path, self.EXTRACTED_DATA_FOLDER)
            if extracted_folder and os.path.exists(extracted_folder):
                print(f"File successfully extracted to {extracted_folder}.")
                # Generate JSON
                self.generate_json(extracted_folder)
                cursor.execute("""
                    UPDATE raw_data
                    SET status = 'extracted'
                    WHERE file_name = ?
                """, (file.filename,))
                conn.commit()
                print(f"Database updated with extraction status for file: {file.filename}.")
            else:
                print(f"Extraction failed for file: {file.filename}.")
                return {
                    "status": "error",
                    "message": f"Extraction failed for file '{file.filename}'.",
                }
        except Exception as e:
            print(f"Error during file upload processing: {e}")
            return {
                "status": "error",
                "message": f"An error occurred while processing '{file.filename}': {e}",
            }
        finally:
            conn.close()

        return {"status": "success", "message": f"File '{file.filename}' uploaded and processed successfully."}

    def generate_json(self, project_folder):
        """Generate JSON file from the SQLite database in the extracted project folder."""
        print(f"Starting JSON generation for folder: {project_folder}")
        projects_folder = os.path.join(project_folder, "Projects")
        photos_folder = os.path.join(project_folder, "Photos")
        report_folder = self.JSON_FOLDER

        # Ensure JSON folder exists
        os.makedirs(report_folder, exist_ok=True)

        # Locate .swm2 file
        swm2_files = [f for f in os.listdir(projects_folder) if f.endswith(".swm2")]
        print(f".swm2 files found in {projects_folder}: {swm2_files}")
        if not swm2_files:
            print(f"No .swm2 files found in {projects_folder}. JSON generation aborted.")
            return

        db_path = os.path.join(projects_folder, swm2_files[0])
        folder_name = os.path.basename(project_folder)
        json_file_path = os.path.join(report_folder, f"{folder_name}.json")

        conn = sqlite3.connect(db_path)
        try:
            # Read tables from database
            print(f"Connecting to SQLite database: {db_path}")
            df_fields = pd.read_sql("SELECT * FROM attribute_fields", conn)
            df_values = pd.read_sql("SELECT * FROM attribute_values", conn)
            df_project_info = pd.read_sql("SELECT * FROM project_info", conn)
            df_features = pd.read_sql("SELECT * FROM features", conn)
            df_points = pd.read_sql("SELECT * FROM points", conn)

            # Debugging - Check table data
            print("Loaded data samples:")
            print("attribute_fields:", df_fields.head())
            print("attribute_values:", df_values.head())
            print("project_info:", df_project_info.head())
            print("features:", df_features.head())
            print("points:", df_points.head())

            # Validate if required data exists
            if df_fields.empty or df_values.empty:
                print(f"Required data missing in database: fields or values are empty.")
                return
            if df_project_info.empty:
                print("Project info table is empty. Cannot generate project information.")
                return

            # Merge and categorize data
            df_merged = pd.merge(df_values, df_fields[['uuid', 'field_name']], left_on='field_id', right_on='uuid')
            categorized_items = self.categorize_data(df_merged, df_features, df_points, photos_folder)

            # Convert project_info to dictionary
            project_info_dict = df_project_info.set_index('attr')['value'].to_dict()

            # Write JSON
            output_json = {
                "project_info": project_info_dict,
                "items": categorized_items,
            }
            print(f"Writing JSON to {json_file_path}")
            with open(json_file_path, "w", encoding="utf-8") as json_file:
                json.dump(output_json, json_file, indent=4, ensure_ascii=False)
            print(f"JSON file successfully created: {json_file_path}")
        except pd.io.sql.DatabaseError as db_err:
            print(f"Database error while reading tables: {db_err}")
        except Exception as e:
            print(f"Error during JSON generation: {e}")
        finally:
            conn.close()

    @staticmethod
    def categorize_data(df_merged, df_features, df_points, photos_folder):
        """Categorize data into relevant sections for JSON."""
        categorized = {
            "Source Name": [],
            "Structure Type": [],
            "Junction": [],
            "Pipe Function": [],
            "Taps": [],
        }

        for item_id, group in df_merged.groupby("item_id"):
            item_data = {row["field_name"]: row["value"] for _, row in group.iterrows()}

            # Add photo paths
            for field_name, field_value in item_data.items():
                if isinstance(field_value, str) and field_value.endswith(".jpg"):
                    photo_path = os.path.join(photos_folder, field_value)
                    item_data[field_name] = photo_path if os.path.exists(photo_path) else f"{field_value} not found"

            # Add feature and geospatial data
            feature_data = df_features[df_features["uuid"] == item_id]
            point_data = df_points[df_points["fid"] == item_id]

            if not feature_data.empty:
                item_data["feature_info"] = feature_data[["name", "remarks"]].to_dict("records")[0]
            if not point_data.empty:
                item_data["geospatial_data"] = point_data[["lat", "lon", "elv", "time", "pos_data"]].to_dict("records")

            # Categorize by specific field
            for category in categorized.keys():
                if category in item_data:
                    categorized[category].append(item_data)
                    break

            # Special logic to identify Taps (if not already categorized)
            if "Tap No" in item_data:
                categorized["Taps"].append(item_data)

        # Debugging categorized data
        print("Categorized data (partial):")
        for category, items in categorized.items():
            print(f"{category}: {len(items)} items")

        return categorized

    @staticmethod
    def delete_related_files(base_name):
        """
        Delete all related files for a given base file name from the respective folders.

        Args:
            base_name (str): The base file name (e.g., '10604003_inv') without extensions.
        """
        # Define the folders
        base_path = "./"
        progress_folder = os.path.join(base_path, "progress")
        json_reports_folder = os.path.join(base_path, "json_reports")
        extracted_data_folder = os.path.join(base_path, "extracted_data")
        raw_data_folder = os.path.join(base_path, "raw_data")
        saved_data_folder = os.path.join(base_path, "saved_data")

        # Define files and folders to delete
        files_to_delete = [
            os.path.join(progress_folder, f"{base_name}.json_progress.json"),
            os.path.join(json_reports_folder, f"{base_name}.json"),
            os.path.join(raw_data_folder, f"{base_name}.swmz"),
            os.path.join(saved_data_folder, f"{base_name}.swmz"),
        ]

        folders_to_delete = [
            os.path.join(extracted_data_folder, base_name)
        ]

        # Delete files
        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                else:
                    print(f"File not found, skipping: {file_path}")
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")

        # Delete folders
        for folder_path in folders_to_delete:
            try:
                if os.path.exists(folder_path):
                    for root, dirs, files in os.walk(folder_path, topdown=False):
                        for file in files:
                            os.remove(os.path.join(root, file))
                        os.rmdir(root)
                    os.rmdir(folder_path)
                    print(f"Deleted folder: {folder_path}")
                else:
                    print(f"Folder not found, skipping: {folder_path}")
            except Exception as e:
                print(f"Error deleting folder {folder_path}: {e}")