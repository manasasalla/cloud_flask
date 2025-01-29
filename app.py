import os
import json
import pickle
from flask import Flask, render_template, request, session, redirect, url_for
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
import google.auth.exceptions
from flask_cors import CORS
CORS(app)


app = Flask(__name__)

app.secret_key = 'your-secret-key'

# Direct credentials JSON data
CLIENT_SECRETS = {
    "web": {
        "client_id":"311381716670-qjk6fkqcfd1tlnh8jlabiinpec34oug9.apps.googleusercontent.com",
        "project_id":"cloudapplication-449109",
        "auth_uri":"https://accounts.google.com/o/oauth2/auth",
        "token_uri":"https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs",
        "client_secret":"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",
        "redirect_uris":["http://localhost:5051/","https://cloud-five-topaz.vercel.app"],
        "javascript_origins":["https://cloud-flask.vercel.app","http://localhost:5050","http://127.0.0.1:5050"]
    }
}


#checking url


SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Path to store information locally
INFO_DIRECTORY = 'information'

# Set the maximum file upload size (100 MB in this case)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit

# Function to get credentials and build the Google Drive service
def get_credentials():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Force re-authentication
                flow = InstalledAppFlow.from_client_config(CLIENT_SECRETS, SCOPES)
                creds = flow.run_local_server(port=5051, open_browser=True)

        except google.auth.exceptions.RefreshError:
            # Handle Google authentication error
            print("Error during Google authentication.")
            return None

        # Save the new token
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def get_drive_service():
    creds = get_credentials()
    return build('drive', 'v3', credentials=creds)

# Load college and department data from JSON file
def load_college_data():
    colleges_file = os.path.join(INFO_DIRECTORY, 'colleges.json')
    if os.path.exists(colleges_file):
        with open(colleges_file, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            return data
    return {}

# Save updated college and department data to JSON file
def save_college_data(data):
    colleges_file = os.path.join(INFO_DIRECTORY, 'colleges.json')
    with open(colleges_file, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    college_data = load_college_data()
    return render_template('home.html', colleges=college_data)

@app.route('/upload', methods=['POST'])
def upload_file():
    if not os.path.exists(INFO_DIRECTORY):
        os.makedirs(INFO_DIRECTORY)

    college_name = request.form['college_name']
    department_name = request.form['department_name']
    file_name = request.form['file_name']
    uploaded_file = request.files['file_content']

    # Logging form data for debugging
    print(f"college_name: {college_name}, department_name: {department_name}, file_name: {file_name}")

    # Check if uploaded file is valid
    if not uploaded_file:
        return "No file selected for upload", 400

    # Create college and department folders
    college_folder_path = os.path.join(INFO_DIRECTORY, college_name)
    if not os.path.exists(college_folder_path):
        os.makedirs(college_folder_path)

    department_folder_path = os.path.join(college_folder_path, department_name)
    if not os.path.exists(department_folder_path):
        os.makedirs(department_folder_path)

    file_path = os.path.join(department_folder_path, file_name)
    uploaded_file.save(file_path)

    # Upload file to Google Drive and handle errors
    try:
        folder_id = create_google_drive_folders(college_name, department_name)
        create_google_drive_file(folder_id, file_name, file_path)
    except Exception as e:
        print(f"Error uploading to Google Drive: {e}")
        return f"Error uploading file to Google Drive: {e}", 500

    # Remove local file after upload
    os.remove(file_path)

    message = f'File "{file_name}" uploaded successfully to Google Drive and stored locally in {department_folder_path}.'

    return render_template('home.html', message=message, colleges=load_college_data())

def create_google_drive_folders(college_name, department_name):
    service = get_drive_service()
    college_folder_id = find_or_create_folder(service, college_name)
    department_folder_id = find_or_create_folder(service, department_name, college_folder_id)
    return department_folder_id

def find_or_create_folder(service, folder_name, parent_id=None):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get('files', [])

    if folders:
        return folders[0]['id']
    else:
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            file_metadata['parents'] = [parent_id]

        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder['id']

def create_google_drive_file(folder_id, file_name, file_path):
    service = get_drive_service()

    mime_type = 'application/octet-stream'
    if file_name.endswith('.txt'):
        mime_type = 'text/plain'
    elif file_name.endswith('.jpg') or file_name.endswith('.jpeg'):
        mime_type = 'image/jpeg'
    elif file_name.endswith('.png'):
        mime_type = 'image/png'
    elif file_name.endswith('.pdf'):
        mime_type = 'application/pdf'

    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype=mime_type)

    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'adminpassword'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('cms_portal'))
        else:
            return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')


from functools import wraps

# Decorator function
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/cms', methods=['GET', 'POST'])
def cms():
    # Redirect to the login page
    return redirect(url_for('login'))

@app.route('/cms_portal', methods=['GET', 'POST'])
@admin_required  # Use the decorator correctly on the route function
def cms_portal():
    college_data = load_college_data()
    message = None

    if request.method == 'POST':
        if 'add' in request.form:
            college_name = request.form.get('college_name')
            department_name = request.form.get('department_name')
            
            if college_name:
                if college_name not in college_data:
                    college_data[college_name] = []
                
                if department_name and department_name not in college_data[college_name]:
                    college_data[college_name].append(department_name)
                
                save_college_data(college_data)
                message = f"Added {department_name} to {college_name}"

        elif 'delete_college' in request.form:
            college_to_delete = request.form.get('college_to_delete')
            if college_to_delete and college_to_delete in college_data:
                del college_data[college_to_delete]
                save_college_data(college_data)
                message = f"Deleted college {college_to_delete}"

        elif 'delete_department' in request.form:
            college_name = request.form.get('college_name')
            department_to_delete = request.form.get('department_to_delete')
            if college_name in college_data and department_to_delete in college_data[college_name]:
                college_data[college_name].remove(department_to_delete)
                if not college_data[college_name]:
                    del college_data[college_name]
                save_college_data(college_data)
                message = f"Deleted department {department_to_delete} from {college_name}"

    return render_template('cms.html', college_data=college_data, message=message)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset_google_auth', methods=['POST'])
def reset_google_auth():
    if os.path.exists('token.pickle'):
        os.remove('token.pickle')
    session.clear()
    return "Google authentication reset. Please log in again."

if __name__ == '__main__':
    app.run(debug=False, port=5050)
