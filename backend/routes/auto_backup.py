"""
自动备份模块 - v8.5 (重构版)
方案B: APScheduler + 文件锁 + 启动时立即启动 + Decimal精度保留
"""
import os
import json
import fcntl  # Linux文件锁
import atexit
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_db_connection

auto_backup_bp = Blueprint('auto_backup', __name__)

# APScheduler 实例
_scheduler = None

# 全量备份表列表（v8.5: 补全所有表）
_BACKUP_TABLES = [
    # 业务核心表
    'income_records', 'expense_records', 'transfer_records',
    # 基础数据表
    'category_records', 'bank_accounts',
    'account_subjects_l1', 'account_subjects_l2', 'category_subject_map',
    # 凭证表
    'vouchers', 'voucher_entries',
    # 财务报表相关（v8.5新增）
    'accounting_periods', 'subject_balances', 'opening_balance_skip_log',
    # 系统配置表
    'system_settings', 'auto_backup_settings', 'auto_backup_logs',
    # 库存管理表（v8.5新增）
    'inventory_photos', 'suppliers', 'supplier_photos', 'inventory_records', 'inventory_logs', 'inventory_batch_counters',
    # 知情同意书表（v8.5.5新增）
    'informed_consents',
]

# 文件锁路径（用于防止多Worker重复备份）
_LOCK_FILE = '/tmp/dental-finance-backup.lock'


def _get_db_conn():
    return get_db_connection()


def _get_backup_config():
    """获取当前备份配置"""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auto_backup_settings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f'[AutoBackup] 读取配置失败: {e}')
        return None


def _json_serializer(obj):
    """自定义JSON序列化：Decimal→字符串保留精度，datetime→字符串"""
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, 'strftime'):
        if type(obj).__name__ == 'date':
            return obj.strftime('%Y-%m-%d')
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError(f'无法序列化类型: {type(obj)}')


def _acquire_lock():
    """获取文件锁，返回 (success, lock_fd)"""
    try:
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True, fd
    except (OSError, IOError):
        return False, None


def _release_lock(fd):
    """释放文件锁"""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except Exception:
        pass


def _do_full_backup(save_path):
    """执行全量备份，返回 (success, file_path, message, record_count)"""
    try:
        os.makedirs(save_path, exist_ok=True)
    except Exception as e:
        return False, '', f'无法创建备份目录 {save_path}: {e}', 0

    # 获取文件锁，防止多Worker同时备份
    lock_acquired, lock_fd = _acquire_lock()
    if not lock_acquired:
        print('[AutoBackup] 另一个进程正在备份，本次跳过')
        return False, '', '另一个进程正在备份', 0

    try:
        conn = _get_db_conn()
        cursor = conn.cursor()

        backup_data = {
            'version': '8.5',
            'backup_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'auto_backup': True,
            'tables': {}
        }

        total_records = 0
        failed_tables = []

        for table in _BACKUP_TABLES:
            try:
                cursor.execute(f'SELECT * FROM {table}')
                rows = cursor.fetchall()
                table_data = []
                for row in rows:
                    item = dict(row)
                    table_data.append(item)
                    total_records += 1
                backup_data['tables'][table] = table_data
            except Exception as e:
                failed_tables.append(f'{table}: {str(e)}')
                backup_data['tables'][table] = []

        conn.close()

        if failed_tables:
            print(f'[AutoBackup] 警告: 以下表备份失败: {", ".join(failed_tables)}')

        # 写入文件（使用自定义序列化保留Decimal精度）
        filename = 'dental_auto_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'
        file_path = os.path.join(save_path, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=_json_serializer)

        file_size = os.path.getsize(file_path)
        inc = len(backup_data['tables'].get('income_records', []))
        exp = len(backup_data['tables'].get('expense_records', []))
        tf = len(backup_data['tables'].get('transfer_records', []))

        msg = f'成功备份 {inc + exp + tf} 条交易记录({len(_BACKUP_TABLES)}张表)'
        if failed_tables:
            msg += f', {len(failed_tables)}张表失败'

        return True, file_path, msg, total_records

    except Exception as e:
        return False, '', f'备份执行异常: {e}', 0
    finally:
        _release_lock(lock_fd)


