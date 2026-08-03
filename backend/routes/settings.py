from flask import Blueprint, request, jsonify
from database import get_db_connection
import pymysql
import json
from datetime import datetime

settings_bp = Blueprint('settings', __name__)


# ==================== 收费大类管理 v7.2.2 ====================

@settings_bp.route('/categories', methods=['GET'])
def get_categories():
    """获取所有收费大类，按类型分组"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, trans_type, created_at
        FROM category_records
        ORDER BY trans_type, created_at
    ''')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({
        'code': 200,
        'data': [dict(row) for row in rows]
    })


@settings_bp.route('/categories', methods=['POST'])
def add_category():
    """添加收费大类"""
    data = request.get_json()
    name = data.get('name', '').strip()
    trans_type = data.get('trans_type', 'income')

    if not name:
        return jsonify({'code': 400, 'message': '大类名称不能为空'}), 400
    if trans_type not in ('income', 'expense'):
        return jsonify({'code': 400, 'message': '类型必须是 income 或 expense'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO category_records (name, trans_type) VALUES (%s, %s)
        ''', (name, trans_type))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return jsonify({
            'code': 200,
            'message': '添加成功',
            'data': {'id': new_id, 'name': name, 'trans_type': trans_type}
        })
    except pymysql.IntegrityError:
        conn.close()
        return jsonify({'code': 400, 'message': '该大类已存在'}), 400


@settings_bp.route('/categories/<int:cat_id>', methods=['PUT'])
def update_category(cat_id):
    """更新收费大类名称"""
    data = request.get_json()
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'code': 400, 'message': '大类名称不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE category_records SET name = %s WHERE id = %s
        ''', (name, cat_id))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '更新成功'})
    except pymysql.IntegrityError:
        conn.close()
        return jsonify({'code': 400, 'message': '该大类已存在'}), 400


@settings_bp.route('/categories/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    """删除收费大类"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM category_records WHERE id = %s', (cat_id,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})


# ==================== 诊所信息 ====================

