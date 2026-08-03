from flask import Blueprint, request, jsonify
from database import get_db_connection, generate_voucher_no
from datetime import datetime

vouchers_bp = Blueprint('vouchers', __name__)


# ========== 自动生成凭证草稿（由transactions.py调用） ==========

def auto_generate_voucher(source_table, source_id, link_no):
    """根据收支/调拨记录自动生成凭证草稿 - v8.3.1 全面防重复"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 检查是否已有凭证（使用 link_no 或 source_table+source_id 双重检查）
        if link_no:
            cursor.execute('SELECT id FROM vouchers WHERE link_no = %s', (link_no,))
            if cursor.fetchone():
                return {'code': 400, 'message': '该记录已生成凭证'}

        # 如果 link_no 为空（旧数据），用 source_table + source_id 检查
        source_table_name = 'income_records' if source_table == 'income' else 'expense_records' if source_table == 'expense' else 'transfer_records'
        cursor.execute('SELECT id FROM vouchers WHERE source_table = %s AND source_id = %s', (source_table_name, source_id))
        if cursor.fetchone():
            return {'code': 400, 'message': '该记录已生成凭证'}

        # 2. 读取交易数据
        if source_table == 'transfer':
            return _generate_transfer_voucher_body(cursor, conn, source_id, link_no)

        table = source_table_name
        cursor.execute(f'''
            SELECT id, trans_date, counterparty, category, item_name,
                   amount_receivable, amount_real, payment_method, remark, link_no
            FROM {table} WHERE id = %s
        ''', (source_id,))
        row = cursor.fetchone()
        if not row:
            return {'code': 404, 'message': '记录不存在'}

        # 3. 查科目映射
        cursor.execute('''
            SELECT m.subject_l2_id, s.code as l2_code, s.name as l2_name,
                   p.code as l1_code, p.name as l1_name
            FROM category_subject_map m
            JOIN account_subjects_l2 s ON m.subject_l2_id = s.id
            JOIN account_subjects_l1 p ON s.parent_id = p.id
            JOIN category_records c ON m.category_id = c.id
            WHERE c.name = %s AND c.trans_type = %s
        ''', (row['category'] or '', source_table))
        mapping = cursor.fetchone()

        # 4. 生成凭证号
        vno = generate_voucher_no(cursor)
        total = float(row['amount_receivable'] or 0)

        # 5. 插入凭证头（link_no 为空时用短格式回退，确保不超过VARCHAR(20)）
        short_type = 'I' if source_table == 'income' else 'E' if source_table == 'expense' else 'T'
        actual_link_no = link_no or f"FK-{short_type}{source_id}"
        cursor.execute('''
            INSERT INTO vouchers (voucher_no, voucher_date, source_type, source_table, source_id, link_no, total_amount, status, remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s)
        ''', (vno, row['trans_date'], source_table, table, source_id, actual_link_no, total,
              f"{row['counterparty'] or ''}-{row['category'] or ''}"))
        vid = cursor.lastrowid

        # 6. 插入分录行
        seq = 1
        fee = float(row['amount_receivable'] or 0) - float(row['amount_real'] or 0)

        if source_table == 'income':
            cursor.execute('''
                INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
                VALUES (%s, %s, %s, %s, %s, 'debit', %s, %s)
            ''', (vid, seq, '1002', '1002.01', '银行存款—对公账户', row['amount_real'],
                  f"收-{row['counterparty'] or ''}-{row['category'] or ''}"))
            seq += 1
            if fee > 0:
                cursor.execute('''
                    INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
                    VALUES (%s, %s, %s, %s, %s, 'debit', %s, %s)
                ''', (vid, seq, '6603', '6603.01', '财务费用—手续费', fee,
                      f"手续费-{row['category'] or ''}"))
                seq += 1
            l1_code = mapping['l1_code'] if mapping else '6001'
            l2_code = mapping['l2_code'] if mapping else '6001.01'
            l2_name = mapping['l2_name'] if mapping else '主营业务收入'
            cursor.execute('''
                INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
                VALUES (%s, %s, %s, %s, %s, 'credit', %s, %s)
            ''', (vid, seq, l1_code, l2_code, l2_name, row['amount_receivable'],
                  f"{row['category'] or ''}收入-{row['counterparty'] or ''}"))
        else:
            l1_code = mapping['l1_code'] if mapping else '6602'
            l2_code = mapping['l2_code'] if mapping else '6602.02'
            l2_name = mapping['l2_name'] if mapping else '管理费用—办公费'
            cursor.execute('''
                INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
                VALUES (%s, %s, %s, %s, %s, 'debit', %s, %s)
            ''', (vid, seq, l1_code, l2_code, l2_name, row['amount_real'],
                  f"支-{row['category'] or ''}-{row['counterparty'] or ''}"))
            seq += 1
            cursor.execute('''
                INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
                VALUES (%s, %s, %s, %s, %s, 'credit', %s, %s)
            ''', (vid, seq, '1002', '1002.01', '银行存款—对公账户', row['amount_real'],
                  f"付-{row['counterparty'] or ''}"))

        conn.commit()
        return {'code': 200, 'message': '凭证已生成', 'data': {'voucher_no': vno, 'id': vid}}

    except Exception as e:
        conn.rollback()
        return {'code': 500, 'message': f'生成失败: {str(e)}'}
    finally:
        conn.close()


def _generate_transfer_voucher_body(cursor, conn, source_id, link_no):
    """生成资金调拨凭证草稿 v8.3.1 - 在 auto_generate_voucher 的 try 块内调用"""
    cursor.execute('''
        SELECT id, trans_date, from_account, to_account, from_bank_id, to_bank_id,
               amount_planned, amount_real, remark
        FROM transfer_records WHERE id = %s
    ''', (source_id,))
    row = cursor.fetchone()
    if not row:
        return {'code': 404, 'message': '调拨记录不存在'}

    vno = generate_voucher_no(cursor)
    planned = float(row['amount_planned'] or 0)
    real = float(row['amount_real'] or 0)
    fee = planned - real

    # 插入凭证头（短格式回退，确保不超过VARCHAR(20)）
    actual_link_no = link_no or f"FK-T{source_id}"
    cursor.execute('''
        INSERT INTO vouchers (voucher_no, voucher_date, source_type, source_table, source_id, link_no, total_amount, status, remark)
        VALUES (%s, %s, 'transfer', 'transfer_records', %s, %s, %s, 'draft', %s)
    ''', (vno, row['trans_date'], source_id, actual_link_no, planned,
          f"调拨-{row['from_account']}→{row['to_account']}"))
    vid = cursor.lastrowid

    seq = 1
    cursor.execute('''
        INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, bank_account_id, summary)
        VALUES (%s, %s, '1002', '1002.01', '银行存款—对公账户', 'debit', %s, %s, %s)
    ''', (vid, seq, real, row['to_bank_id'], f"转入-{row['to_account']}"))
    seq += 1

    if fee > 0:
        cursor.execute('''
            INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, summary)
            VALUES (%s, %s, '6603', '6603.01', '财务费用—手续费', 'debit', %s, %s)
        ''', (vid, seq, fee, f"调拨手续费-{row['from_account']}→{row['to_account']}"))
        seq += 1

    cursor.execute('''
        INSERT INTO voucher_entries (voucher_id, seq_no, subject_l1_code, subject_l2_code, subject_name, direction, amount, bank_account_id, summary)
        VALUES (%s, %s, '1002', '1002.01', '银行存款—对公账户', 'credit', %s, %s, %s)
    ''', (vid, seq, planned, row['from_bank_id'], f"转出-{row['from_account']}"))

    conn.commit()  # v8.3.1: 调拨路径直接return，此处必须commit
    return {'code': 200, 'message': '调拨凭证已生成', 'data': {'voucher_no': vno, 'id': vid}}


# ========== 凭证API ==========

@vouchers_bp.route('/', methods=['GET'])
def get_vouchers():
    """凭证列表"""
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    offset = (page - 1) * page_size

    conn = get_db_connection()
    cursor = conn.cursor()

    where = "WHERE 1=1"
    params = []
    if status:
        where += " AND status = %s"
        params.append(status)

    cursor.execute(f'SELECT COUNT(*) as total FROM vouchers {where}', params)
    total = cursor.fetchone()['total']

    cursor.execute(f'''
        SELECT id, voucher_no, voucher_date, source_type, link_no, total_amount, status, created_at, remark
        FROM vouchers {where}
        ORDER BY created_at DESC LIMIT %s OFFSET %s
    ''', params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        item = dict(r)
        item['total_amount'] = float(item['total_amount'])
        result.append(item)

    return jsonify({'code': 200, 'data': {'list': result, 'total': total, 'page': page, 'page_size': page_size}})


@vouchers_bp.route('/<int:vid>', methods=['GET'])
def get_voucher_detail(vid):
    """凭证详情（含分录行）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM vouchers WHERE id = %s', (vid,))
    v = cursor.fetchone()
    if not v:
        conn.close()
        return jsonify({'code': 404, 'message': '凭证不存在'}), 404

    cursor.execute('''
        SELECT e.*, b.account_name as bank_name
        FROM voucher_entries e
        LEFT JOIN bank_accounts b ON e.bank_account_id = b.id
        WHERE e.voucher_id = %s ORDER BY e.seq_no
    ''', (vid,))
    entries = cursor.fetchall()
    conn.close()

    voucher = dict(v)
    voucher['total_amount'] = float(voucher['total_amount'])
    entry_list = []
    for e in entries:
        item = dict(e)
        item['amount'] = float(item['amount'])
        entry_list.append(item)

    return jsonify({'code': 200, 'data': {'voucher': voucher, 'entries': entry_list}})


