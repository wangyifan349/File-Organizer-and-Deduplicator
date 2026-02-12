import os
import shutil
from flask import Flask, request, jsonify, send_file, session, redirect, url_for, render_template_string
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'change_this_secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///meta.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

### 数据库模型 -----------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))

class SharedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filepath = db.Column(db.String(300), unique=True)  # 绝对路径
    filename = db.Column(db.String(200))
    username = db.Column(db.String(150))               # 分享者

with app.app_context():
    db.create_all()

### 辅助 -----------------------------------
def get_user_folder(user=None):
    username = user or session.get('username')
    if not username: return None
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(path, exist_ok=True)
    return path

def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrap

def share_url(filepath):
    return url_for('download_shared', fid=abs(hash(filepath)), _external=True)

### ---------------- 用户注册/登录相关 API ---------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        data = request.get_json()
        username, password = data.get('username'), data.get('password')
        if User.query.filter_by(username=username, password=password).first():
            session['username'] = username
            return jsonify({'message': '登录成功'})
        return jsonify({'error': '用户名或密码错误'}), 403
    return render_template_string(LOGIN_TPL)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        data = request.get_json()
        username, password = data.get('username'), data.get('password')
        if not username or not password:
            return jsonify({'error': '参数缺失'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用户已存在'}), 400
        db.session.add(User(username=username, password=password))
        db.session.commit()
        return jsonify({'message': '注册成功'})
    return render_template_string(REGISTER_TPL)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'message': '登出成功'})

### ----------- 文件管理（主面板专用接口） -----------
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_TPL, username=session['username'])

@app.route('/files', methods=['GET'])
@login_required
def list_files():
    folder = get_user_folder()
    items = []
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        items.append({
            'name': name,
            'type': 'dir' if os.path.isdir(p) else 'file'
        })
    return jsonify(items)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    folder = get_user_folder()
    path = os.path.join(folder, filename)
    file.save(path)
    return jsonify({'message': '上传成功'})

@app.route('/download', methods=['GET'])
@login_required
def download():
    filename = request.args.get('file')
    folder = get_user_folder()
    if not filename:
        return jsonify({'error': '缺少参数'}), 400
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(path, as_attachment=True, download_name=filename)

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    data = request.get_json()
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': '缺少参数'}), 400
    folder = get_user_folder()
    target = os.path.join(folder, filename)
    if os.path.isdir(target):
        shutil.rmtree(target)
    elif os.path.isfile(target):
        os.remove(target)
        # 如有分享，移除
        s = SharedFile.query.filter_by(filepath=target, username=session['username']).first()
        if s: db.session.delete(s); db.session.commit()
    else:
        return jsonify({'error': '找不到目标'}), 404
    return jsonify({'message': '删除成功'})

@app.route('/move', methods=['POST'])
@login_required
def move():
    data = request.get_json()
    src, dst = data.get('src'), data.get('dst')
    if not src or not dst:
        return jsonify({'error': '缺少参数'}), 400
    folder = get_user_folder()
    srcp, dstp = os.path.join(folder, src), os.path.join(folder, dst)
    if not os.path.exists(srcp):
        return jsonify({'error': '源文件不存在'}), 404
    shutil.move(srcp, dstp)
    # 如有分享，跟着同步
    s = SharedFile.query.filter_by(filepath=srcp, username=session['username']).first()
    if s:
        s.filepath = dstp
        s.filename = dst
        db.session.commit()
    return jsonify({'message': '移动成功'})

### ---------- 分享相关 -------------------
@app.route('/share_files')
@login_required
def share_files():
    return render_template_string(SHARE_FILES_TPL)

@app.route('/share', methods=['POST'])
@login_required
def share():
    data = request.get_json()
    filename = data.get('filename')
    folder = get_user_folder()
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        return jsonify({'error': '找不到文件'}), 404
    if not SharedFile.query.filter_by(filepath=path).first():
        db.session.add(SharedFile(filepath=path, filename=filename, username=session['username']))
        db.session.commit()
    share_url_str = share_url(path)
    return jsonify({'message': '已分享', 'share_url': share_url_str})

