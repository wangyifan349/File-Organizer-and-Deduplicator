import os  # Standard library: filesystem paths and directory operations
import shutil  # Standard library: high-level file operations (move, rmtree)
import uuid  # Standard library: UUID generation for stable share identifiers

from functools import wraps  # Preserves function metadata when using decorators
from flask import (  # Flask web framework imports
    Flask,  # Main Flask application class
    request,  # HTTP request object (JSON, files, args)
    jsonify,  # Helper to return JSON responses
    send_file,  # Send files as HTTP responses
    session,  # Cookie-based session storage
    redirect,  # Redirect responses
    url_for,  # Build URLs for endpoints
    render_template_string  # Render HTML templates from strings
)
from flask_sqlalchemy import SQLAlchemy  # SQLAlchemy integration for Flask
from werkzeug.utils import secure_filename  # Sanitize uploaded filenames
from werkzeug.security import generate_password_hash, check_password_hash  # Password hashing and verification


app = Flask(__name__)  # Create Flask app instance

BASE_DIR = os.path.abspath(os.path.dirname(__file__))  # Absolute directory of this script
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")  # Root folder where all user folders are stored
DATABASE_FILE = os.path.join(BASE_DIR, "meta.db")  # SQLite database file path

app.config["UPLOAD_FOLDER"] = UPLOAD_ROOT  # Configure upload root directory
app.config["SECRET_KEY"] = "change_this_secret_key"  # Session signing key (change in production)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DATABASE_FILE  # SQLite database URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable SQLAlchemy event system overhead

db = SQLAlchemy(app)  # Initialize ORM with Flask app


class User(db.Model):  # User table model
    id = db.Column(db.Integer, primary_key=True)  # Primary key
    username = db.Column(db.String(150), unique=True, index=True, nullable=False)  # Unique username
    password_hash = db.Column(db.String(255), nullable=False)  # Hashed password


class SharedFile(db.Model):  # Shared file mapping model
    id = db.Column(db.Integer, primary_key=True)  # Primary key
    share_id = db.Column(db.String(36), unique=True, index=True, nullable=False)  # Public share UUID
    owner_username = db.Column(db.String(150), index=True, nullable=False)  # Owner username
    relative_path = db.Column(db.String(400), nullable=False)  # Path relative to user's folder
    display_name = db.Column(db.String(200), nullable=False)  # Name used when downloading


with app.app_context():  # Ensure we have an app context for DB operations
    db.create_all()  # Create tables if they do not exist


def require_login(handler):  # Decorator to enforce login on routes
    @wraps(handler)  # Keep original function name/docs for Flask
    def wrapper(*args, **kwargs):  # Wrapper that checks session first
        if "username" not in session:  # If user not logged in
            return redirect(url_for("login"))  # Redirect to login page
        return handler(*args, **kwargs)  # Proceed to actual handler
    return wrapper  # Return decorated function


def ensure_user_directory(username=None):  # Get/create the user's storage directory
    current_username = username or session.get("username")  # Prefer explicit username, else from session
    if not current_username:  # If still missing (not logged in / invalid call)
        return None  # No directory can be resolved
    user_dir = os.path.join(app.config["UPLOAD_FOLDER"], current_username)  # Path: uploads/<username>
    os.makedirs(user_dir, exist_ok=True)  # Create directory if missing
    return user_dir  # Return user directory path


def resolve_user_path(user_dir, user_input):  # Resolve a user-provided path safely under user_dir
    if user_input is None:  # Guard missing input
        raise ValueError("missing path")  # Reject

    text = str(user_input).strip().replace("\\", "/").lstrip("/")  # Normalize separators, remove leading slash
    if text == "" or text in (".", ".."):  # Reject empty/unsafe names
        raise ValueError("invalid path")  # Reject

    normalized = os.path.normpath(text)  # Normalize path (removes ../ patterns)
    if normalized.startswith("..") or os.path.isabs(normalized):  # Block traversal or absolute paths
        raise ValueError("path traversal")  # Reject

    base_abs = os.path.abspath(user_dir)  # Absolute base directory
    target_abs = os.path.abspath(os.path.join(base_abs, normalized))  # Absolute resolved path

    if not (target_abs == base_abs or target_abs.startswith(base_abs + os.sep)):  # Ensure target stays within base
        raise ValueError("path traversal")  # Reject if outside base

    return target_abs, normalized  # Return absolute path and normalized relative path


