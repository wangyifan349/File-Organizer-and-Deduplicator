from flask import Flask, request, render_template_string, redirect, url_for, session, jsonify, send_from_directory
import os
import sqlite3
import shutil
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# 设置数据库和上传文件存储路径
DATABASE = 'users.db'
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.urandom(24)  # 用于会话管理

# 数据库操作函数
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL)''')
    conn.commit()
    conn.close()

# 检查用户是否存在
def get_user_by_username(username):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

# 注册功能
def register_user(username, password):
    hashed_password = generate_password_hash(password)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
    conn.commit()
    conn.close()

# 验证用户登录
def validate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user[2], password):  # user[2] is the password
        return True
    return False

# 注册页面
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if get_user_by_username(username):
            return 'Username already exists. Please try another one.'
        register_user(username, password)
        return redirect(url_for('login'))  # 注册后重定向到登录页面
    return render_template_string(REGISTER_HTML)

# 登录页面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if validate_user(username, password):
            session['username'] = username
            return redirect(url_for('index'))  # 登录成功，跳转到主页
        else:
            return 'Invalid username or password.'
    return render_template_string(LOGIN_HTML)

# 首页（文件管理页面）
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))  # 如果用户未登录，跳转到登录页面
    return render_template_string(INDEX_HTML)

# 上传文件页面（文件管理页面）
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    files = request.files.getlist('file')  # 处理多个文件上传
    filenames = []
    for file in files:
        if file.filename == '':
            return 'No selected file'
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        filenames.append(filename)
    return jsonify({'message': f'{", ".join(filenames)} uploaded successfully.'})

# 列出文件
@app.route('/files', methods=['GET'])
def list_files():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return jsonify({'files': files})

# 删除文件或文件夹
@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
        return jsonify({'message': f'{filename} deleted successfully.'}), 200
    return jsonify({'error': 'File or directory not found.'}), 404

# 下载文件
@app.route('/download/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found.'}), 404

# 移动文件或文件夹
@app.route('/move', methods=['POST'])
def move_file():
    data = request.json
    src = os.path.join(app.config['UPLOAD_FOLDER'], data['src'])
    dst = os.path.join(app.config['UPLOAD_FOLDER'], data['dst'])

    if not os.path.exists(src):
        return jsonify({'error': 'Source file/folder not found.'}), 404
    
    try:
        shutil.move(src, dst)
        return jsonify({'message': f'Moved {data["src"]} to {data["dst"]}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 启动应用
if __name__ == '__main__':
    init_db()  # 初始化数据库
    app.run(debug=True)

# 前端 HTML 内容，注册页面
REGISTER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container">
    <h2>Register</h2>
    <form method="POST">
        <div class="mb-3">
            <label for="username" class="form-label">Username</label>
            <input type="text" id="username" name="username" class="form-control" required>
        </div>
        <div class="mb-3">
            <label for="password" class="form-label">Password</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn btn-primary">Register</button>
    </form>
    <p class="mt-2">Already have an account? <a href="{{ url_for('login') }}">Login here</a></p>
</div>
</body>
</html>
'''

# 前端 HTML 内容，登录页面
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container">
    <h2>Login</h2>
    <form method="POST">
        <div class="mb-3">
            <label for="username" class="form-label">Username</label>
            <input type="text" id="username" name="username" class="form-control" required>
        </div>
        <div class="mb-3">
            <label for="password" class="form-label">Password</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn btn-primary">Login</button>
    </form>
    <p class="mt-2">Don't have an account? <a href="{{ url_for('register') }}">Register here</a></p>
</div>
</body>
</html>
'''

# 前端 HTML 内容，首页和文件上传
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask File Manager</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .file-item, .folder-item {
            border: 2px solid #ddd;
            margin: 5px;
            padding: 10px;
            text-align: center;
            cursor: pointer;
        }
        .file-item {
            background-color: #f8f9fa;
        }
        .folder-item {
            background-color: #e9ecef;
        }
        .container {
            margin-top: 20px;
        }
        .breadcrumb {
            background-color: transparent;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>Flask File Manager</h1>
    <h2>Welcome, {{ session['username'] }}!</h2>

    <!-- Breadcrumb for directory navigation -->
    <nav aria-label="breadcrumb">
        <ol class="breadcrumb" id="breadcrumb">
            <li class="breadcrumb-item"><a href="#" onclick="loadFiles('/')">Home</a></li>
        </ol>
    </nav>

    <!-- Upload Files Section -->
    <h2>Upload Files</h2>
    <form id="upload-form" enctype="multipart/form-data">
        <input type="file" name="file" multiple required>
        <button type="submit" class="btn btn-primary">Upload</button>
    </form>

    <!-- File List Section -->
    <h2>Files</h2>
    <div id="file-list" class="d-flex flex-wrap"></div>

    <!-- Modal for moving file/folder -->
    <div class="modal fade" id="moveModal" tabindex="-1" aria-labelledby="moveModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="moveModalLabel">Move File/Folder</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="move-dst" class="form-label">Destination</label>
                        <input type="text" class="form-control" id="move-dst" placeholder="Enter destination path">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" id="move-btn">Move</button>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Bootstrap and jQuery scripts -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script>
    // 加载文件并显示
    function loadFiles(path) {
        $.get('/files', function(data) {
            const fileList = $('#file-list');
            const breadcrumb = $('#breadcrumb');
            fileList.empty();

            // 更新breadcrumb
            const pathArray = path.split('/');
            breadcrumb.empty().append('<li class="breadcrumb-item"><a href="#" onclick="loadFiles(\'/\')">Home</a></li>');
            pathArray.forEach((part, idx) => {
                if (part) {
                    breadcrumb.append(`<li class="breadcrumb-item"><a href="#" onclick="loadFiles('/${pathArray.slice(0, idx + 1).join('/')}/')">${part}</a></li>`);
                }
            });

            // 遍历文件和文件夹并显示
            data.files.forEach(function(file) {
                const isFolder = file.includes('/');
                const item = $('<div>').addClass(isFolder ? 'folder-item' : 'file-item').text(file);
                
                if (isFolder) {
                    item.on('click', function() {
                        loadFiles(file);
                    });
                } else {
                    item.on('click', function() {
                        window.location.href = `/download/${file}`;
                    });
                }
                fileList.append(item);
            });
        });
    }

    // 上传文件
    $('#upload-form').on('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);

        $.ajax({
            url: '/upload',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                alert(response.message);
                loadFiles('/'); // 刷新文件列表
            },
            error: function(err) {
                alert('Error uploading files');
            }
        });
    });

    // 初始化加载文件
    loadFiles('/');
</script>
</body>
</html>
'''

