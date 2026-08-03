from flask import Blueprint, request, jsonify
from database import get_db_connection, generate_link_no
from datetime import datetime

transfers_bp = Blueprint('transfers', __name__)


@transfers_bp.route('/', methods=['POST'])
def create_transfer():
    """创建资金调拨记录 v8.3"""
    data = request.get_json()
    trans_date = data.get('trans_date', '')
    from_account = data.get('from_account', '').strip()
    to_account = data.get('to_account', '').strip()
    from_bank_id = data.get('from_bank_id')
    to_bank_id = data.get('to_bank_id')
    amount_planned = data.get('amount_planned', 0)
    amount_real = data.get('amount_real', 0)
    remark = data.get('remark', '')

    if not trans_date:
        return jsonify({'code': 400, 'message': '日期不能为空'}), 400
    if not from_account:
        return jsonify({'code': 400, 'message': '转出账户不能为空'}), 400
    if not to_account:
        return jsonify({'code': 400, 'message': '转入账户不能为空'}), 400
    try:
        amount_planned = float(amount_planned)
        amount_real = float(amount_real) if amount_real else amount_planned
        if amount_planned <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'code': 400, 'message': '调拨金额必须大于0'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    link_no = generate_link_no(cursor, 'TF')
    cursor.execute('''
        INSERT INTO transfer_records
        (trans_date, from_account, to_account, from_bank_id, to_bank_id,
         amount_planned, amount_real, amount, remark, link_no)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (trans_date, from_account, to_account, from_bank_id, to_bank_id,
          amount_planned, amount_real, amount_planned, remark, link_no))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'code': 200, 'message': '调拨记录已添加', 'data': {'id': new_id, 'link_no': link_no}})


@transfers_bp.route('/', methods=['GET'])
def get_transfers():
    """调拨记录列表"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    keyword = request.args.get('keyword', '')
    offset = (page - 1) * page_size

    conn = get_db_connection()
    cursor = conn.cursor()

    where = "WHERE 1=1"
    params = []

    if start_date:
        where += " AND trans_date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND trans_date <= %s"
        params.append(end_date)
    if keyword:
        where += " AND (from_account LIKE %s OR to_account LIKE %s OR remark LIKE %s)"
        like = f'%{keyword}%'
        params.extend([like, like, like])

    cursor.execute(f'SELECT COUNT(*) as total FROM transfer_records {where}', params)
    total = cursor.fetchone()['total']

    cursor.execute(f'''
        SELECT id, trans_date, from_account, to_account, from_bank_id, to_bank_id,
               amount_planned, amount_real, amount, remark, link_no, created_at
        FROM transfer_records {where}
        ORDER BY trans_date DESC, created_at DESC
        LIMIT %s OFFSET %s
    ''', params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        item['amount'] = float(item['amount'])
        item['amount_planned'] = float(item['amount_planned']) if item['amount_planned'] else 0
        item['amount_real'] = float(item['amount_real']) if item['amount_real'] else 0
        item['trans_type'] = 'transfer'
        result.append(item)

    return jsonify({'code': 200, 'data': {'list': result, 'total': total, 'page': page, 'page_size': page_size}})


@transfers_bp.route('/<int:tid>', methods=['PUT'])
def update_transfer(tid):
    """修改调拨记录"""
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM transfer_records WHERE id = %s', (tid,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    fields = []
    params = []
    for f in ['trans_date', 'from_account', 'to_account', 'amount', 'remark']:
        if f in data:
            fields.append(f'{f} = %s')
            params.append(data[f])
    if not fields:
        conn.close()
        return jsonify({'code': 400, 'message': '没有要修改的字段'}), 400

    params.append(tid)
    cursor.execute(f'UPDATE transfer_records SET {", ".join(fields)} WHERE id = %s', params)
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '修改成功'})


@transfers_bp.route('/<int:tid>', methods=['DELETE'])
def delete_transfer(tid):
    """删除调拨记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transfer_records WHERE id = %s', (tid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})


@transfers_bp.route('/list-all', methods=['GET'])
def list_all_transfers():
    """获取所有调拨记录（用于记录查询合并展示）"""
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND trans_date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND trans_date <= %s"
        params.append(end_date)

    cursor.execute(f'''
        SELECT id, trans_date, from_account, to_account, from_bank_id, to_bank_id,
               amount_planned, amount_real, amount, remark, link_no, created_at
        FROM transfer_records {where}
        ORDER BY trans_date DESC
    ''', params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        item['amount'] = float(item['amount'])
        item['amount_planned'] = float(item['amount_planned']) if item['amount_planned'] else 0
        item['amount_real'] = float(item['amount_real']) if item['amount_real'] else 0
        item['trans_type'] = 'transfer'
        item['counterparty'] = f"{item['from_account']} → {item['to_account']}"
        item['category'] = '资金调拨'
        item['item_name'] = item['remark'] or '资金调拨'
        item['amount_receivable'] = item['amount_planned']
        item['amount_real'] = item['amount_real']
        item['payment_method'] = 'transfer'
        result.append(item)

    return jsonify({'code': 200, 'data': result})