@app.route('/unshare', methods=['POST'])
@login_required
def unshare():
    data = request.get_json()
    filename = data.get('filename')
    folder = get_user_folder()
    path = os.path.join(folder, filename)
    sf = SharedFile.query.filter_by(filepath=path, username=session['username']).first()
    if sf:
        db.session.delete(sf)
        db.session.commit()
        return jsonify({'message': '已取消分享'})
    return jsonify({'error': '该文件未分享'})

@app.route('/download_shared/<int:fid>', methods=['GET'])
def download_shared(fid):
    for sf in SharedFile.query.all():
        if abs(hash(sf.filepath)) == fid and os.path.isfile(sf.filepath):
            return send_file(sf.filepath, as_attachment=True)
    return "文件不存在或已取消分享", 404

@app.route('/manage_shares')
@login_required
def manage_shares():
    file_list = SharedFile.query.filter_by(username=session['username']).all()
    # 为每个文件拼share_url
    share_items = [{'filename': f.filename, 'share_url': share_url(f.filepath)} for f in file_list]
    return render_template_string(MANAGE_SHARES_TPL, share_items=share_items)

### --------- 页面模板(HTML) ----------------

LOGIN_TPL = '''
<!DOCTYPE html>
<html>
<head>
    <title>登录 | 网盘</title>
    <style>
        body{font-family:sans-serif;background:#f2f6fa;}
        .card{width:350px;margin:80px auto;background:white;padding:24px;border-radius:8px;box-shadow:0 2px 8px #ccc}
        .card h2{margin-top:0;}
        input{padding:8px;width:90%;margin-bottom:13px;}
        button{padding:8px 16px;}
        #msg{color:#b11;}
    </style>
</head>
<body>
<div class="card">
    <h2>用户登录</h2>
    <input id="user" placeholder="用户名"><br>
    <input id="pwd" type="password" placeholder="密码"><br>
    <button onclick="login()">登录</button>
    <button onclick="window.location='/register'">注册</button>
    <div id="msg"></div>
</div>
<script>
function post(url, data, cb){fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(cb);}
function login(){
    post('/login',{username:user.value,password:pwd.value},function(ret){
        if(ret.message){ window.location='/dashboard'; } else { msg.innerText=ret.error; }
    });
}
</script>
</body>
</html>
'''

REGISTER_TPL = '''
<!DOCTYPE html>
<html>
<head>
    <title>注册 | 网盘</title>
    <style>
        body{font-family:sans-serif;background:#f2f6fa;}
        .card{width:350px;margin:80px auto;background:white;padding:24px;border-radius:8px;box-shadow:0 2px 8px #ccc}
        .card h2{margin-top:0;}
        input{padding:8px;width:90%;margin-bottom:13px;}
        button{padding:8px 16px;}
        #msg{color:#b11;}
    </style>
</head>
<body>
<div class="card">
    <h2>用户注册</h2>
    <input id="user" placeholder="用户名"><br>
    <input id="pwd" type="password" placeholder="密码"><br>
    <button onclick="register()">注册</button>
    <button onclick="window.location='/login'">返回登录</button>
    <div id="msg"></div>
</div>
<script>
function post(url, data, cb){fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(cb);}
function register(){
    post('/register',{username:user.value,password:pwd.value},function(ret){
        if(ret.message){ alert('注册成功,请登录'); window.location='/login'; } else { msg.innerText=ret.error; }
    });
}
</script>
</body>
</html>
'''