def build_share_url(share_id):  # Build a full external share URL
    return url_for("download_shared", share_id=share_id, _external=True)  # External URL for share link


@app.route("/", methods=["GET"])  # Root endpoint
def root():  # Redirect based on login state
    if "username" in session:  # If user already logged in
        return redirect(url_for("dashboard"))  # Go to dashboard
    return redirect(url_for("login"))  # Otherwise go to login page


@app.route("/login", methods=["GET", "POST"])  # Login route
def login():  # Handles login page and login submission
    if request.method == "POST":  # API login request
        payload = request.get_json(silent=True) or {}  # Read JSON body safely
        username = (payload.get("username") or "").strip()  # Username from JSON
        password = payload.get("password") or ""  # Password from JSON

        if not username or not password:  # Validate required fields
            return jsonify({"error": "Missing parameters"}), 400  # Bad request

        user = User.query.filter_by(username=username).first()  # Lookup user by username
        if user and check_password_hash(user.password_hash, password):  # Verify password
            session["username"] = username  # Set session login
            return jsonify({"message": "Login success"})  # Return success JSON
        return jsonify({"error": "Invalid credentials"}), 403  # Unauthorized

    return render_template_string(LOGIN_HTML)  # Render login page for GET


@app.route("/register", methods=["GET", "POST"])  # Register route
def register():  # Handles registration page and user creation
    if request.method == "POST":  # API register request
        payload = request.get_json(silent=True) or {}  # Read JSON body safely
        username = (payload.get("username") or "").strip()  # Username from JSON
        password = payload.get("password") or ""  # Password from JSON

        if not username or not password:  # Validate required fields
            return jsonify({"error": "Missing parameters"}), 400  # Bad request

        if User.query.filter_by(username=username).first():  # Check existing user
            return jsonify({"error": "User already exists"}), 400  # Conflict-like

        user = User(username=username, password_hash=generate_password_hash(password))  # Create user w/ hashed password
        db.session.add(user)  # Add to session
        db.session.commit()  # Persist to DB
        return jsonify({"message": "Register success"})  # Return success JSON

    return render_template_string(REGISTER_HTML)  # Render register page for GET


@app.route("/logout", methods=["POST"])  # Logout route
def logout():  # Clears login session
    session.pop("username", None)  # Remove username from session
    return jsonify({"message": "Logout success"})  # Return success JSON


@app.route("/dashboard", methods=["GET"])  # Dashboard page route
@require_login  # Require user to be logged in
def dashboard():  # Render the main UI
    return render_template_string(DASHBOARD_HTML, username=session["username"])  # Render dashboard with username


@app.route("/files", methods=["GET"])  # List files API
@require_login  # Require user to be logged in
def list_files():  # Return list of items in user directory
    user_dir = ensure_user_directory()  # Ensure user directory exists
    items = []  # Response list
    for name in sorted(os.listdir(user_dir)):  # List entries in the user directory
        full_path = os.path.join(user_dir, name)  # Full path for each entry
        items.append({"name": name, "type": "dir" if os.path.isdir(full_path) else "file"})  # Add name + type
    return jsonify(items)  # Return JSON list


