from flask import Blueprint, request, jsonify
from database import get_db_connection
from datetime import datetime, timedelta
import json
import os
import threading

auto_backup_bp = Blueprint('auto_backup', __name__)

# 全局定时器引用
_backup_timer = None
_timer_lock = threading.Lock()

# 需要备份的表（全量）
_BACKUP_TABLES = [
    'income_records', 'expense_records',
    'category_records', 'bank_accounts',
    'account_subjects_l1', 'account_subjects_l2',
    'category_subject_map', 'system_settings',
    'vouchers', 'voucher_entries',
]


def _get_db_conn():
    """获取数据库连接"""
    return get_db_connection()


def _get_backup_config():
    """获取当前备份配置"""
    conn = _get_db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM auto_backup_settings WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def _do_full_backup(save_path):
    """执行全量备份，返回 (success, file_path, message)"""
    try:
        # 确保目录存在
        os.makedirs(save_path, exist_ok=True)

        conn = _get_db_conn()
        cursor = conn.cursor()

        backup_data = {
            'version': '8.1',
            'backup_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'auto_backup': True,
            'tables': {}
        }

        for table in _BACKUP_TABLES:
            try:
                cursor.execute(f'SELECT * FROM {table}')
                rows = cursor.fetchall()
                table_data = []
                for row in rows:
                    item = dict(row)
                    for k, v in item.items():
                        if hasattr(v, 'quantize'):
                            item[k] = float(v)
                        elif hasattr(v, 'strftime'):
                            if type(v).__name__ == 'date':
                                item[k] = v.strftime('%Y-%m-%d')
                            else:
                                item[k] = v.strftime('%Y-%m-%d %H:%M:%S')
                    table_data.append(item)
                backup_data['tables'][table] = table_data
            except Exception:
                backup_data['tables'][table] = []

        # 统计记录数
        inc = len(backup_data['tables'].get('income_records', []))
        exp = len(backup_data['tables'].get('expense_records', []))
        backup_data['record_count'] = inc + exp

        conn.close()

        # 写入文件
        filename = 'dental_auto_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'
        file_path = os.path.join(save_path, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(file_path)
        return True, file_path, f'成功备份 {inc + exp} 条记录'

    except Exception as e:
        return False, '', str(e)


def _log_backup(status, file_path, file_size, message):
    """记录备份日志"""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO auto_backup_logs (status, file_path, file_size, message)
            VALUES (%s, %s, %s, %s)
        ''', (status, file_path, file_size, message))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _update_last_backup_time():
    """更新最后备份时间"""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE auto_backup_settings SET last_backup_time = NOW() WHERE id = 1
        ''')
        conn.commit()
        conn.close()
    except Exception:
        pass


def _schedule_next_backup():
    """调度下一次备份"""
    global _backup_timer

    config = _get_backup_config()
    if not config or not config.get('is_enabled'):
        return

    interval_hours = config.get('interval_hours', 24)
    if interval_hours <= 0:
        interval_hours = 24

    # 转换为秒
    interval_seconds = interval_hours * 3600

    def _backup_job():
        config = _get_backup_config()
        if not config or not config.get('is_enabled'):
            return

        save_path = config.get('save_path', '/www/wwwroot/dental-finance/backups')
        success, file_path, message = _do_full_backup(save_path)

        if success:
            file_size = os.path.getsize(file_path)
            _log_backup('success', file_path, file_size, message)
            _update_last_backup_time()
        else:
            _log_backup('failed', '', 0, message)

        # 调度下一次
        _schedule_next_backup()

    with _timer_lock:
        if _backup_timer:
            _backup_timer.cancel()
        _backup_timer = threading.Timer(interval_seconds, _backup_job)
        _backup_timer.daemon = True
        _backup_timer.start()


def start_auto_backup_scheduler():
    """启动自动备份调度器（应用启动时调用）"""
    config = _get_backup_config()
    if config and config.get('is_enabled'):
        _schedule_next_backup()
        print(f'[AutoBackup] 已启动，间隔 {config.get("interval_hours", 24)} 小时')
    else:
        print('[AutoBackup] 未启用')