def _log_backup(status, file_path, file_size, message):
    """记录备份日志到数据库"""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO auto_backup_logs (status, file_path, file_size, message)
            VALUES (%s, %s, %s, %s)
        ''', (status, file_path, file_size, message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[AutoBackup] 写入日志失败: {e}')


def _update_last_backup_time():
    """更新最后备份时间"""
    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE auto_backup_settings SET last_backup_time = NOW() WHERE id = 1')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[AutoBackup] 更新时间失败: {e}')


def _backup_job():
    """定时备份任务（APScheduler调用）"""
    print(f'[AutoBackup] 定时任务触发: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    config = _get_backup_config()
    if not config:
        print('[AutoBackup] 无法读取配置，跳过本次备份')
        return
    if not config.get('is_enabled'):
        print('[AutoBackup] 自动备份已停用，跳过')
        return

    save_path = config.get('save_path', '/www/wwwroot/dental-finance/backups')
    success, file_path, message, count = _do_full_backup(save_path)

    if success:
        file_size = os.path.getsize(file_path)
        _log_backup('success', file_path, file_size, message)
        _update_last_backup_time()
        print(f'[AutoBackup] 备份成功: {message} → {file_path}')
    else:
        _log_backup('failed', '', 0, message)
        print(f'[AutoBackup] 备份失败: {message}')


def start_auto_backup_scheduler():
    """启动自动备份调度器（应用启动时调用，不依赖HTTP请求）"""
    global _scheduler

    config = _get_backup_config()
    if not config or not config.get('is_enabled'):
        print('[AutoBackup] 未启用，调度器未启动')
        return

    interval_hours = int(config.get('interval_hours', 24))
    if interval_hours < 1:
        interval_hours = 24

    # 停止已有调度器
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _backup_job,
        'interval',
        hours=interval_hours,
        id='auto_backup_job',
        replace_existing=True,
        misfire_grace_time=3600,  # 1小时宽限期
    )
    _scheduler.start()
    print(f'[AutoBackup] APScheduler 已启动，间隔 {interval_hours} 小时')


def stop_auto_backup_scheduler():
    """停止自动备份调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print('[AutoBackup] 调度器已停止')


def trigger_backup_now():
    """立即执行一次备份（供backup-now API调用）"""
    config = _get_backup_config()
    save_path = config.get('save_path', '/www/wwwroot/dental-finance/backups') if config else '/www/wwwroot/dental-finance/backups'

    print(f'[AutoBackup] 手动触发备份: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    success, file_path, message, count = _do_full_backup(save_path)

    if success:
        file_size = os.path.getsize(file_path)
        _log_backup('success', file_path, file_size, message)
        _update_last_backup_time()
        print(f'[AutoBackup] 手动备份成功: {message}')
        return True, file_path, file_size, message
    else:
        _log_backup('failed', '', 0, message)
        print(f'[AutoBackup] 手动备份失败: {message}')
        return False, '', 0, message


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
    """保存自动备份配置并重启调度器"""
    data = request.get_json()
    is_enabled = 1 if data.get('is_enabled') else 0
    interval_hours = data.get('interval_hours', 24)
    save_path = data.get('save_path', '/www/wwwroot/dental-finance/backups')

    try:
        interval_hours = int(interval_hours)
        if interval_hours < 1:
            interval_hours = 1
    except (ValueError, TypeError):
        interval_hours = 24

    if not save_path or save_path.strip() == '':
        return jsonify({'code': 400, 'message': '保存路径不能为空'}), 400

    try:
        conn = _get_db_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE auto_backup_settings
            SET is_enabled = %s, interval_hours = %s, save_path = %s, updated_at = NOW()
            WHERE id = 1
        ''', (is_enabled, interval_hours, save_path))
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({'code': 500, 'message': f'保存配置失败: {e}'}), 500

    # 重启调度器
    stop_auto_backup_scheduler()
    if is_enabled:
        start_auto_backup_scheduler()

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
    success, file_path, file_size, message = trigger_backup_now()
    if success:
        return jsonify({
            'code': 200,
            'message': message,
            'data': {'file_path': file_path, 'file_size': file_size}
        })
    else:
        return jsonify({'code': 500, 'message': f'备份失败: {message}'}), 500


@auto_backup_bp.route('/logs', methods=['GET'])
def get_logs():
    """获取最近备份日志"""
    limit = request.args.get('limit', 20, type=int)
    try:
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
            size = item.get('file_size', 0) or 0
            if size > 1024 * 1024:
                item['file_size_str'] = f'{size / (1024 * 1024):.2f} MB'
            elif size > 1024:
                item['file_size_str'] = f'{size / 1024:.2f} KB'
            else:
                item['file_size_str'] = f'{size} B'
            result.append(item)

        return jsonify({'code': 200, 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': f'查询日志失败: {e}'}), 500


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