@settings_bp.route('/clinic', methods=['GET'])
def get_clinic_info():
    """获取诊所信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM system_settings WHERE `key` = %s', ('clinic_name',))
    row = cursor.fetchone()
    conn.close()
    return jsonify({
        'code': 200,
        'data': {'clinic_name': row['value'] if row else '我的口腔诊所'}
    })


@settings_bp.route('/clinic', methods=['PUT'])
def update_clinic_info():
    """更新诊所信息"""
    data = request.get_json()
    clinic_name = data.get('clinic_name', '').strip()
    if not clinic_name:
        return jsonify({'code': 400, 'message': '诊所名称不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        REPLACE INTO system_settings (`key`, value, updated_at) 
        VALUES (%s, %s, CURRENT_TIMESTAMP)
    ''', ('clinic_name', clinic_name))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


# ==================== 备份与恢复 v8.5（全量，修复完整表列表+精度） ====================

# v8.5: 完整的备份表列表（含 transfer_records 和 v8.5 新表）
_BACKUP_TABLES = [
    ('income_records', 'id'),
    ('expense_records', 'id'),
    ('transfer_records', 'id'),
    ('category_records', 'id'),
    ('bank_accounts', 'id'),
    ('account_subjects_l1', 'id'),
    ('account_subjects_l2', 'id'),
    ('category_subject_map', 'id'),
    ('system_settings', '`key`'),
    ('vouchers', 'id'),
    ('voucher_entries', 'id'),
    # v8.5 新增表
    ('accounting_periods', 'id'),
    ('subject_balances', 'id'),
    ('opening_balance_skip_log', 'id'),
    ('auto_backup_settings', 'id'),
    ('auto_backup_logs', 'id'),
]


def _fetch_table(cursor, table_name, order_by='id'):
    """辅助：读取整张表数据，Decimal转str保留精度，datetime转标准字符串"""
    try:
        cursor.execute(f'SELECT * FROM {table_name} ORDER BY {order_by}')
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for k, v in item.items():
                # v8.5: Decimal 转 str 保留精度（不再转 float）
                if hasattr(v, 'quantize'):
                    item[k] = str(v)
                # datetime/date 转标准字符串
                elif hasattr(v, 'strftime'):
                    if type(v).__name__ == 'date':
                        item[k] = v.strftime('%Y-%m-%d')
                    else:
                        item[k] = v.strftime('%Y-%m-%d %H:%M:%S')
            result.append(item)
        return result
    except Exception as e:
        # v8.5: 不再静默吞掉错误，记录到控制台
        print(f'[Backup] 读取表 {table_name} 失败: {e}')
        return []


@settings_bp.route('/backup', methods=['GET'])
def export_backup():
    """全量备份：导出所有业务数据（v8.5: 16张完整表）"""
    conn = get_db_connection()
    cursor = conn.cursor()

    backup_data = {
        'version': '8.5',
        'backup_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'manual_backup': True,
        'tables': {}
    }

    # v8.5: 使用完整表列表循环备份
    total_records = 0
    for table_name, order_by in _BACKUP_TABLES:
        table_data = _fetch_table(cursor, table_name, order_by)
        backup_data['tables'][table_name] = table_data
        total_records += len(table_data)

    conn.close()
    backup_data['record_count'] = total_records

    return jsonify({'code': 200, 'data': backup_data})


@settings_bp.route('/restore', methods=['POST'])
def import_backup():
    """全量恢复：先清空所有表，再逐表插入备份数据"""
    data = request.get_json()
    tables = data.get('tables', {})

    if not tables:
        return jsonify({'code': 400, 'message': '备份文件中没有数据'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    def _norm_date(val):
        """兼容各种日期格式，统一转为 MySQL DATETIME"""
        if not val or val == 'None' or val == 'null':
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(val, str):
            # 已经是标准格式
            if len(val) >= 19 and val[4] == '-' and val[10] in ' T':
                return val[:19].replace('T', ' ')
            # RFC格式: Sun, 31 May 2026 11:39:18 GMT
            if ',' in val:
                from email.utils import parsedate_to_datetime
                try:
                    dt = parsedate_to_datetime(val)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            # ISO格式: 2026-05-31T11:39:18
            if 'T' in val:
                return val[:19].replace('T', ' ')
        return str(val)[:19]

    try:
        # 1. 关闭外键检查
        cursor.execute('SET FOREIGN_KEY_CHECKS = 0')

        # 2. 清空所有业务表（v8.5: 完整表列表，含 transfer_records 和 v8.5 新表）
        clear_order = [
            'voucher_entries', 'vouchers',
            'opening_balance_skip_log', 'subject_balances', 'accounting_periods',
            'category_subject_map',
            'account_subjects_l2', 'account_subjects_l1',
            'bank_accounts', 'category_records',
            'transfer_records',  # v8.3 新增
            'expense_records', 'income_records',
            'auto_backup_logs', 'auto_backup_settings',
            'system_settings',
        ]
        for table in clear_order:
            try:
                cursor.execute(f'DELETE FROM {table}')
            except Exception as e:
                print(f'[Restore] 清空表 {table} 警告: {e}')

        # 辅助：安全获取数值（兼容 str/float/None）
        def _safe_num(val, default=0):
            if val is None or val == '' or val == 'None':
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        # 3. 逐表恢复数据
        # 3.1 收费大类
        for row in tables.get('category_records', []):
            cursor.execute('''
                INSERT INTO category_records (id, name, trans_type, created_at)
                VALUES (%s, %s, %s, %s)
            ''', (row.get('id'), row.get('name'), row.get('trans_type'), _norm_date(row.get('created_at'))))

        # 3.2 银行账号
        for row in tables.get('bank_accounts', []):
            cursor.execute('''
                INSERT INTO bank_accounts (id, account_name, bank_name, account_no, is_active, is_default, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('account_name'), row.get('bank_name'),
                  row.get('account_no'), row.get('is_active', 1),
                  row.get('is_default', 0), _norm_date(row.get('created_at'))))

        # 3.3 一级会计科目
        for row in tables.get('account_subjects_l1', []):
            cursor.execute('''
                INSERT INTO account_subjects_l1 (id, code, name, category, direction, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('code'), row.get('name'),
                  row.get('category'), row.get('direction'), _norm_date(row.get('created_at'))))

        # 3.4 二级会计科目
        for row in tables.get('account_subjects_l2', []):
            cursor.execute('''
                INSERT INTO account_subjects_l2 (id, parent_id, code, name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('parent_id'), row.get('code'),
                  row.get('name'), row.get('is_active', 1), _norm_date(row.get('created_at'))))

        # 3.5 科目映射
        for row in tables.get('category_subject_map', []):
            cursor.execute('''
                INSERT INTO category_subject_map (id, category_id, subject_l2_id, created_at)
                VALUES (%s, %s, %s, %s)
            ''', (row.get('id'), row.get('category_id'), row.get('subject_l2_id'), _norm_date(row.get('created_at'))))

        # 3.6 系统设置
        for row in tables.get('system_settings', []):
            cursor.execute('''
                INSERT INTO system_settings (`key`, value, updated_at)
                VALUES (%s, %s, %s)
            ''', (row.get('key'), row.get('value'), _norm_date(row.get('updated_at'))))

        # 3.7 收入记录（v8.5: _safe_num 兼容 str/float）
        inc_count = 0
        for row in tables.get('income_records', []):
            cursor.execute('''
                INSERT INTO income_records
                (id, trans_date, counterparty, category, item_name,
                 amount_receivable, amount_real, payment_method, remark, source_file, link_no, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), _norm_date(row.get('trans_date')), row.get('counterparty', ''),
                  row.get('category', ''), row.get('item_name', ''),
                  _safe_num(row.get('amount_receivable')), _safe_num(row.get('amount_real')),
                  row.get('payment_method', 'cash'), row.get('remark', ''),
                  row.get('source_file', ''), row.get('link_no'), _norm_date(row.get('created_at'))))
            inc_count += 1

        # 3.8 支出记录
        exp_count = 0
        for row in tables.get('expense_records', []):
            cursor.execute('''
                INSERT INTO expense_records
                (id, trans_date, counterparty, category, item_name,
                 amount_receivable, amount_real, payment_method, remark, source_file, link_no, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), _norm_date(row.get('trans_date')), row.get('counterparty', ''),
                  row.get('category', ''), row.get('item_name', ''),
                  _safe_num(row.get('amount_receivable')), _safe_num(row.get('amount_real')),
                  row.get('payment_method', 'cash'), row.get('remark', ''),
                  row.get('source_file', ''), row.get('link_no'), _norm_date(row.get('created_at'))))
            exp_count += 1

        # 3.9 资金调拨（v8.3 新增）
        tf_count = 0
        for row in tables.get('transfer_records', []):
            cursor.execute('''
                INSERT INTO transfer_records
                (id, transfer_date, from_bank_id, from_bank_name, to_bank_id, to_bank_name,
                 amount_planned, amount_real, fee, remark, link_no, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), _norm_date(row.get('transfer_date')),
                  row.get('from_bank_id'), row.get('from_bank_name', ''),
                  row.get('to_bank_id'), row.get('to_bank_name', ''),
                  _safe_num(row.get('amount_planned')), _safe_num(row.get('amount_real')),
                  _safe_num(row.get('fee', 0)), row.get('remark', ''),
                  row.get('link_no'), _norm_date(row.get('created_at'))))
            tf_count += 1

        # 3.10 凭证
        for row in tables.get('vouchers', []):
            cursor.execute('''
                INSERT INTO vouchers
                (id, voucher_no, voucher_date, source_type, source_table, source_id,
                 link_no, total_amount, status, audit_time, created_at, remark)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('voucher_no'), _norm_date(row.get('voucher_date')),
                  row.get('source_type'), row.get('source_table'), row.get('source_id'),
                  row.get('link_no'), _safe_num(row.get('total_amount')),
                  row.get('status', 'draft'), _norm_date(row.get('audit_time')),
                  _norm_date(row.get('created_at')), row.get('remark', '')))

        # 3.11 凭证分录
        for row in tables.get('voucher_entries', []):
            cursor.execute('''
                INSERT INTO voucher_entries
                (id, voucher_id, seq_no, subject_l1_code, subject_l2_code,
                 subject_name, direction, amount, bank_account_id, summary, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('voucher_id'), row.get('seq_no'),
                  row.get('subject_l1_code'), row.get('subject_l2_code'),
                  row.get('subject_name'), row.get('direction'),
                  _safe_num(row.get('amount')), row.get('bank_account_id'), row.get('summary', ''),
                  _norm_date(row.get('created_at'))))

        # 3.12 会计期间（v8.5 新增）
        for row in tables.get('accounting_periods', []):
            cursor.execute('''
                INSERT INTO accounting_periods (id, year, month, status, is_year_end, closed_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('year'), row.get('month'),
                  row.get('status', 'open'), row.get('is_year_end', 0),
                  _norm_date(row.get('closed_at')) if row.get('closed_at') else None,
                  _norm_date(row.get('created_at'))))

        # 3.13 科目期初余额（v8.5 新增）
        for row in tables.get('subject_balances', []):
            cursor.execute('''
                INSERT INTO subject_balances
                (id, period_id, subject_l1_code, subject_l2_code, opening_balance,
                 current_debit, current_credit, closing_balance, is_l1_entry, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('period_id'), row.get('subject_l1_code'),
                  row.get('subject_l2_code'), _safe_num(row.get('opening_balance')),
                  _safe_num(row.get('current_debit', 0)), _safe_num(row.get('current_credit', 0)),
                  _safe_num(row.get('closing_balance')), row.get('is_l1_entry', 0),
                  _norm_date(row.get('created_at'))))

        # 3.14 自动备份配置（v8.5 新增）
        for row in tables.get('auto_backup_settings', []):
            cursor.execute('''
                INSERT INTO auto_backup_settings (id, is_enabled, interval_hours, save_path, last_backup_time, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (row.get('id'), row.get('is_enabled', 1), row.get('interval_hours', 24),
                  row.get('save_path', '/www/wwwroot/dental-finance/backups'),
                  _norm_date(row.get('last_backup_time')) if row.get('last_backup_time') else None,
                  _norm_date(row.get('created_at')), _norm_date(row.get('updated_at'))))

        # 4. 重新开启外键检查
        cursor.execute('SET FOREIGN_KEY_CHECKS = 1')

        conn.commit()

        total = inc_count + exp_count + tf_count
        return jsonify({
            'code': 200,
            'message': f'成功恢复 {total} 条交易记录（收入{inc_count} + 支出{exp_count} + 调拨{tf_count}），系统设置和财务数据已同步还原'
        })

    except Exception as e:
        conn.rollback()
        # 确保外键检查重新开启
        try:
            cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
        except Exception:
            pass
        return jsonify({'code': 500, 'message': f'恢复失败: {str(e)}'})

    finally:
        conn.close()
