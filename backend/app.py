from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
import os
from utils.config_manager import config_exists, get_db_config
from database import init_database

# 创建Flask应用
app = Flask(__name__, static_folder='static')
CORS(app)

# 配置
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
app.register_blueprint(import_bp, url_prefix='/api/import')
app.register_blueprint(bank_bp, url_prefix='/api/bank-accounts')
app.register_blueprint(subjects_bp, url_prefix='/api/account-subjects')
app.register_blueprint(vouchers_bp, url_prefix='/api/vouchers')
app.register_blueprint(auto_backup_bp, url_prefix='/api/auto-backup')
app.register_blueprint(transfers_bp, url_prefix='/api/transfers')
app.register_blueprint(accounting_bp, url_prefix='/api/accounting')

# v8.1 自动备份：首次请求时启动
_auto_backup_started = False


@app.before_request
def _global_before_request():
    global _auto_backup_started

    # 1. 未安装时拦截业务 API（仅 /api/* 排除 /api/setup/* 和 /api/health）
    if not _is_installed():
        path = request.path
        if path.startswith('/api/') and not path.startswith('/api/setup/') and path != '/api/health':
            return jsonify({
                'code': 503,
                'message': '系统尚未初始化，请先访问首页完成安装向导',
                'data': {'setup_required': True}
            }), 503
        return  # 非 API 请求（如 /, /css, /js）允许通过

    # 2. 已安装：启动自动备份
    if not _auto_backup_started:
        _auto_backup_started = True
        try:
            start_auto_backup_scheduler()
        except Exception as e:
            print('[AutoBackup] 启动失败:', e)


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


# 健康检查
@app.route('/api/health')
def health_check():
    if _is_installed():
        return {'status': 'ok', 'message': '系统运行正常'}
    return {
        'status': 'setup_required',
        'message': '系统尚未初始化，请先访问首页完成安装向导'
    }


if __name__ == '__main__':
    if _is_installed():
        try:
            init_database()
        except Exception as e:
            print('[APP] Database init warning:', e)
    app.run(host='0.0.0.0', port=5000, debug=True)