@vouchers_bp.route('/<int:vid>/audit', methods=['POST'])
def audit_voucher(vid):
    """审核凭证：选择银行账号 - v8.3.2 支持调拨凭证双银行选择"""
    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取凭证信息
    cursor.execute('SELECT status, source_type FROM vouchers WHERE id = %s', (vid,))
    v = cursor.fetchone()
    if not v:
        conn.close()
        return jsonify({'code': 404, 'message': '凭证不存在'}), 404
    if v['status'] == 'confirmed':
        conn.close()
        return jsonify({'code': 400, 'message': '凭证已审核'}), 400

    # ===== v8.3.2: 调拨凭证需要分别指定借方和贷方银行 =====
    if v['source_type'] == 'transfer':
        debit_bank_id = data.get('debit_bank_id')
        credit_bank_id = data.get('credit_bank_id')

        if not debit_bank_id:
            conn.close()
            return jsonify({'code': 400, 'message': '请选择借方银行（转入账户）'}), 400
        if not credit_bank_id:
            conn.close()
            return jsonify({'code': 400, 'message': '请选择贷方银行（转出账户）'}), 400

        # 检查两个银行是否都启用
        cursor.execute('SELECT id, is_active, l2_code, l2_name FROM bank_accounts WHERE id IN (%s, %s)',
                       (debit_bank_id, credit_bank_id))
        bank_rows = cursor.fetchall()
        if len(bank_rows) != 2:
            conn.close()
            return jsonify({'code': 400, 'message': '选择的银行账号不存在'}), 400
        for br in bank_rows:
            if not br['is_active']:
                conn.close()
                return jsonify({'code': 400, 'message': f"银行账号 {br['l2_name'] or br['id']} 已停用"}), 400

        # 获取借方银行信息
        cursor.execute('SELECT l2_code, l2_name FROM bank_accounts WHERE id = %s', (debit_bank_id,))
        debit_bank = cursor.fetchone()
        debit_l2_code = debit_bank['l2_code'] if debit_bank and debit_bank['l2_code'] else '1002.01'
        debit_l2_name = debit_bank['l2_name'] if debit_bank and debit_bank['l2_name'] else '银行存款—对公账户'

        # 获取贷方银行信息
        cursor.execute('SELECT l2_code, l2_name FROM bank_accounts WHERE id = %s', (credit_bank_id,))
        credit_bank = cursor.fetchone()
        credit_l2_code = credit_bank['l2_code'] if credit_bank and credit_bank['l2_code'] else '1002.01'
        credit_l2_name = credit_bank['l2_name'] if credit_bank and credit_bank['l2_name'] else '银行存款—对公账户'

        # 更新借方分录（转入账户）
        cursor.execute('''
            UPDATE voucher_entries SET bank_account_id = %s, subject_l2_code = %s, subject_name = %s
            WHERE voucher_id = %s AND direction = 'debit' AND subject_l1_code = '1002'
        ''', (debit_bank_id, debit_l2_code, debit_l2_name, vid))

        # 更新贷方分录（转出账户）
        cursor.execute('''
            UPDATE voucher_entries SET bank_account_id = %s, subject_l2_code = %s, subject_name = %s
            WHERE voucher_id = %s AND direction = 'credit' AND subject_l1_code = '1002'
        ''', (credit_bank_id, credit_l2_code, credit_l2_name, vid))

    else:
        # ===== 普通凭证（收入/支出）：使用单一银行 =====
        bank_id = data.get('bank_account_id')

        # 确定银行
        if not bank_id:
            cursor.execute('SELECT id FROM bank_accounts WHERE is_default = 1 AND is_active = 1')
            row = cursor.fetchone()
            bank_id = row['id'] if row else None

        if not bank_id:
            conn.close()
            return jsonify({'code': 400, 'message': '没有可用的银行账号，请先设置'}), 400

        # 检查银行是否启用
        cursor.execute('SELECT is_active FROM bank_accounts WHERE id = %s', (bank_id,))
        bank = cursor.fetchone()
        if not bank or not bank['is_active']:
            conn.close()
            return jsonify({'code': 400, 'message': '选择的银行账号已停用'}), 400

        # 更新银行存款分录行的银行账号、二级科目代码和名称
        cursor.execute('SELECT l2_code, l2_name FROM bank_accounts WHERE id = %s', (bank_id,))
        bank_row = cursor.fetchone()
        l2_code = bank_row['l2_code'] if bank_row and bank_row['l2_code'] else '1002.01'
        l2_name = bank_row['l2_name'] if bank_row and bank_row['l2_name'] else '银行存款—对公账户'

        if v['source_type'] == 'income':
            cursor.execute('''
                UPDATE voucher_entries SET bank_account_id = %s, subject_l2_code = %s, subject_name = %s
                WHERE voucher_id = %s AND direction = 'debit' AND subject_l1_code = '1002'
            ''', (bank_id, l2_code, l2_name, vid))
        else:
            cursor.execute('''
                UPDATE voucher_entries SET bank_account_id = %s, subject_l2_code = %s, subject_name = %s
                WHERE voucher_id = %s AND direction = 'credit' AND subject_l1_code = '1002'
            ''', (bank_id, l2_code, l2_name, vid))

    # 更新凭证状态
    cursor.execute('''
        UPDATE vouchers SET status = 'confirmed', audit_time = NOW() WHERE id = %s
    ''', (vid,))

    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '审核成功'})


