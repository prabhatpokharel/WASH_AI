from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify, send_from_directory
from backend.db_handler import (
    authenticate_user,
    add_user,
    fetch_all_users,
    delete_user,
    fetch_user_by_id,
    update_user_details,
    get_new_records_count,
    add_owner,  # Import add_owner
    check_user_permission,  # Import check_user_permission if not already imported
    sync_owners_with_raw_data,
    save_data,
    standardize_file_name,
    remove_file_extension,
    save_file_for_user

)
from backend.file_manager import FileManager
from datetime import timedelta
import os
import sqlite3
import json
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from backend.data_extraction import extract_data
from backend.file_validation import extract_data_temporarily, validate_project_code_and_structure, cleanup_temporary_folder
from backend.compression import compress_project_folder
from backend.predict_anomaly import process_json  # Import process_json

EXTRACTED_DATA_FOLDER = './extracted_data'
SAVED_DATA_FOLDER = './saved_data'

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.permanent_session_lifetime = timedelta(minutes=30)

UPLOAD_FOLDER = './temp_uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Ensure the temp directory exists

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

file_manager = FileManager()

# ----------- Authentication Routes -----------
@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user = authenticate_user(username, password)
    if user:
        session['user'] = user
        return redirect('/admin-dashboard' if user['permission'] == 'administrator' else '/home')
    return render_template('error.html', message="Invalid username or password.")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# ----------- User Management Routes -----------
@app.route('/admin-dashboard')
def admin_dashboard():
    """Route for the admin dashboard."""
    user = session.get('user')
    if not user or user['permission'] != 'administrator':
        return redirect('/')
    users = fetch_all_users()
    return render_template('admin_dashboard.html', users=users)

@app.route('/add-user', methods=['POST'])
def add_user_route():
    """Handle adding a new user from the admin dashboard."""
    user = session.get('user')
    if not user or user['permission'] != 'administrator':
        return redirect('/')
    username = request.form['username']
    password = request.form['password']
    email = request.form['email']
    phone = request.form['phone']
    full_name = request.form['full_name']
    department = request.form['department']
    permission = request.form['permission']
    success = add_user(username, password, email, phone, full_name, department, permission)
    if not success:
        return render_template('error.html', message="User already exists.")
    flash("User successfully added!")
    return redirect('/admin-dashboard')

@app.route('/edit-user/<int:user_id>')
def edit_user_page(user_id):
    """Render the edit user form."""
    user = fetch_user_by_id(user_id)
    if not user or 'user' not in session or session['user']['permission'] != 'administrator':
        return redirect('/')
    return render_template('edit_user.html', user=user)