DASHBOARD_TPL = '''
<!DOCTYPE html>
<html>
<head>
    <title>文件管理 | 网盘</title>
    <style>
        body{font-family:sans-serif;background:#f0f1f4;}
        .topbar{margin:0 0 30px 0;padding:18px 0 12px 0;background:#3e6bab;color:white;}
        .topbar .inner{width:860px;margin:auto; font-size:18px;}
        .topbar .user{float:right;}
        .menu{margin:20px 0;}
        .menu button{margin-right:10px;padding:6px 14px;border-radius:5px;border:0;background:#eee;}
        .filegrid{display:flex;flex-wrap:wrap;gap:20px;}
        .fileblock{background:white;border-radius:8px;padding:18px 18px 8px 18px;min-width:110px;max-width:150px;min-height:70px;box-shadow:0 2px 12px #ddd;position:relative;}
        .fileicon{font-size:34px;text-align:center;}
        .fname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;font-size:15px;margin:10px 0;}
        .fileop{font-size:13px;text-align:center;}
        .foldericon{color:#f3a403;}
        .fileiconfile{color:#599;}
        #msg{color:#d44;margin:8px 0 0 0;}
    </style>
</head>
<body>
<div class='topbar'><div class='inner'>
    网盘文件管理
    <span class='user'>欢迎 {{username}} 
      <button onclick="logout()" style="margin-left:16px;">登出</button>
    </span>
</div></div>
<div class='inner' style='width:860px;margin:auto;'>
    <div class='menu'>
      <input type="file" id="upload">
      <button onclick="up()">上传文件</button>
      <button onclick="window.location='/dashboard'">文件管理</button>
      <button onclick="window.location='/share_files'">文件分享</button>
      <button onclick="window.location='/manage_shares'">我的分享</button>
    </div>
    <div id="msg"></div>
    <div class="filegrid" id="filegrid"></div>
</div>
<script>
function post(url, data, cb){fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(cb);}
function get(url, cb){fetch(url).then(r=>r.json()).then(cb);}
function logout(){post('/logout',{},()=>{window.location='/login';});}
// 块状展示
function showFiles(){
    get('/files', function(ret){
        if(!Array.isArray(ret)) { filegrid.innerHTML="未登录"; return; }
        let s = "", icon, color;
        for(let item of ret){
            if(item.type==="dir"){
                icon="📁"; color="foldericon";
            }else{
                icon="🗎"; color="fileiconfile";
            }
            s += `<div class="fileblock">
                <div class="fileicon ${color}">${icon}</div>
                <div class="fname" title="${item.name}">${item.name}</div>
                <div class="fileop">
                  <button onclick="down('${item.name}')">下载</button>
                  <button onclick="del('${item.name}')">删除</button>
                  <button onclick="moveFile('${item.name}')">移动</button>
                </div>
            </div>`;
        }
        filegrid.innerHTML = s || '<div style="color:#999;margin:40px;">无文件，请上传</div>';
    });
}
function up(){
    let f = upload.files[0];
    if(!f) return;
    let fd = new FormData();
    fd.append('file', f);
    fetch('/upload', {method:'POST', body:fd}).then(r=>r.json())
        .then(ret=>{msg.innerText = ret.message||ret.error; showFiles(); upload.value=null;});
}
function down(fn){ location.href='/download?file='+encodeURIComponent(fn);}
function del(fn){
    post('/delete', {filename:fn}, ret=>{
        msg.innerText=(ret.message||ret.error); showFiles();
    });
}
function moveFile(src){
    let dst = prompt("输入目标文件名（包含扩展名）",src);
    if(!dst || dst==src) return;
    post('/move',{src:src, dst:dst},ret=>{
        msg.innerText = ret.message||ret.error; showFiles();
    });
}
showFiles();
</script>
</body>
</html>
'''

