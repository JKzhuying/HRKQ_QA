from flask import Blueprint, request, jsonify
from database import get_db_connection
import pymysql

bank_bp = Blueprint('bank', __name__)


@bank_bp.route('/', methods=['GET'])
def get_banks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bank_accounts ORDER BY is_default DESC, created_at')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


@bank_bp.route('/', methods=['POST'])
def add_bank():
    data = request.get_json()
    name = data.get('account_name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '账户名称不能为空'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    is_default = 1 if data.get('is_default') else 0
    if is_default:
        cursor.execute('UPDATE bank_accounts SET is_default = 0')
    # v8.3.1: 自动分配二级科目代码
    cursor.execute("SELECT MAX(id) as max_id FROM bank_accounts")
    row = cursor.fetchone()
    next_id = (row['max_id'] or 0) + 1
    l2_code = f"1002.{next_id:02d}"
    l2_name = f"银行存款—{name}"
    cursor.execute('''
        INSERT INTO bank_accounts (account_name, bank_name, account_no, l2_code, l2_name, is_default)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (name, data.get('bank_name', ''), data.get('account_no', ''), l2_code, l2_name, is_default))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '添加成功'})


@bank_bp.route('/<int:bid>', methods=['PUT'])
def update_bank(bid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    is_default = 1 if data.get('is_default') else 0
    if is_default:
        cursor.execute('UPDATE bank_accounts SET is_default = 0')
    cursor.execute('''
        UPDATE bank_accounts SET account_name=%s, bank_name=%s, account_no=%s, is_default=%s, is_active=%s WHERE id=%s
    ''', (data.get('account_name', ''), data.get('bank_name', ''), data.get('account_no', ''),
        is_default, 1 if data.get('is_active', True) else 0, bid))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


@bank_bp.route('/<int:bid>', methods=['DELETE'])
def delete_bank(bid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_default FROM bank_accounts WHERE id=%s', (bid,))
    row = cursor.fetchone()
    if row and row['is_default']:
        conn.close()
        return jsonify({'code': 400, 'message': '默认账号不能删除，请先设置其他默认账号'}), 400
    cursor.execute('DELETE FROM bank_accounts WHERE id=%s', (bid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})


@bank_bp.route('/<int:bid>/toggle', methods=['POST'])
def toggle_bank(bid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active, is_default FROM bank_accounts WHERE id=%s', (bid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '账号不存在'}), 404
    new_active = 0 if row['is_active'] else 1
    if row['is_default'] and new_active == 0:
        conn.close()
        return jsonify({'code': 400, 'message': '默认账号不能停用'}), 400
    cursor.execute('UPDATE bank_accounts SET is_active=%s WHERE id=%s', (new_active, bid))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '状态已切换'})


@bank_bp.route('/<int:bid>/set-default', methods=['POST'])
def set_default_bank(bid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM bank_accounts WHERE id=%s', (bid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '账号不存在'}), 404
    if not row['is_active']:
        conn.close()
        return jsonify({'code': 400, 'message': '停用的账号不能设为默认'}), 400
    cursor.execute('UPDATE bank_accounts SET is_default = 0')
    cursor.execute('UPDATE bank_accounts SET is_default = 1 WHERE id=%s', (bid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已设为默认'})