@app.route('/edit-user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    """Handle updating user details."""
    if 'user' not in session or session['user']['permission'] != 'administrator':
        return redirect('/')
    username = request.form['username']
    email = request.form['email']
    phone = request.form['phone']
    full_name = request.form['full_name']
    department = request.form['department']
    permission = request.form['permission']
    update_user_details(user_id, username, email, phone, full_name, department, permission)
    flash("User successfully updated!")
    return redirect('/admin-dashboard')

@app.route('/delete-user', methods=['POST'])
def delete_user_route():
    """Handle deleting a user from the admin dashboard."""
    user = session.get('user')
    if not user or user['permission'] != 'administrator':
        return redirect('/')
    user_id = request.form['user_id']
    delete_user(user_id)
    flash("User successfully deleted!")
    return redirect('/admin-dashboard')


@app.route('/home')
def home():
    """Route for the user's home page."""
    user = session.get('user')
    if not user:
        return redirect('/')

    conn = sqlite3.connect(file_manager.DATABASE)
    cursor = conn.cursor()

    # Fetch file name associated with the user
    cursor.execute('SELECT file_name FROM users WHERE full_name = ?', (user['full_name'],))
    file_name = cursor.fetchone()
    file_name = file_name[0] if file_name else None

    # Fetch selected file data if a file is selected
    selected_file_data = {}
    if file_name:
        try:
            with open(f"./json_reports/{file_name}.json", "r", encoding="utf-8") as f:
                selected_file_data = json.load(f)
        except FileNotFoundError:
            print(f"JSON file for {file_name} not found.")
        except json.JSONDecodeError:
            print(f"Error decoding JSON for {file_name}.")

    # Sync owners before displaying files
    sync_owners_with_raw_data()

    # Fetch uploaded files
    cursor.execute('SELECT file_name, status, user, date_time FROM raw_data')
    uploaded_files = [
        row for row in cursor.fetchall()
        if check_user_permission(row[0], user['full_name'])
    ]

    # Fetch all users
    cursor.execute('SELECT full_name FROM users')
    all_users = [row[0] for row in cursor.fetchall()]

    # Fetch file owners and shared users
    file_owner = {}
    shared_users = {}
    cursor.execute('SELECT file, users FROM owners')
    for file, users in cursor.fetchall():
        users_list = users.split(',')
        file_owner[file] = users_list[0] if users_list else None
        shared_users[file] = users_list

    cursor.execute("SELECT COUNT(*) FROM raw_data WHERE status = 'extracted'")
    extracted_count = cursor.fetchone()[0]
    conn.close()

    # Get new records count
    new_records = get_new_records_count()

    return render_template(
        'home.html',
        full_name=user['full_name'],
        department=user['department'],
        uploaded_files=uploaded_files,
        extracted_count=extracted_count,
        new_records=new_records,
        all_users=all_users,
        file_owner=file_owner,
        shared_users=shared_users,
        selected_file=file_name,
        selected_file_data=selected_file_data  # Pass the selected file data
    )


@app.route('/upload-file', methods=['POST'])
def upload_file():
    """Handle file upload for .swmz files, ensuring validation and all processing steps are executed."""
    user = session.get('user')
    if not user:
        return jsonify({"error": "User session expired. Please log in again."}), 401

    file = request.files.get('file')
    if not file or not file.filename.endswith('.swmz'):
        return jsonify({"error": "Invalid file type. Please upload a .swmz file."}), 400

    file_name = secure_filename(file.filename)
    file_base_name = remove_file_extension(file_name)
    temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    temp_extracted_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted_data_temp')

    conn = None

    try:
        # Check for existing file in the database
        conn = sqlite3.connect(file_manager.DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT user FROM raw_data WHERE file_name = ?", (file_base_name,))
        existing_record = cursor.fetchone()

        if existing_record:
            owner = existing_record[0]
            if owner == user['full_name']:
                return jsonify({"error": "You have already uploaded this file."}), 409
            else:
                return jsonify({"error": f"This file is already uploaded by {owner}."}), 409

        # Save the file temporarily
        file.save(temp_file_path)

        # Extract temporarily and validate ProjectCode
        temp_extracted = extract_data_temporarily(temp_file_path, temp_extracted_folder)
        if not temp_extracted:
            os.remove(temp_file_path)
            cleanup_temporary_folder(temp_extracted_folder)
            return jsonify({"error": "File extraction failed. Invalid file structure."}), 400

        is_valid = validate_project_code_and_structure(temp_extracted, file_base_name)
        cleanup_temporary_folder(temp_extracted_folder)
        if not is_valid:
            os.remove(temp_file_path)
            return jsonify({"error": "Validation failed. ProjectCode mismatch or invalid folder structure."}), 400

        # Save the new file to RAW_DATA_FOLDER
        raw_file_path = os.path.join(file_manager.RAW_DATA_FOLDER, file_name)
        with open(raw_file_path, 'wb') as raw_file:
            raw_file.write(open(temp_file_path, 'rb').read())

        # Add record to the database
        cursor.execute("""
            INSERT INTO raw_data (file_name, user, status, date_time)
            VALUES (?, ?, ?, ?)
        """, (file_base_name, user['full_name'], "not_extracted", datetime.now()))
        conn.commit()

        # Extract data and generate JSON
        extracted_folder = extract_data(raw_file_path, file_manager.EXTRACTED_DATA_FOLDER)
        if extracted_folder:
            json_file_path = file_manager.generate_json(extracted_folder)
            cursor.execute("""
                UPDATE raw_data
                SET status = 'extracted'
                WHERE file_name = ?
            """, (file_base_name,))
            conn.commit()

            # Update the `users` table with the selected file name
            cursor.execute("""
                UPDATE users
                SET file_name = ?
                WHERE full_name = ?
            """, (file_base_name, user['full_name']))
            conn.commit()
        else:
            raise ValueError(f"Extraction failed for '{file_name}'.")

        return jsonify({"success": f"File '{file_name}' uploaded, extracted, and processed successfully.", "json_file": json_file_path}), 200

    except Exception as e:
        print(f"Exception occurred: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

    finally:
        if conn:
            conn.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        cleanup_temporary_folder(temp_extracted_folder)


@app.route('/select-file/<file_name>', methods=['POST'])
def select_file(file_name):
    """Update the selected file for the current user."""
    user = session.get('user')
    if not user:
        return jsonify({"success": False, "error": "User not logged in."}), 401

    try:
        # Update the file_name in the users table for the current user
        conn = sqlite3.connect(file_manager.DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET file_name = ? WHERE full_name = ?',
            (file_name, user['full_name'])
        )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": f"File '{file_name}' selected."})
    except Exception as e:
        print(f"Error updating file_name for user: {e}")
        return jsonify({"success": False, "error": "Failed to update selected file."}), 500



@app.route('/overwrite-file', methods=['POST'])
def overwrite_file():
    """Handle overwriting an existing file."""
    user = session.get('user')
    if not user:
        return redirect('/')

    # Retrieve the temporary file path and filename from the session
    temp_file_path = session.pop('temp_file_path', None)
    file_name = session.pop('overwrite_file_name', None)

    if temp_file_path and file_name and os.path.exists(temp_file_path):
        # Open the temporary file for overwriting
        with open(temp_file_path, 'rb') as temp_file:
            result = file_manager.handle_overwrite(temp_file, file_name, user['full_name'])  # Includes extraction and JSON logic
        os.remove(temp_file_path)  # Clean up the temp file
        flash(result['message'], "success" if result['status'] == 'success' else "error")
    else:
        flash("An error occurred. Please try uploading the file again.", "error")

    return redirect('/home')


@app.route('/delete-file/<file_name>', methods=['POST'])
def delete_file(file_name):
    """Delete a file and its associated data."""
    user = session.get('user')
    if not user:
        return jsonify({"error": "Unauthorized access"}), 401

    try:
        conn = sqlite3.connect(file_manager.DATABASE)
        cursor = conn.cursor()

        # Check if the user has permission to delete the file
        base_name = remove_file_extension(file_name)  # Extract base file name

        # Fetch uploader from raw_data table
        cursor.execute("SELECT user FROM raw_data WHERE file_name = ?", (base_name,))
        raw_data_user = cursor.fetchone()
        if raw_data_user and raw_data_user[0] == user['full_name']:
            has_permission = True
        else:
            # Check owners table
            cursor.execute("SELECT users FROM owners WHERE file = ?", (base_name,))
            owners = cursor.fetchone()
            has_permission = owners and owners[0].split(',')[0] == user['full_name']

        if not has_permission:
            flash(f"You do not have permission to delete '{file_name}': {e}", "error")

        # Delete related files from storage
        FileManager.delete_related_files(base_name)

        # Delete entries from database
        cursor.execute("DELETE FROM raw_data WHERE file_name = ?", (base_name,))
        cursor.execute("DELETE FROM saved_data WHERE file_name = ?", (base_name,))
        cursor.execute("DELETE FROM owners WHERE file = ?", (base_name,))
        cursor.execute("UPDATE users SET file_name = NULL WHERE file_name = ?", (file_name,))
        conn.commit()

        flash(f"File '{file_name}' and all related data have been deleted.", "success")
        #return jsonify({"success": True, "message": f"File '{file_name}' deleted successfully."}), 200
        return redirect('/home') 
    except Exception as e:
        flash(f"An error occurred while deleting '{file_name}': {e}", "error")
        #return jsonify({"error": f"An error occurred: {e}"}), 500
        return redirect('/home') 

    finally:
        conn.close()


# ----------- File Management Routes -----------

@app.route('/extracted_data/<path:filename>')
def serve_extracted_data(filename):
    return send_from_directory('./extracted_data', filename)


@app.route('/get-json/<file_name>', methods=['GET'])
def get_json(file_name):
    """
    Return the JSON data for a specific file.
    """
    try:
        
        file_name = standardize_file_name(file_name)

        if '_inv' not in file_name:
            file_name += '_inv.json'
        elif '_inv' in file_name and not file_name.endswith('.json'):
            file_name += '.json'

        # Add the correct JSON file extension
        json_file_path = os.path.join(file_manager.JSON_FOLDER, f"{file_name}")

        # Debugging logs
        print(f"Fetching JSON for file: {json_file_path}")

    
        # Verify the file exists
        if not os.path.exists(json_file_path):
            print(f"JSON file does not exist at app.py: {json_file_path}")
            return jsonify({"error": f"JSON file for '{file_name}' does not exist."}), 404

        # Load and return the JSON data
        with open(json_file_path, "r", encoding="utf-8") as json_file:
            json_data = json.load(json_file)

        return jsonify(json_data)
    except Exception as e:
        print(f"Error while fetching JSON: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500


@app.route('/save-json', methods=['POST'])
def save_json():
    """
    Endpoint to save the changes made to the JSON file and create an updated .swmz file.
    """
    try:
        # Retrieve the file name and updated data from the request
        data = request.json
        file_name = data.get("file_name")
        updated_data = data.get("updated_data")

        # Validate input
        if not file_name or not updated_data:
            return jsonify({"error": "Missing 'file_name' or 'updated_data' in the request."}), 400

        # Process Tap Condition rows (if required)
        def process_tap_condition(data):
            if "Tap Condition" in data:
                for row in data["Tap Condition"]:
                    # Add or modify logic as necessary
                    row["condition_key"] = "updated_value"
            return data

        updated_data = process_tap_condition(updated_data)

        # Standardize and ensure the file name is correct
        standardized_file_name = standardize_file_name(file_name)
        if not standardized_file_name.endswith(".json"):
            standardized_file_name += ".json"

        # Construct the JSON file path
        json_file_path = os.path.join(file_manager.JSON_FOLDER, standardized_file_name)

        # Save the updated JSON to the file
        with open(json_file_path, "w", encoding="utf-8") as json_file:
            json.dump(updated_data, json_file, indent=4, ensure_ascii=False)

        # Convert JSON to .swmz and save it
        compress_project_folder(
            project_code=standardize_file_name(file_name.replace(".json", "")),
            extracted_data_folder=EXTRACTED_DATA_FOLDER,
            saved_data_folder=SAVED_DATA_FOLDER,
            json_file_path=json_file_path
        )

        # Log changes to `saved_data` table
        save_data(
            remove_file_extension(file_name),
            session['user']['full_name'],
            status='saved'
        )

        # Return a success response
        return jsonify({
            "success": True,
            "message": f"JSON file '{standardized_file_name}' and corresponding .swmz file saved successfully."
        })
    except Exception as e:
        print(f"Error while saving JSON: {e}")
        return jsonify({"error": f"An error occurred while saving the JSON file: {e}"}), 500


@app.route('/compress-project/<string:project_code>', methods=['POST'])
def compress_project(project_code):
    """
    Endpoint to compress a project folder and update the saved_data table.
    """
    try:
        # Parse JSON input to get json_file_path
        data = request.get_json()
        json_file_path = data.get("json_file_path", None)
        
        # Debugging log
        print(f"Using JSON file path from request: {json_file_path}")

        # Standardize file name globally
        standardized_project_code = standardize_file_name(project_code)
        compressed_file_path, is_new_file = compress_project_folder(
            project_code=standardized_project_code,
            extracted_data_folder=EXTRACTED_DATA_FOLDER,
            saved_data_folder=SAVED_DATA_FOLDER,
            json_file_path=json_file_path  # Pass JSON file path
        )

        # Debug: Log compress operation
        print(f"Compressed project: {standardized_project_code}")
        print(f"Compressed file path: {compressed_file_path}")

        # Return a success response
        return jsonify({
            'success': True,
            'message': f"Project compressed successfully: {compressed_file_path}"
        }), 200
    except FileNotFoundError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': f"An error occurred: {str(e)}"}), 500



@app.route('/view-json/<file_name>', methods=['GET'])
def view_json(file_name):
    """Display the JSON data for the selected file in a new tab."""
    # Check for user session
    user = session.get('user')
    if not user:
        flash("Your session has expired. Please log in again.", "error")
        return redirect('/')

    # Ensure the file name ends with `.json` and contains `_inv`
    if not file_name.endswith('_inv.json'):
        file_name = f"{file_name.replace('.json', '')}_inv.json"

    # Resolve the file path
    json_file_path = os.path.join(file_manager.JSON_FOLDER, file_name)
    print(f"Resolved JSON file path: {json_file_path}")  # Debugging log

    # Check if the JSON file exists
    if not os.path.exists(json_file_path):
        print(f"JSON file does not exist at path: {json_file_path}")  # Debugging log
        return render_template('error.html', message=f"JSON file '{file_name}' does not exist.")

    # Load the JSON content
    try:
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            json_data = json.load(json_file)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return render_template('error.html', message=f"Failed to load JSON file: {e}")

    # Render the JSON data in the view_json.html template
    return render_template('view_json.html', json_content=json_data, file_name=file_name)


@app.route('/get-overview-data', methods=['GET'])
def get_overview_data():
    user = session.get('user')
    if not user:
        return jsonify({"error": "User not logged in"}), 401

    conn = sqlite3.connect(file_manager.DATABASE)
    cursor = conn.cursor()

    try:
        uploaded = cursor.execute(
            "SELECT COUNT(*) FROM raw_data WHERE user = ?", (user['full_name'],)
        ).fetchone()[0]

        working = cursor.execute(
            "SELECT COUNT(*) FROM saved_data WHERE user = ?", (user['full_name'],)
        ).fetchone()[0]

        completed = cursor.execute(
            "SELECT COUNT(*) FROM pushed_data WHERE user = ?", (user['full_name'],)
        ).fetchone()[0]

        total = uploaded + working + completed

        return jsonify({
            "uploaded": uploaded,
            "working": working,
            "completed": completed,
        })
    except Exception as e:
        print(f"Error fetching overview data: {e}")
        return jsonify({"error": "Failed to fetch overview data"}), 500
    finally:
        conn.close()

@app.route('/save-file', methods=['POST'])
def save_file():
    """Save the selected file name for the current user."""
    user = session.get('user')
    if not user:
        return jsonify({"success": False, "error": "User not logged in."}), 401

    try:
        # Get the file_name from the request
        data = request.get_json()
        file_name = data.get('file_name')

        print(f"User: {user['full_name']} is selecting file: {file_name}")  # Debug log

        if not file_name:
            return jsonify({"success": False, "error": "No file name provided."}), 400

        # Remove the `.json` extension if present
        if file_name.endswith(".json"):
            file_name = file_name[:-5]  # Remove the trailing '.json'

        # Update the file_name in the users table for the current user
        conn = sqlite3.connect(file_manager.DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET file_name = ? WHERE full_name = ?',
            (file_name, user['full_name'])
        )
        conn.commit()
        cursor.execute(
            'SELECT file_name FROM users WHERE full_name = ?',
            (user['full_name'],)
        )
        updated_file = cursor.fetchone()
        conn.close()

        print(f"Updated file_name for user {user['full_name']}: {updated_file}")  # Debug log

        return jsonify({"success": True, "message": f"File '{file_name}' saved for user '{user['full_name']}'."})
    except Exception as e:
        print(f"Error saving file name for user: {e}")  # Debug log
        return jsonify({"success": False, "error": "Failed to save selected file."}), 500



@app.route('/share-file/<file_name>', methods=['POST'])
def share_file(file_name):
    user = session.get('user')
    if not user:
        return redirect('/')

    shared_user = request.form['shared_user']
    conn = sqlite3.connect(file_manager.DATABASE)
    cursor = conn.cursor()

    try:
        # Check if the file exists in the owners table
        cursor.execute('SELECT users FROM owners WHERE file = ?', (file_name,))
        result = cursor.fetchone()
        if not result:
            return redirect('/home')  # File does not exist
        existing_users = result[0].split(',')

        # Only allow the owner to share
        if user['full_name'] != existing_users[0]:
            flash("You do not have permission to share this file.", "error")
            return redirect('/home')

        # Add the new user if not already shared
        if shared_user not in existing_users:
            existing_users.append(shared_user)
            cursor.execute(
                'UPDATE owners SET users = ? WHERE file = ?',
                (','.join(existing_users), file_name)
            )
            conn.commit()
        flash(f"File '{file_name}' shared with {shared_user}.", "success")
    except Exception as e:
        flash(f"Error sharing file: {e}", "error")
    finally:
        conn.close()

    return redirect('/home')

@app.route('/unshare-file/<file_name>', methods=['POST'])
def unshare_file(file_name):
    user = session.get('user')
    if not user:
        return redirect('/')

    unshared_user = request.form['unshared_user']
    conn = sqlite3.connect(file_manager.DATABASE)
    cursor = conn.cursor()

    try:
        # Check if the file exists in the owners table
        cursor.execute('SELECT users FROM owners WHERE file = ?', (file_name,))
        result = cursor.fetchone()
        if not result:
            return redirect('/home')  # File does not exist
        existing_users = result[0].split(',')

        # Only allow the owner to unshare
        if user['full_name'] != existing_users[0]:
            flash("You do not have permission to unshare this file.", "error")
            return redirect('/home')

        # Remove the user if they are in the shared list
        if unshared_user in existing_users:
            existing_users.remove(unshared_user)
            cursor.execute(
                'UPDATE owners SET users = ? WHERE file = ?',
                (','.join(existing_users), file_name)
            )
            conn.commit()
        flash(f"File '{file_name}' unshared with {unshared_user}.", "success")
    except Exception as e:
        flash(f"Error unsharing file: {e}", "error")
    finally:
        conn.close()

    return redirect('/home')

@app.route('/run-ai/<file_name>', methods=['POST'])
def run_ai(file_name):
    """Run AI model for the given JSON file."""
    user = session.get('user')
    if not user:
        return jsonify({"success": False, "error": "User not logged in."}), 401

    try:
        # Standardize the file name
        file_name = standardize_file_name(file_name)
        print(f"Running AI for file: {file_name}")

        # Call the AI processing function
        process_json(file_name)  # Ensure this works as expected
        return jsonify({"success": True, "message": f"AI processing completed for '{file_name}'."})
    except Exception as e:
        print(f"Error running AI for {file_name}: {e}")
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500

@app.route('/check-updates', methods=['GET'])
def check_updates():
    """Endpoint to check if the JSON file has been updated."""
    json_file = request.args.get('file')
    if not json_file:
        return jsonify({"updated": False, "error": "No file specified"}), 400

    try:
        # Ensure the file is standardized
        standardized_file_name = standardize_file_name(json_file)
        if not standardized_file_name.endswith(".json"):
            standardized_file_name += ".json"

        # Construct the file path
        json_file_path = os.path.join(file_manager.JSON_FOLDER, standardized_file_name)

        # Check if the file exists
        if not os.path.exists(json_file_path):
            return jsonify({"updated": False, "error": f"File '{standardized_file_name}' does not exist."}), 404

        # Get the last modified timestamp of the file
        file_last_modified = datetime.fromtimestamp(os.path.getmtime(json_file_path))

        # Example: Compare with a pre-defined reference time or session-stored time
        reference_time = session.get(f"{json_file}_last_checked", datetime.min)
        if isinstance(reference_time, str):  # If stored as a string, parse it
            reference_time = datetime.strptime(reference_time, "%Y-%m-%d %H:%M:%S")

        # Update session with the latest check time
        session[f"{json_file}_last_checked"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Return whether the file has been updated since the last check
        is_updated = file_last_modified > reference_time
        return jsonify({"updated": is_updated}), 200
    except Exception as e:
        print(f"Error in /check-updates: {e}")
        return jsonify({"updated": False, "error": f"An error occurred: {str(e)}"}), 500

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)