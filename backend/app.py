from flask import Flask, send_from_directory
from flask_cors import CORS
import os
from database import init_database

# 创建Flask应用
app = Flask(__name__, static_folder='static')
CORS(app)

# 配置
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 注册蓝图
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.import_excel import import_bp
from routes.bank_accounts import bank_bp
from routes.account_subjects import subjects_bp
from routes.vouchers import vouchers_bp
from routes.auto_backup import auto_backup_bp, start_auto_backup_scheduler
from routes.transfers import transfers_bp

app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
app.register_blueprint(import_bp, url_prefix='/api/import')
app.register_blueprint(bank_bp, url_prefix='/api/bank-accounts')
app.register_blueprint(subjects_bp, url_prefix='/api/account-subjects')
app.register_blueprint(vouchers_bp, url_prefix='/api/vouchers')
app.register_blueprint(auto_backup_bp, url_prefix='/api/auto-backup')
app.register_blueprint(transfers_bp, url_prefix='/api/transfers')

# v8.1 自动备份：首次请求时启动（避免模块导入时数据库未就绪）
_auto_backup_started = False

@app.before_request
def _ensure_auto_backup():
    global _auto_backup_started
    if not _auto_backup_started:
        _auto_backup_started = True
        try:
            start_auto_backup_scheduler()
        except Exception as e:
            print('[AutoBackup] 启动失败:', e)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


# 健康检查
@app.route('/api/health')
def health_check():
    return {'status': 'ok', 'message': '系统运行正常'}


if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
