from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
import os
from utils.config_manager import config_exists, get_db_config
from database import init_database

# 创建Flask应用
app = Flask(__name__, static_folder='static')
CORS(app)

# v8.6.6: 上传目录移到项目根目录（backend 外部），避免替换 backend 文件夹时丢失上传文件
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['UPLOAD_FOLDER'] = os.path.join(PROJECT_ROOT, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# v8.6.6: 启动时自动迁移旧目录文件（backend/uploads → 项目根目录/uploads）
import shutil
_old_uploads = os.path.join(os.path.dirname(__file__), 'uploads')
_new_uploads = app.config['UPLOAD_FOLDER']
if _old_uploads != _new_uploads and os.path.isdir(_old_uploads):
    for item in os.listdir(_old_uploads):
        src = os.path.join(_old_uploads, item)
        dst = os.path.join(_new_uploads, item)
        if not os.path.exists(dst):
            shutil.move(src, dst)
        elif os.path.isdir(src) and os.path.isdir(dst):
            # 目录已存在，合并子文件
            for sub in os.listdir(src):
                sub_src = os.path.join(src, sub)
                sub_dst = os.path.join(dst, sub)
                if not os.path.exists(sub_dst):
                    shutil.move(sub_src, sub_dst)
    print('[MIGRATE] 上传文件已从 backend/uploads 迁移到 uploads/')

# ==================== v9.0 安装状态检测 ====================
# 运行时动态检查（不要缓存！安装完成后会自动切换）
def _is_installed():
    return bool(config_exists() and get_db_config())


# ===== 始终注册所有蓝图 =====
# 安装向导蓝图
from routes.setup import setup_bp
app.register_blueprint(setup_bp, url_prefix='/api/setup')

# 业务蓝图（导入时无数据库操作，安全）
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.import_excel import import_bp
from routes.bank_accounts import bank_bp
from routes.account_subjects import subjects_bp
from routes.vouchers import vouchers_bp
from routes.auto_backup import auto_backup_bp, start_auto_backup_scheduler
from routes.transfers import transfers_bp
from routes.accounting import accounting_bp
from routes.inventory import inventory_bp
from routes.consents import consents_bp

app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
app.register_blueprint(import_bp, url_prefix='/api/import')
app.register_blueprint(bank_bp, url_prefix='/api/bank-accounts')
app.register_blueprint(subjects_bp, url_prefix='/api/account-subjects')
app.register_blueprint(vouchers_bp, url_prefix='/api/vouchers')
app.register_blueprint(auto_backup_bp, url_prefix='/api/auto-backup')
app.register_blueprint(transfers_bp, url_prefix='/api/transfers')
app.register_blueprint(accounting_bp, url_prefix='/api/accounting')
app.register_blueprint(inventory_bp, url_prefix='/api/inventory')
app.register_blueprint(consents_bp, url_prefix='/api/consents')


@app.before_request
def _global_before_request():
    # 未安装时拦截业务 API（仅 /api/* 排除 /api/setup/* 和 /api/health）
    if not _is_installed():
        path = request.path
        if path.startswith('/api/') and not path.startswith('/api/setup/') and path != '/api/health':
            return jsonify({
                'code': 503,
                'message': '系统尚未初始化，请先访问首页完成安装向导',
                'data': {'setup_required': True}
            }), 503
        return  # 非 API 请求（如 /, /css, /js）允许通过


# ==================== 动态路由 ====================

@app.route('/')
def index():
    """动态判断：已安装 → 系统首页，未安装 → 安装向导"""
    if _is_installed():
        return send_from_directory('static', 'index.html')
    return send_from_directory('static', 'setup.html')


@app.route('/css/<path:path>')
def serve_css(path):
    """CSS 静态文件（安装前后都需要）"""
    return send_from_directory('static/css', path)


@app.route('/js/<path:path>')
def serve_js(path):
    """JS 静态文件（安装前后都需要）"""
    return send_from_directory('static/js', path)


# v8.5: 提供上传文件访问（库存照片、供应商证照、签名图片、条码标签）
# v8.6.6: 使用绝对路径，上传目录在项目根目录（backend 外部）
@app.route('/uploads/<path:path>')
def serve_uploads(path):
    """提供 uploads 目录下的文件访问"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], path)


# 健康检查
@app.route('/api/health')
def health_check():
    if _is_installed():
        return {'status': 'ok', 'message': '系统运行正常'}
    return {
        'status': 'setup_required',
        'message': '系统尚未初始化，请先访问首页完成安装向导'
    }


# v8.5: 应用启动时初始化数据库表（uWSGI模式下也执行）
if _is_installed():
    try:
        init_database()
        print('[APP] Database initialized')
    except Exception as e:
        print('[APP] Database init warning:', e)
    # v8.5: 应用启动时立即启动自动备份（不依赖HTTP请求）
    try:
        start_auto_backup_scheduler()
    except Exception as e:
        print('[AutoBackup] 启动时初始化失败:', e)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