@app.route("/upload", methods=["POST"])  # Upload API
@require_login  # Require user to be logged in
def upload():  # Handle multipart/form upload
    if "file" not in request.files:  # Ensure file field exists
        return jsonify({"error": "No file"}), 400  # Bad request

    file_obj = request.files["file"]  # Get uploaded file object
    if not file_obj.filename:  # Ensure filename present
        return jsonify({"error": "Empty filename"}), 400  # Bad request

    safe_name = secure_filename(file_obj.filename)  # Sanitize filename
    if not safe_name:  # Ensure it didn't sanitize to empty
        return jsonify({"error": "Invalid filename"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    dest = os.path.join(user_dir, safe_name)  # Destination path
    file_obj.save(dest)  # Save file to disk
    return jsonify({"message": "Upload success"})  # Success JSON


@app.route("/download", methods=["GET"])  # Download API
@require_login  # Require user to be logged in
def download():  # Send a user file as attachment
    filename = request.args.get("file")  # File name parameter
    if not filename:  # Validate parameter
        return jsonify({"error": "Missing parameter"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    try:
        file_path, _ = resolve_user_path(user_dir, filename)  # Safely resolve path
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400  # Reject traversal attempts

    if not os.path.isfile(file_path):  # Ensure it's an existing file
        return jsonify({"error": "File not found"}), 404  # Not found

    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))  # Send file


@app.route("/delete", methods=["POST"])  # Delete API
@require_login  # Require user to be logged in
def delete():  # Delete a file or folder
    payload = request.get_json(silent=True) or {}  # Read JSON body
    filename = payload.get("filename")  # Target to delete
    if not filename:  # Validate parameter
        return jsonify({"error": "Missing parameter"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    try:
        target_abs, target_rel = resolve_user_path(user_dir, filename)  # Safely resolve path
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400  # Reject traversal attempts

    if os.path.isdir(target_abs):  # If target is a directory
        shutil.rmtree(target_abs)  # Delete directory recursively
        return jsonify({"message": "Delete success"})  # Success JSON

    if os.path.isfile(target_abs):  # If target is a file
        os.remove(target_abs)  # Delete file

        shared = SharedFile.query.filter_by(  # Find share record (if any)
            owner_username=session["username"],  # Must match current user
            relative_path=target_rel  # Must match the file's relative path
        ).first()  # Get first match
        if shared:  # If file was shared
            db.session.delete(shared)  # Remove share record
            db.session.commit()  # Persist change

        return jsonify({"message": "Delete success"})  # Success JSON

    return jsonify({"error": "Target not found"}), 404  # Not found if neither file nor directory


@app.route("/move", methods=["POST"])  # Move/Rename API
@require_login  # Require user to be logged in
def move():  # Move or rename a file/folder within user's space
    payload = request.get_json(silent=True) or {}  # Read JSON body
    source = payload.get("src")  # Source path
    target = payload.get("dst")  # Target path

    if not source or not target:  # Validate parameters
        return jsonify({"error": "Missing parameters"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    try:
        source_abs, source_rel = resolve_user_path(user_dir, source)  # Resolve source safely
        target_abs, target_rel = resolve_user_path(user_dir, target)  # Resolve target safely
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400  # Reject traversal attempts

    if not os.path.exists(source_abs):  # Ensure source exists
        return jsonify({"error": "Source not found"}), 404  # Not found

    if os.path.exists(target_abs):  # Disallow overwrite for safety/clarity
        return jsonify({"error": "Target already exists"}), 409  # Conflict

    os.makedirs(os.path.dirname(target_abs), exist_ok=True)  # Ensure target directory exists

    try:
        shutil.move(source_abs, target_abs)  # Perform move/rename operation
    except Exception as exc:
        return jsonify({"error": f"Move failed: {exc}"}), 500  # Server error with message

    shared = SharedFile.query.filter_by(  # If this file was shared, update share record
        owner_username=session["username"],  # Share must belong to current user
        relative_path=source_rel  # Match previous relative path
    ).first()  # Find record
    if shared:  # If share exists
        shared.relative_path = target_rel  # Update stored relative path
        shared.display_name = os.path.basename(target_rel)  # Update display name
        db.session.commit()  # Persist updates

    return jsonify({"message": "Move success"})  # Success JSON


@app.route("/share", methods=["POST"])  # Share API
@require_login  # Require user to be logged in
def share():  # Create or reuse a share link for a file
    payload = request.get_json(silent=True) or {}  # Read JSON body
    filename = payload.get("filename")  # Filename to share
    if not filename:  # Validate parameter
        return jsonify({"error": "Missing parameter"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    try:
        file_abs, file_rel = resolve_user_path(user_dir, filename)  # Resolve file path safely
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400  # Reject traversal attempts

    if not os.path.isfile(file_abs):  # Ensure file exists
        return jsonify({"error": "File not found"}), 404  # Not found

    record = SharedFile.query.filter_by(  # Check if already shared
        owner_username=session["username"],  # Must belong to current user
        relative_path=file_rel  # Same relative path
    ).first()  # Get record if exists

    if not record:  # If not yet shared
        record = SharedFile(  # Create new share record
            share_id=str(uuid.uuid4()),  # New UUID for stable link
            owner_username=session["username"],  # Owner is current user
            relative_path=file_rel,  # Save relative path
            display_name=os.path.basename(file_rel)  # Save display name for download
        )
        db.session.add(record)  # Add to DB session
        db.session.commit()  # Persist to DB

    return jsonify({"message": "Share success", "share_url": build_share_url(record.share_id)})  # Return share URL


@app.route("/unshare", methods=["POST"])  # Unshare API
@require_login  # Require user to be logged in
def unshare():  # Remove a share record
    payload = request.get_json(silent=True) or {}  # Read JSON body
    filename = payload.get("filename")  # Filename (or relative path) to unshare
    if not filename:  # Validate parameter
        return jsonify({"error": "Missing parameter"}), 400  # Bad request

    user_dir = ensure_user_directory()  # Resolve user directory
    try:
        _, file_rel = resolve_user_path(user_dir, filename)  # Resolve to normalized relative path
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400  # Reject traversal attempts

    record = SharedFile.query.filter_by(  # Find matching share record
        owner_username=session["username"],  # Must belong to current user
        relative_path=file_rel  # Match relative path
    ).first()  # Get record

    if not record:  # If not shared
        return jsonify({"error": "Not shared"}), 404  # Not found

    db.session.delete(record)  # Delete share record
    db.session.commit()  # Persist changes
    return jsonify({"message": "Unshare success"})  # Success JSON


@app.route("/download_shared/<share_id>", methods=["GET"])  # Public share download endpoint
def download_shared(share_id):  # Download a shared file without login
    record = SharedFile.query.filter_by(share_id=share_id).first()  # Look up share record by UUID
    if not record:  # If missing or deleted
        return "File not found or unshared", 404  # Not found response

    owner_dir = ensure_user_directory(record.owner_username)  # Resolve owner's directory
    try:
        file_abs, _ = resolve_user_path(owner_dir, record.relative_path)  # Resolve file path safely
    except ValueError:
        return "File not found or unshared", 404  # Treat invalid as missing

    if not os.path.isfile(file_abs):  # Ensure file still exists
        return "File not found or unshared", 404  # Not found

    return send_file(file_abs, as_attachment=True, download_name=record.display_name)  # Send file


@app.route("/manage_shares", methods=["GET"])  # Shares management page
@require_login  # Require user to be logged in
def manage_shares():  # Render share management UI
    return render_template_string(MANAGE_SHARES_HTML)  # Render template


@app.route("/shares", methods=["GET"])  # Shares list API
@require_login  # Require user to be logged in
def shares_json():  # Return shares as JSON for management page
    records = SharedFile.query.filter_by(owner_username=session["username"]).order_by(SharedFile.id.desc()).all()  # Query shares
    response = []  # Prepare response list
    for item in records:  # Convert records into JSON-serializable dicts
        response.append({
            "display_name": item.display_name,  # Display name
            "relative_path": item.relative_path,  # Relative path
            "share_url": build_share_url(item.share_id)  # Public URL
        })
    return jsonify(response)  # Return JSON list


LOGIN_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login</title>
  <style>
    body{font-family:sans-serif;background:#f2f6fa;}
    .card{width:360px;margin:80px auto;background:white;padding:24px;border-radius:10px;box-shadow:0 2px 10px #ccc}
    input{padding:8px;width:92%;margin-bottom:12px;}
    button{padding:8px 16px;}
    #message{color:#b11;margin-top:10px;min-height:18px;}
  </style>
</head>
<body>
  <div class="card">
    <h2>User Login</h2>
    <input id="usernameInput" placeholder="Username"><br>
    <input id="passwordInput" type="password" placeholder="Password"><br>
    <button onclick="doLogin()">Login</button>
    <button onclick="window.location='/register'">Register</button>
    <div id="message"></div>
  </div>

<script>
function postJson(url, body){
  return fetch(url,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    credentials:'same-origin',
    body:JSON.stringify(body)
  }).then(r=>r.json().then(j=>({ok:r.ok, json:j})));
}
function doLogin(){
  postJson('/login',{username:usernameInput.value,password:passwordInput.value}).then(res=>{
    if(res.ok && res.json.message){
      window.location='/dashboard';
    }else{
      message.innerText = res.json.error || 'Login failed';
    }
  }).catch(()=>message.innerText='Network error');
}
</script>
</body>
</html>
"""


REGISTER_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Register</title>
  <style>
    body{font-family:sans-serif;background:#f2f6fa;}
    .card{width:360px;margin:80px auto;background:white;padding:24px;border-radius:10px;box-shadow:0 2px 10px #ccc}
    input{padding:8px;width:92%;margin-bottom:12px;}
    button{padding:8px 16px;}
    #message{color:#b11;margin-top:10px;min-height:18px;}
  </style>
</head>
<body>
  <div class="card">
    <h2>User Register</h2>
    <input id="usernameInput" placeholder="Username"><br>
    <input id="passwordInput" type="password" placeholder="Password"><br>
    <button onclick="doRegister()">Register</button>
    <button onclick="window.location='/login'">Back to Login</button>
    <div id="message"></div>
  </div>

<script>
function postJson(url, body){
  return fetch(url,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    credentials:'same-origin',
    body:JSON.stringify(body)
  }).then(r=>r.json().then(j=>({ok:r.ok, json:j})));
}
function doRegister(){
  postJson('/register',{username:usernameInput.value,password:passwordInput.value}).then(res=>{
    if(res.ok && res.json.message){
      alert('Register success, please login.');
      window.location='/login';
    }else{
      message.innerText = res.json.error || 'Register failed';
    }
  }).catch(()=>message.innerText='Network error');
}
</script>
</body>
</html>
"""


DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Dashboard</title>
  <style>
    body{font-family:sans-serif;background:#f0f1f4;margin:0;}
    .topbar{padding:18px 0 12px 0;background:#3e6bab;color:white;}
    .container{width:980px;margin:auto;}
    .topline{display:flex;justify-content:space-between;align-items:center;}
    .menu{margin:18px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
    .menu button{padding:7px 14px;border-radius:6px;border:0;background:#eee;cursor:pointer;}
    .menu button:hover{background:#e3e3e3;}
    select{padding:7px;border-radius:6px;border:1px solid #ccc;min-width:260px;}
    .message{color:#d44;margin:10px 0;min-height:18px;}
    .sharebox{background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 2px 10px #ddd;display:none;}
    .shareurl{color:#06c;font-size:13px;word-break:break-all;}
    .grid{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:40px;}
    .card{background:white;border-radius:10px;padding:14px 14px 10px 14px;min-width:140px;max-width:190px;min-height:92px;box-shadow:0 2px 12px #ddd;}
    .icon{font-size:34px;text-align:center;}
    .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;font-size:14px;margin:10px 0;}
    .ops{font-size:13px;text-align:center;display:flex;gap:6px;justify-content:center;flex-wrap:wrap;}
    .ops button{padding:4px 10px;border-radius:6px;border:0;background:#f1f1f1;cursor:pointer;}
    .ops button:hover{background:#e7e7e7;}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="container topline">
      <div>File Dashboard</div>
      <div>
        <span>Welcome {{username}}</span>
        <button onclick="doLogout()" style="margin-left:12px;padding:7px 14px;border-radius:6px;border:0;cursor:pointer;">Logout</button>
      </div>
    </div>
  </div>

  <div class="container">
    <div class="menu">
      <input type="file" id="uploadInput">
      <button onclick="uploadFile()">Upload</button>

      <select id="fileSelect">
        <option value="">Select a file (AJAX dropdown)</option>
      </select>

      <button onclick="dropdownDownload()">Download</button>
      <button onclick="dropdownDelete()">Delete</button>
      <button onclick="dropdownMove()">Move/Rename</button>
      <button onclick="dropdownShare()">Share</button>

      <button onclick="window.location='/manage_shares'">My Shares</button>
    </div>

    <div class="message" id="statusMessage"></div>

    <div class="sharebox" id="shareBox">
      Share link: <span class="shareurl" id="shareUrlText"></span>
      <button onclick="copyShare()">Copy</button>
    </div>

    <div class="grid" id="fileGrid"></div>
  </div>

<script>
function escapeForJs(text){
  return String(text).replaceAll('\\','\\\\').replaceAll("'","\\'");
}
function setStatus(text){
  statusMessage.innerText = text || '';
}
function hideShareBox(){
  shareBox.style.display = 'none';
  shareUrlText.textContent = '';
}
function showShareBox(url){
  shareUrlText.textContent = url || '';
  shareBox.style.display = url ? 'inline-block' : 'none';
}

function postJson(url, body){
  return fetch(url,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    credentials:'same-origin',
    body:JSON.stringify(body)
  }).then(async r=>{
    const j = await r.json().catch(()=> ({}));
    if(!r.ok) throw j;
    return j;
  });
}
function getJson(url){
  return fetch(url,{credentials:'same-origin'}).then(async r=>{
    const j = await r.json().catch(()=> ({}));
    if(!r.ok) throw j;
    return j;
  });
}

function doLogout(){
  postJson('/logout',{}).then(()=>window.location='/login');
}

function refreshDropdown(items){
  const current = fileSelect.value;
  fileSelect.innerHTML = '<option value="">Select a file (AJAX dropdown)</option>';
  for(const item of items){
    if(item.type === 'file'){
      const option = document.createElement('option');
      option.value = item.name;
      option.textContent = item.name;
      fileSelect.appendChild(option);
    }
  }
  if(current){
    for(const option of fileSelect.options){
      if(option.value === current){
        fileSelect.value = current;
        break;
      }
    }
  }
}

function loadFiles(){
  getJson('/files').then(items=>{
    if(!Array.isArray(items)){
      fileGrid.innerHTML = 'Load failed';
      return;
    }

    refreshDropdown(items);

    let html = '';
    for(const item of items){
      const icon = item.type === 'dir' ? '📁' : '🗎';
      html += `
        <div class="card">
          <div class="icon">${icon}</div>
          <div class="name" title="${item.name}">${item.name}</div>
          <div class="ops">
            ${item.type === 'file' ? `<button onclick="downloadFile('${escapeForJs(item.name)}')">Download</button>` : ``}
            <button onclick="deleteEntry('${escapeForJs(item.name)}')">Delete</button>
            <button onclick="moveEntry('${escapeForJs(item.name)}')">Move</button>
            ${item.type === 'file' ? `<button onclick="shareFile('${escapeForJs(item.name)}')">Share</button>` : ``}
          </div>
        </div>
      `;
    }
    fileGrid.innerHTML = html || '<div style="color:#999;margin:40px;">No files</div>';
  }).catch(()=>{ fileGrid.innerHTML = 'Load failed'; });
}

function uploadFile(){
  const file = uploadInput.files[0];
  if(!file) return;

  const formData = new FormData();
  formData.append('file', file);

  fetch('/upload',{
    method:'POST',
    credentials:'same-origin',
    body:formData
  }).then(r=>r.json())
    .then(j=>{
      setStatus(j.message || j.error || 'Upload failed');
      uploadInput.value = null;
      hideShareBox();
      loadFiles();
    }).catch(()=>setStatus('Network error'));
}

function downloadFile(name){
  window.location = '/download?file=' + encodeURIComponent(name);
}

function deleteEntry(name){
  if(!confirm('Delete: ' + name + ' ?')) return;
  postJson('/delete',{filename:name}).then(j=>{
    setStatus(j.message || 'Delete success');
    hideShareBox();
    loadFiles();
  }).catch(e=>setStatus(e.error || 'Delete failed'));
}

function moveEntry(name){
  const target = prompt('Enter new name (or path):', name);
  if(!target || target === name) return;

  postJson('/move',{src:name, dst:target}).then(j=>{
    setStatus(j.message || 'Move success');
    hideShareBox();
    loadFiles();
  }).catch(e=>setStatus(e.error || 'Move failed'));
}

function shareFile(name){
  postJson('/share',{filename:name}).then(j=>{
    setStatus(j.message || 'Share success');
    showShareBox(j.share_url || '');
  }).catch(e=>setStatus(e.error || 'Share failed'));
}

function selectedDropdownFile(){
  const value = fileSelect.value;
  if(!value){
    setStatus('Please select a file in the dropdown first');
    return null;
  }
  return value;
}

function dropdownDownload(){
  const name = selectedDropdownFile();
  if(!name) return;
  downloadFile(name);
}

function dropdownDelete(){
  const name = selectedDropdownFile();
  if(!name) return;
  deleteEntry(name);
}

function dropdownMove(){
  const name = selectedDropdownFile();
  if(!name) return;
  moveEntry(name);
}

function dropdownShare(){
  const name = selectedDropdownFile();
  if(!name) return;
  shareFile(name);
}

function copyShare(){
  const text = shareUrlText.textContent;
  if(!text) return;
  navigator.clipboard.writeText(text);
  alert('Copied');
}

loadFiles();
</script>
</body>
</html>
"""


MANAGE_SHARES_HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>My Shares</title>
  <style>
    body{font-family:sans-serif;background:#f0f1f4;margin:0;}
    .topbar{padding:18px 0 12px 0;background:#3e6bab;color:white;}
    .container{width:980px;margin:auto;}
    table{background:#fff;width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px #ddd;margin:18px 0 40px 0;}
    th,td{padding:10px 8px;text-align:left;vertical-align:top;}
    tr:nth-child(even){background:#f7f7fa;}
    .link{color:#06c;font-size:13px;word-break:break-all;}
    button{padding:5px 12px;border-radius:6px;border:0;background:#eee;cursor:pointer;}
    button:hover{background:#e3e3e3;}
    #message{color:#d44;margin:12px 0;min-height:18px;}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="container" style="display:flex;justify-content:space-between;align-items:center;">
      <div>My Shared Files</div>
      <div>
        <button onclick="window.location='/dashboard'">Back</button>
      </div>
    </div>
  </div>

  <div class="container">
    <div id="message"></div>
    <table>
      <thead>
        <tr>
          <th style="width:260px;">File</th>
          <th>Share Link</th>
          <th style="width:220px;">Actions</th>
        </tr>
      </thead>
      <tbody id="shareTableBody"></tbody>
    </table>
  </div>

<script>
function setMessage(text){
  message.innerText = text || '';
}

function postJson(url, body){
  return fetch(url,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    credentials:'same-origin',
    body:JSON.stringify(body)
  }).then(async r=>{
    const j = await r.json().catch(()=> ({}));
    if(!r.ok) throw j;
    return j;
  });
}

function getJson(url){
  return fetch(url,{credentials:'same-origin'}).then(async r=>{
    const j = await r.json().catch(()=> ({}));
    if(!r.ok) throw j;
    return j;
  });
}

function escapeForJs(text){
  return String(text).replaceAll('\\','\\\\').replaceAll("'","\\'");
}

function copyTextById(elementId){
  const text = document.getElementById(elementId).innerText;
  navigator.clipboard.writeText(text);
  alert('Copied');
}

function cancelShare(relativePath){
  postJson('/unshare',{filename:relativePath}).then(j=>{
    alert(j.message || 'Unshare success');
    loadShares();
  }).catch(e=>alert(e.error || 'Unshare failed'));
}

function loadShares(){
  getJson('/shares').then(items=>{
    let html = '';
    for(const item of items){
      const linkId = 'link_' + Math.random().toString(16).slice(2);
      html += `
        <tr>
          <td>${item.display_name}</td>
          <td>
            <span class="link" id="${linkId}">${item.share_url}</span>
            <button onclick="copyTextById('${linkId}')" style="margin-left:10px;">Copy</button>
          </td>
          <td>
            <button onclick="cancelShare('${escapeForJs(item.relative_path)}')">Unshare</button>
          </td>
        </tr>
      `;
    }
    shareTableBody.innerHTML = html || `<tr><td colspan="3" style="color:#999;padding:20px;">No shares</td></tr>`;
  }).catch(()=>setMessage('Load failed'));
}

loadShares();
</script>
</body>
</html>
"""


if __name__ == "__main__":  # Only run the server when executed directly
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)  # Ensure upload root exists
    app.run(debug=True)  # Start Flask dev server with debug mode