@vouchers_bp.route('/<int:vid>', methods=['DELETE'])
def delete_voucher(vid):
    """删除凭证（仅限草稿状态）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM vouchers WHERE id = %s', (vid,))
    v = cursor.fetchone()
    if not v:
        conn.close()
        return jsonify({'code': 404, 'message': '凭证不存在'}), 404
    if v['status'] == 'confirmed':
        conn.close()
        return jsonify({'code': 400, 'message': '已审核的凭证不能删除'}), 400
    cursor.execute('DELETE FROM vouchers WHERE id = %s', (vid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})


# ========== 批量生成凭证 v8.0 ==========

@vouchers_bp.route('/batch-generate', methods=['POST'])
def batch_generate_vouchers():
    """根据选中的记录ID批量生成凭证草稿"""
    data = request.get_json()
    record_ids = data.get('record_ids', [])

    if not record_ids:
        return jsonify({'code': 400, 'message': '请选择要生成凭证的记录'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # 统计结果
    success = 0
    failed = 0
    errors = []
    generated = []

    # v8.3.1: 先查出所有记录的类型和 link_no，然后逐个调用 auto_generate_voucher
    # 不在此做重复检查，完全依赖 auto_generate_voucher 内部的双重检查
    record_info = []
    for rid in record_ids:
        cursor.execute('SELECT id, link_no, %s as src FROM income_records WHERE id = %s', ('income', rid))
        row = cursor.fetchone()
        if not row:
            cursor.execute('SELECT id, link_no, %s as src FROM expense_records WHERE id = %s', ('expense', rid))
            row = cursor.fetchone()
        if not row:
            cursor.execute('SELECT id, link_no, %s as src FROM transfer_records WHERE id = %s', ('transfer', rid))
            row = cursor.fetchone()
        if row:
            record_info.append((row['src'], rid, row['link_no']))
        else:
            failed += 1
            errors.append(f'记录 {rid} 不存在')
    conn.close()

    # 逐个生成 - auto_generate_voucher 内部有双重检查防重复
    for source_table, rid, link_no in record_info:
        try:
            result = auto_generate_voucher(source_table, rid, link_no)
            if result and result.get('code') == 200:
                success += 1
                generated.append({'record_id': rid, 'voucher_no': result['data']['voucher_no']})
            else:
                failed += 1
                msg = result.get('message', '生成失败') if result else '无返回'
                errors.append(f'记录 {rid}: {msg}')
        except Exception as e:
            failed += 1
            errors.append(f'记录 {rid}: {str(e)}')

    return jsonify({
        'code': 200,
        'message': f'生成完成：成功 {success} 条，失败 {failed} 条',
        'data': {
            'success': success,
            'failed': failed,
            'generated': generated,
            'errors': errors
        }
    })


@vouchers_bp.route('/clear-drafts', methods=['POST'])
def clear_draft_vouchers():
    """一键清理所有草稿凭证 + 孤儿凭证（已审核但对应交易记录不存在的凭证）v8.3.1"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 先删除所有草稿凭证的分录
    cursor.execute('''
        DELETE ve FROM voucher_entries ve
        JOIN vouchers v ON ve.voucher_id = v.id
        WHERE v.status = 'draft'
    ''')
    # 2. 删除草稿凭证
    cursor.execute('DELETE FROM vouchers WHERE status = %s', ('draft',))
    draft_deleted = cursor.rowcount

    # 3. 清理孤儿凭证（已审核但对应交易记录已不存在）
    # 获取所有凭证的 link_no 和 source_table
    cursor.execute('SELECT id, link_no, source_table FROM vouchers WHERE link_no IS NOT NULL')
    all_vouchers = cursor.fetchall()

    orphan_ids = []
    table_map = {
        'income_records': 'SELECT 1 FROM income_records WHERE link_no = %s',
        'expense_records': 'SELECT 1 FROM expense_records WHERE link_no = %s',
        'transfer_records': 'SELECT 1 FROM transfer_records WHERE link_no = %s',
    }
    for v in all_vouchers:
        check_sql = table_map.get(v['source_table'], 'SELECT 1 WHERE 1=0')
        cursor.execute(check_sql, (v['link_no'],))
        if not cursor.fetchone():
            orphan_ids.append(v['id'])

    orphan_deleted = 0
    if orphan_ids:
        placeholders = ','.join(['%s'] * len(orphan_ids))
        cursor.execute(f'DELETE FROM voucher_entries WHERE voucher_id IN ({placeholders})', orphan_ids)
        cursor.execute(f'DELETE FROM vouchers WHERE id IN ({placeholders})', orphan_ids)
        orphan_deleted = cursor.rowcount

    conn.commit()
    conn.close()

    total = draft_deleted + orphan_deleted
    msg = f'已清理 {total} 张凭证'
    if draft_deleted > 0 and orphan_deleted > 0:
        msg = f'已清理 {draft_deleted} 张草稿凭证 + {orphan_deleted} 张孤儿凭证'
    elif draft_deleted > 0:
        msg = f'已清理 {draft_deleted} 张草稿凭证'
    elif orphan_deleted > 0:
        msg = f'已清理 {orphan_deleted} 张孤儿凭证'

    return jsonify({'code': 200, 'message': msg, 'data': {'deleted': total, 'draft': draft_deleted, 'orphan': orphan_deleted}})


@vouchers_bp.route('/clear-all', methods=['POST'])
def clear_all_vouchers():
    """强制清空所有凭证（包括已审核）v8.3.1 - 仅用于紧急重置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM voucher_entries')
    cursor.execute('DELETE FROM vouchers')
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': f'已清空全部 {deleted} 张凭证', 'data': {'deleted': deleted}})


@vouchers_bp.route('/link-nos', methods=['GET'])
def get_linked_nos():
    """获取所有已生成凭证的 link_no 列表 v8.3.1"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT link_no FROM vouchers WHERE link_no IS NOT NULL')
    rows = cursor.fetchall()
    conn.close()
    result = [r['link_no'] for r in rows if r['link_no']]
    return jsonify({'code': 200, 'data': result})
