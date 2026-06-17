from flask import Blueprint, request, jsonify
from database import get_db_connection, generate_link_no
from datetime import datetime

transactions_bp = Blueprint('transactions', __name__)

# ========== 双表辅助函数 v7.2.1 ==========

def _income_table():
    return 'income_records'

def _expense_table():
    return 'expense_records'

def _build_where_clause(params, table_alias=''):
    """构建查询条件（不含 trans_type，因为已按表分离）"""
    prefix = table_alias + '.' if table_alias else ''
    conditions = []
    values = []

    start_date = params.get('start_date')
    end_date = params.get('end_date')
    if start_date:
        conditions.append(f'{prefix}trans_date >= %s')
        values.append(start_date)
    if end_date:
        conditions.append(f'{prefix}trans_date <= %s')
        values.append(end_date)

    category = params.get('category')
    if category:
        conditions.append(f'{prefix}category = %s')
        values.append(category)

    item_name = params.get('item_name')
    if item_name:
        conditions.append(f'{prefix}item_name = %s')
        values.append(item_name)

    payment_method = params.get('payment_method')
    if payment_method:
        conditions.append(f'{prefix}payment_method = %s')
        values.append(payment_method)

    counterparty = params.get('counterparty')
    if counterparty:
        conditions.append(f'{prefix}counterparty LIKE %s')
        values.append(f'%{counterparty}%')

    keyword = params.get('keyword')
    if keyword:
        conditions.append(f'({prefix}counterparty LIKE %s OR {prefix}item_name LIKE %s OR {prefix}remark LIKE %s)')
        values.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

    where_clause = ' AND '.join(conditions) if conditions else '1=1'
    return where_clause, values


def _format_row(row, trans_type):
    """格式化行数据，添加 trans_type 字段"""
    item = dict(row)
    item['trans_type'] = trans_type
    item['amount_receivable'] = float(item['amount_receivable']) if item['amount_receivable'] is not None else 0.0
    item['amount_real'] = float(item['amount_real']) if item['amount_real'] is not None else 0.0
    return item


# ==================== 列表查询 ====================