def stop_auto_backup_scheduler():
    """停止自动备份调度器"""
    global _backup_timer
    with _timer_lock:
        if _backup_timer:
            _backup_timer.cancel()
            _backup_timer = None


# ========== API ==========

@auto_backup_bp.route('/config', methods=['GET'])
def get_config():
    """获取自动备份配置"""
    config = _get_backup_config()
    if not config:
        return jsonify({'code': 404, 'message': '配置不存在'}), 404
    return jsonify({'code': 200, 'data': config})


@auto_backup_bp.route('/config', methods=['POST'])
def save_config():
    """保存自动备份配置"""
    data = request.get_json()
    is_enabled = 1 if data.get('is_enabled') else 0
    interval_hours = data.get('interval_hours', 24)
    save_path = data.get('save_path', '/www/wwwroot/dental-finance/backups')

    # 校验
    try:
        interval_hours = int(interval_hours)
        if interval_hours < 1:
            interval_hours = 1
    except (ValueError, TypeError):
        interval_hours = 24

    if not save_path or save_path.strip() == '':
        return jsonify({'code': 400, 'message': '保存路径不能为空'}), 400

    conn = _get_db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE auto_backup_settings
        SET is_enabled = %s, interval_hours = %s, save_path = %s, updated_at = NOW()
        WHERE id = 1
    ''', (is_enabled, interval_hours, save_path))
    conn.commit()
    conn.close()

    # 重启调度器
    stop_auto_backup_scheduler()
    if is_enabled:
        _schedule_next_backup()

    return jsonify({
        'code': 200,
        'message': '保存成功' if is_enabled else '已停用自动备份',
        'data': {
            'is_enabled': is_enabled == 1,
            'interval_hours': interval_hours,
            'save_path': save_path,
        }
    })


@auto_backup_bp.route('/backup-now', methods=['POST'])
def backup_now():
    """立即执行一次备份"""
    config = _get_backup_config()
    save_path = config.get('save_path', '/www/wwwroot/dental-finance/backups') if config else '/www/wwwroot/dental-finance/backups'

    success, file_path, message = _do_full_backup(save_path)

    if success:
        file_size = os.path.getsize(file_path)
        _log_backup('success', file_path, file_size, message)
        _update_last_backup_time()
        return jsonify({
            'code': 200,
            'message': message,
            'data': {'file_path': file_path, 'file_size': file_size}
        })
    else:
        _log_backup('failed', '', 0, message)
        return jsonify({'code': 500, 'message': f'备份失败: {message}'}), 500


@auto_backup_bp.route('/logs', methods=['GET'])
def get_logs():
    """获取最近备份日志"""
    limit = request.args.get('limit', 20, type=int)
    conn = _get_db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, status, file_path, file_size, message, created_at
        FROM auto_backup_logs
        ORDER BY created_at DESC
        LIMIT %s
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        # 文件大小转为 KB/MB
        size = item.get('file_size', 0) or 0
        if size > 1024 * 1024:
            item['file_size_str'] = f'{size / (1024 * 1024):.2f} MB'
        elif size > 1024:
            item['file_size_str'] = f'{size / 1024:.2f} KB'
        else:
            item['file_size_str'] = f'{size} B'
        result.append(item)

    return jsonify({'code': 200, 'data': result})


@auto_backup_bp.route('/files', methods=['GET'])
def list_backup_files():
    """列出备份目录下的所有备份文件"""
    config = _get_backup_config()
    save_path = config.get('save_path', '/www/wwwroot/dental-finance/backups') if config else '/www/wwwroot/dental-finance/backups'

    files = []
    try:
        if os.path.exists(save_path):
            for fname in sorted(os.listdir(save_path), reverse=True):
                if fname.endswith('.json') and (fname.startswith('dental_auto_') or fname.startswith('dental_backup_')):
                    fpath = os.path.join(save_path, fname)
                    fsize = os.path.getsize(fpath)
                    ftime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M:%S')
                    files.append({
                        'name': fname,
                        'path': fpath,
                        'size': fsize,
                        'time': ftime,
                    })
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500

    return jsonify({'code': 200, 'data': files})