SHARE_FILES_TPL = '''
<!DOCTYPE html>
<html>
<head>
    <title>文件分享 | 网盘</title>
    <style>
        body{font-family:sans-serif;background:#f0f1f4;}
        .topbar{margin:0 0 30px 0;padding:18px 0 12px 0;background:#3e6bab;color:white;}
        .topbar .inner{width:860px;margin:auto; font-size:18px;}
        .topbar .user{float:right;}
        .menu{margin:20px 0;}
        .filegrid{display:flex;flex-wrap:wrap;gap:20px;}
        .fileblock{background:white;border-radius:8px;padding:18px 18px 8px 18px;min-width:140px;max-width:180px;box-shadow:0 2px 12px #ddd;position:relative;}
        .fileicon{font-size:30px;text-align:center;color:#608;}
        .fname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;font-size:15px;margin:10px 0;}
        .fileop button{margin:2px;}
        .share-url{font-size:12px;color:#36c;}
        #msg{color:#d44;margin:8px 0;}
    </style>
</head>
<body>
<div class='topbar'><div class='inner'>
    文件分享（选择要分享的文件）
    <span class='user'>
        <button onclick="window.location='/dashboard'">返回文件管理</button>
    </span>
</div></div>
<div class='inner' style='width:860px;margin:auto;'>
    <div id="msg"></div>
    <div class="filegrid" id="filegrid"></div>
</div>
<script>
function post(url, data, cb){fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(cb);}
function get(url, cb){fetch(url).then(r=>r.json()).then(cb);}
function showFiles(){
    get('/files', function(ret){
        let s = "";
        for(let item of ret){
            if(item.type=="file"){
                s += `<div class="fileblock">
                    <div class="fileicon">🗎</div>
                    <div class="fname" title="${item.name}">${item.name}</div>
                    <div class="fileop">
                        <button onclick="shareFile('${item.name}')">分享</button>
                    </div>
                </div>`;
            }
        }
        filegrid.innerHTML = s || "<div style='color:#999;margin:40px;'>无可分享文件</div>";
    });
}
function shareFile(fn){
    post('/share',{filename:fn},ret=>{
        msg.innerHTML = ret.message + "<br>分享链接: <span class='share-url' style='cursor:pointer;' onclick='copyToClipboard(\""+ret.share_url+"\")'>"+ret.share_url+"</span>";
    });
}
function copyToClipboard(text){
    navigator.clipboard.writeText(text);
    alert('已复制到剪贴板');
}
showFiles();
</script>
</body>
</html>
'''

MANAGE_SHARES_TPL = '''
<!DOCTYPE html>
<html>
<head>
    <title>我的分享 | 网盘</title>
    <style>
        body{font-family:sans-serif;background:#f0f1f4;}
        .topbar{margin:0 0 30px 0;padding:18px 0 12px 0;background:#3e6bab;color:white;}
        .topbar .inner{width:660px;margin:auto; font-size:18px;}
        .menu{margin:20px 0;}
        table{background:#fff;width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px #ddd;}
        th,td{padding:10px 7px;text-align:left;}
        tr:nth-child(even){background:#f7f7fa;}
        .later{text-align:right;}
        .share-url{font-size:13px;color:#008;}
        button{padding:3px 12px;}
    </style>
</head>
<body>
<div class='topbar'><div class='inner'>
    我的已分享文件
    <button onclick="window.location='/dashboard'" style="float:right;">返回管理</button>
</div></div>
<div class='inner' style='width:660px;margin:auto;'>
    <table>
        <tr><th>文件名</th><th>分享链接</th><th>操作</th></tr>
        {% for f in share_items %}
        <tr>
            <td>{{f.filename}}</td>
            <td>
                <span class='share-url' id='link{{loop.index}}'>{{f.share_url}}</span>
                <button onclick="copyToClipboard('link{{loop.index}}')" style="margin-left:10px;">复制</button>
            </td>
            <td>
                <button onclick="cancelShare('{{f.filename}}')">取消分享</button>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>
<script>
function cancelShare(fn){
    fetch('/unshare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:fn})})
    .then(r=>r.json()).then(ret=>{
        alert(ret.message||ret.error);
        location.reload();
    });
}
function copyToClipboard(spanid){
    let text = document.getElementById(spanid).innerText;
    navigator.clipboard.writeText(text);
    alert('已复制到剪贴板');
}
</script>
</body>
</html>
'''

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