@transactions_bp.route('/list', methods=['GET'])
def get_transactions():
    """获取交易列表 - 自动合并双表"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    trans_type = request.args.get('trans_type')

    conn = get_db_connection()
    cursor = conn.cursor()

    if trans_type == 'income':
        # 只查收入表
        where_clause, values = _build_where_clause(request.args)
        cursor.execute(f'SELECT COUNT(*) as total FROM income_records WHERE {where_clause}', values)
        total = cursor.fetchone()['total']
        cursor.execute(f'''
            SELECT id, trans_date, counterparty, category, item_name,
                   amount_receivable, amount_real, payment_method, remark, created_at, link_no
            FROM income_records WHERE {where_clause}
            ORDER BY trans_date DESC, id DESC LIMIT %s OFFSET %s
        ''', values + [page_size, (page - 1) * page_size])
        rows = cursor.fetchall()
        result_list = [_format_row(r, 'income') for r in rows]

    elif trans_type == 'expense':
        # 只查支出表
        where_clause, values = _build_where_clause(request.args)
        cursor.execute(f'SELECT COUNT(*) as total FROM expense_records WHERE {where_clause}', values)
        total = cursor.fetchone()['total']
        cursor.execute(f'''
            SELECT id, trans_date, counterparty, category, item_name,
                   amount_receivable, amount_real, payment_method, remark, created_at, link_no
            FROM expense_records WHERE {where_clause}
            ORDER BY trans_date DESC, id DESC LIMIT %s OFFSET %s
        ''', values + [page_size, (page - 1) * page_size])
        rows = cursor.fetchall()
        result_list = [_format_row(r, 'expense') for r in rows]

    else:
        # v8.3: 合并收入+支出+调拨
        where_inc, values_inc = _build_where_clause(request.args, 'i')
        where_exp, values_exp = _build_where_clause(request.args, 'e')

        # 调拨WHERE（支持日期范围）
        tf_where = "1=1"
        tf_values = []
        sd = request.args.get('start_date', '')
        ed = request.args.get('end_date', '')
        if sd:
            tf_where += " AND trans_date >= %s"
            tf_values.append(sd)
        if ed:
            tf_where += " AND trans_date <= %s"
            tf_values.append(ed)

        # 总数
        cursor.execute(f'''
            SELECT COUNT(*) as total FROM (
                SELECT id FROM income_records i WHERE {where_inc}
                UNION ALL
                SELECT id FROM expense_records e WHERE {where_exp}
                UNION ALL
                SELECT id FROM transfer_records t WHERE {tf_where}
            ) t
        ''', values_inc + values_exp + tf_values)
        total = cursor.fetchone()['total']

        # 数据（UNION ALL + 排序）v8.3.1: 增加link_no
        cursor.execute(f'''
            SELECT * FROM (
                SELECT id, trans_date, counterparty, category, item_name,
                       amount_receivable, amount_real, payment_method, remark, created_at,
                       link_no, 'income' as trans_type
                FROM income_records i WHERE {where_inc}
                UNION ALL
                SELECT id, trans_date, counterparty, category, item_name,
                       amount_receivable, amount_real, payment_method, remark, created_at,
                       link_no, 'expense' as trans_type
                FROM expense_records e WHERE {where_exp}
                UNION ALL
                SELECT id, trans_date,
                       CONCAT(from_account, ' → ', to_account) as counterparty,
                       '资金调拨' as category, COALESCE(remark, '资金调拨') as item_name,
                       amount_planned as amount_receivable, amount_real as amount_real,
                       'transfer' as payment_method, remark, created_at,
                       link_no, 'transfer' as trans_type
                FROM transfer_records t WHERE {tf_where}
            ) t ORDER BY trans_date DESC, id DESC LIMIT %s OFFSET %s
        ''', values_inc + values_exp + tf_values + [page_size, (page - 1) * page_size])
        rows = cursor.fetchall()
        result_list = []
        for row in rows:
            item = dict(row)
            item['amount_receivable'] = float(item['amount_receivable']) if item['amount_receivable'] is not None else 0.0
            item['amount_real'] = float(item['amount_real']) if item['amount_real'] is not None else 0.0
            result_list.append(item)

    conn.close()
    return jsonify({
        'code': 200,
        'data': {'list': result_list, 'total': total, 'page': page, 'page_size': page_size}
    })


# ==================== 单条查询 ====================

@transactions_bp.route('/<int:trans_id>', methods=['GET'])
def get_transaction(trans_id):
    """获取单条交易详情 - 同时查两张表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 先查收入表
    cursor.execute('SELECT * FROM income_records WHERE id = %s', (trans_id,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return jsonify({'code': 200, 'data': _format_row(row, 'income')})
    # 再查支出表
    cursor.execute('SELECT * FROM expense_records WHERE id = %s', (trans_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({'code': 200, 'data': _format_row(row, 'expense')})
    return jsonify({'code': 404, 'message': '记录不存在'}), 404


# ==================== 创建 ====================

@transactions_bp.route('/', methods=['POST'])
def add_transaction():
    """添加交易记录 - 根据类型写入对应表"""
    data = request.get_json()
    trans_type = data.get('trans_type')
    trans_date = data.get('trans_date')
    counterparty = data.get('counterparty', '')
    category = data.get('category', '')
    item_name = data.get('item_name', '')
    amount_receivable = data.get('amount_receivable', 0)
    amount_real = data.get('amount_real', 0)
    payment_method = data.get('payment_method', 'cash')
    remark = data.get('remark', '')

    if not trans_date:
        return jsonify({'code': 400, 'message': '日期不能为空'}), 400

    table = 'income_records' if trans_type == 'income' else 'expense_records'
    conn = get_db_connection()
    cursor = conn.cursor()

    # 生成 link_no v8.0
    link_no = generate_link_no(cursor)

    cursor.execute(f'''
        INSERT INTO {table} (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, link_no)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, link_no))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'code': 200,
        'message': '添加成功',
        'data': {'id': new_id, 'link_no': link_no}
    })


# ==================== 更新 ====================

@transactions_bp.route('/<int:trans_id>', methods=['PUT'])
def update_transaction(trans_id):
    """更新交易记录 - 同时查两张表确定记录位置"""
    data = request.get_json()
    trans_type = data.get('trans_type')
    conn = get_db_connection()
    cursor = conn.cursor()

    # 先确定记录在哪张表
    cursor.execute('SELECT id FROM income_records WHERE id = %s', (trans_id,))
    is_income = cursor.fetchone() is not None
    cursor.execute('SELECT id FROM expense_records WHERE id = %s', (trans_id,))
    is_expense = cursor.fetchone() is not None

    if not is_income and not is_expense:
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    # 如果类型变更，需要跨表移动
    new_type = trans_type or ('income' if is_income else 'expense')
    if new_type == 'income' and is_expense:
        # 从支出表移到收入表
        cursor.execute('''
            INSERT INTO income_records (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, created_at)
            SELECT trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, created_at
            FROM expense_records WHERE id = %s
        ''', (trans_id,))
        cursor.execute('DELETE FROM expense_records WHERE id = %s', (trans_id,))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '更新成功（已移至收入表）'})
    elif new_type == 'expense' and is_income:
        # 从收入表移到支出表
        cursor.execute('''
            INSERT INTO expense_records (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, created_at)
            SELECT trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, created_at
            FROM income_records WHERE id = %s
        ''', (trans_id,))
        cursor.execute('DELETE FROM income_records WHERE id = %s', (trans_id,))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '更新成功（已移至支出表）'})

    # 同表内更新
    table = 'income_records' if is_income else 'expense_records'
    fields = []
    values = []
    for field in ['trans_date', 'counterparty', 'category', 'item_name',
                  'amount_receivable', 'amount_real', 'payment_method', 'remark']:
        if field in data:
            fields.append(f'{field} = %s')
            values.append(data[field])
    if not fields:
        conn.close()
        return jsonify({'code': 400, 'message': '没有要更新的字段'}), 400
    values.append(trans_id)
    cursor.execute(f'UPDATE {table} SET {", ".join(fields)} WHERE id = %s', values)
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


# ==================== 删除 ====================

@transactions_bp.route('/<int:trans_id>', methods=['DELETE'])
def delete_transaction(trans_id):
    """删除交易记录 - v8.3 同时查三张表（收入/支出/调拨）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 先尝试删除收入/支出
    cursor.execute('DELETE FROM income_records WHERE id = %s', (trans_id,))
    if cursor.rowcount > 0:
        conn.commit(); conn.close()
        return jsonify({'code': 200, 'message': '删除成功'})
    cursor.execute('DELETE FROM expense_records WHERE id = %s', (trans_id,))
    if cursor.rowcount > 0:
        conn.commit(); conn.close()
        return jsonify({'code': 200, 'message': '删除成功'})
    # v8.3: 再尝试删除调拨记录
    cursor.execute('DELETE FROM transfer_records WHERE id = %s', (trans_id,))
    conn.commit(); conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})


# ==================== 批量删除 ====================

@transactions_bp.route('/batch-delete', methods=['POST'])
def batch_delete_transactions():
    """批量删除 - v8.3 同时操作三张表"""
    ids = request.get_json().get('ids', [])
    if not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的记录'}), 400
    placeholders = ','.join(['%s'] * len(ids))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'DELETE FROM income_records WHERE id IN ({placeholders})', ids)
    inc_deleted = cursor.rowcount
    cursor.execute(f'DELETE FROM expense_records WHERE id IN ({placeholders})', ids)
    exp_deleted = cursor.rowcount
    cursor.execute(f'DELETE FROM transfer_records WHERE id IN ({placeholders})', ids)
    tf_deleted = cursor.rowcount
    conn.commit(); conn.close()
    return jsonify({'code': 200, 'message': f'已删除 {inc_deleted + exp_deleted + tf_deleted} 条记录'})


# ==================== 清空所有 ====================

@transactions_bp.route('/clear', methods=['POST'])
def clear_all_transactions():
    """清空两张表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM income_records')
    cursor.execute('DELETE FROM expense_records')
    conn.commit(); conn.close()
    return jsonify({'code': 200, 'message': '已清空所有记录'})


# ==================== 统计 ====================

@transactions_bp.route('/statistics/summary', methods=['GET'])
def get_summary():
    """收支汇总统计 - 合并双表"""
    where_clause_inc, values_inc = _build_where_clause(request.args, 'i')
    where_clause_exp, values_exp = _build_where_clause(request.args, 'e')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 总收入
    cursor.execute(f'SELECT COALESCE(SUM(amount_real), 0) as total FROM income_records i WHERE {where_clause_inc}', values_inc)
    total_income = float(cursor.fetchone()['total'])

    # 总支出（v8.2排除资金调拨）
    cursor.execute(f"SELECT COALESCE(SUM(amount_real), 0) as total FROM expense_records e WHERE {where_clause_exp} AND category != '资金调拨'", values_exp)
    total_expense = float(cursor.fetchone()['total'])

    # 按收费大类统计收入
    cursor.execute(f'''
        SELECT category, 'income' as trans_type, COALESCE(SUM(amount_real), 0) as total
        FROM income_records i WHERE {where_clause_inc}
        GROUP BY category ORDER BY total DESC
    ''', values_inc)
    by_category_inc = [{**dict(r), 'total': float(r['total'])} for r in cursor.fetchall()]

    # 按收费大类统计支出（v8.2排除资金调拨）
    cursor.execute(f"SELECT category, 'expense' as trans_type, COALESCE(SUM(amount_real), 0) as total FROM expense_records e WHERE {where_clause_exp} AND category != '资金调拨' GROUP BY category ORDER BY total DESC", values_exp)
    by_category_exp = [{**dict(r), 'total': float(r['total'])} for r in cursor.fetchall()]

    # 按支付方式统计收入
    cursor.execute(f'''
        SELECT payment_method, COALESCE(SUM(amount_real), 0) as total
        FROM income_records i WHERE {where_clause_inc}
        GROUP BY payment_method
    ''', values_inc)
    by_payment = [{**dict(r), 'total': float(r['total'])} for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        'code': 200,
        'data': {
            'total_income': total_income,
            'total_expense': total_expense,
            'balance': total_income - total_expense,
            'by_category': by_category_inc + by_category_exp,
            'by_payment': by_payment
        }
    })


@transactions_bp.route('/statistics/monthly', methods=['GET'])
def get_monthly_statistics():
    """月度统计 - 合并双表"""
    year = request.args.get('year', datetime.now().year, type=int)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DATE_FORMAT(trans_date, '%%Y-%%m') as month,
               'income' as trans_type, COALESCE(SUM(amount_real), 0) as total
        FROM income_records WHERE YEAR(trans_date) = %s
        GROUP BY month ORDER BY month
    ''', (str(year),))
    inc_rows = cursor.fetchall()

    cursor.execute('''
        SELECT DATE_FORMAT(trans_date, '%%Y-%%m') as month,
               'expense' as trans_type, COALESCE(SUM(amount_real), 0) as total
        FROM expense_records WHERE YEAR(trans_date) = %s AND category != '资金调拨'
        GROUP BY month ORDER BY month
    ''', (str(year),))
    exp_rows = cursor.fetchall()

    conn.close()
    result = []
    for r in inc_rows + exp_rows:
        item = dict(r)
        item['total'] = float(item['total'])
        result.append(item)
    return jsonify({'code': 200, 'data': result})


@transactions_bp.route('/statistics/daily', methods=['GET'])
def get_daily_statistics():
    """日度统计 - 合并双表"""
    month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT trans_date as date, 'income' as trans_type,
               COALESCE(SUM(amount_real), 0) as total, COUNT(*) as count
        FROM income_records WHERE DATE_FORMAT(trans_date, '%%Y-%%m') = %s
        GROUP BY trans_date ORDER BY trans_date
    ''', (month,))
    inc_rows = cursor.fetchall()

    cursor.execute('''
        SELECT trans_date as date, 'expense' as trans_type,
               COALESCE(SUM(amount_real), 0) as total, COUNT(*) as count
        FROM expense_records WHERE DATE_FORMAT(trans_date, '%%Y-%%m') = %s AND category != '资金调拨'
        GROUP BY trans_date ORDER BY trans_date
    ''', (month,))
    exp_rows = cursor.fetchall()

    conn.close()
    result = []
    for r in inc_rows + exp_rows:
        item = dict(r)
        item['total'] = float(item['total'])
        result.append(item)
    return jsonify({'code': 200, 'data': result})
