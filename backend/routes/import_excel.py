from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import os
from utils.excel_parser import parse_excel_file, import_to_database
from database import get_db_connection

import_bp = Blueprint('import', __name__)


def get_valid_categories():
    """从数据库读取所有有效收费大类名称 v7.2.3"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM category_records')
        rows = cursor.fetchall()
        conn.close()
        return set(r['name'] for r in rows if r['name'])
    except Exception:
        return set()


def get_bank_accounts():
    """从数据库读取所有银行账号名称 v8.3"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT account_name FROM bank_accounts WHERE is_active = 1')
        rows = cursor.fetchall()
        conn.close()
        return set(r['account_name'] for r in rows if r['account_name'])
    except Exception:
        return set()


def find_duplicates(records):
    """
    比对records与数据库中已有数据，返回重复记录的索引列表
    比对规则：trans_date + counterparty + category + item_name + amount_real 全部相同
    v7.2.1: 同时比对 income_records 和 expense_records 两张表
    """
    if not records:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()

    # 从两张表获取比对字段
    cursor.execute('''
        SELECT trans_date, counterparty, category, item_name, amount_real
        FROM income_records
    ''')
    inc_existing = cursor.fetchall()

    cursor.execute('''
        SELECT trans_date, counterparty, category, item_name, amount_real
        FROM expense_records
    ''')
    exp_existing = cursor.fetchall()
    conn.close()

    # 合并构建特征集合
    existing_keys = set()
    for row in inc_existing + exp_existing:
        key = (
            str(row['trans_date']) if row['trans_date'] else '',
            str(row['counterparty']) if row['counterparty'] else '',
            str(row['category']) if row['category'] else '',
            str(row['item_name']) if row['item_name'] else '',
            float(row['amount_real']) if row['amount_real'] else 0.0
        )
        existing_keys.add(key)

    # 检查每条新记录是否重复
    duplicate_indices = []
    for idx, record in enumerate(records):
        new_key = (
            record.get('trans_date', ''),
            record.get('counterparty', ''),
            record.get('category', ''),
            record.get('item_name', ''),
            record.get('amount_real', 0.0)
        )
        if new_key in existing_keys:
            duplicate_indices.append(idx)

    return duplicate_indices


@import_bp.route('/compare', methods=['POST'])
def compare_records():
    """比对导入数据与现有数据，返回重复记录索引"""
    data = request.get_json()
    records = data.get('records', [])
    if not records:
        return jsonify({'code': 200, 'data': {'duplicates': [], 'total': 0, 'duplicate_count': 0}})
    
    duplicate_indices = find_duplicates(records)
    return jsonify({
        'code': 200,
        'data': {
            'duplicates': duplicate_indices,
            'total': len(records),
            'duplicate_count': len(duplicate_indices)
        }
    })


@import_bp.route('/excel', methods=['POST'])
def import_excel():
    """导入Excel文件
    支持参数：skip_duplicates=true（跳过重复记录）
    """
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '请选择文件'}), 400

    # 检查文件扩展名
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'code': 400, 'message': '只支持 .xlsx 或 .xls 格式'}), 400
    
    # 获取是否跳过重复的参数
    skip_duplicates = request.form.get('skip_duplicates') == 'true'

    # 保存文件
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        # 从数据库读取有效收费大类和银行账号 v8.3
        valid_categories = get_valid_categories()
        bank_accounts = get_bank_accounts()
        # 解析Excel
        result = parse_excel_file(filepath, valid_categories, bank_accounts)

        if not result['success']:
            return jsonify({'code': 400, 'message': result.get('error', '解析失败')})

        records = result['records']

        if not records:
            return jsonify({
                'code': 200,
                'message': '没有可导入的数据',
                'data': {
                    'stats': result['stats'],
                    'errors': result['errors']
                }
            })
        
        # 如果要求跳过重复，先比对
        skipped_count = 0
        if skip_duplicates:
            duplicate_indices = find_duplicates(records)
            if duplicate_indices:
                skipped_count = len(duplicate_indices)
                records = [r for i, r in enumerate(records) if i not in duplicate_indices]

        if not records:
            return jsonify({
                'code': 200,
                'message': f'所有 {skipped_count} 条记录均已存在，已自动跳过',
                'data': {
                    'imported': 0,
                    'skipped': skipped_count,
                    'stats': result['stats'],
                    'errors': result['errors']
                }
            })

        # 导入数据库
        import_result = import_to_database(records, filename)

        if not import_result['success']:
            return jsonify({'code': 500, 'message': f'导入数据库失败: {import_result.get("error", "")}'})

        message = f'成功导入 {import_result["imported"]} 条记录'
        if skipped_count > 0:
            message += f'，跳过 {skipped_count} 条重复记录'

        return jsonify({
            'code': 200,
            'message': message,
            'data': {
                'imported': import_result['imported'],
                'skipped': skipped_count,
                'stats': result['stats'],
                'errors': result['errors']
            }
        })

    except Exception as e:
        return jsonify({'code': 500, 'message': f'处理失败: {str(e)}'})
    finally:
        # 清理临时文件
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass


@import_bp.route('/preview', methods=['POST'])
def preview_excel():
    """预览Excel内容（不导入）"""
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '请选择文件'}), 400

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'code': 400, 'message': '只支持 .xlsx 或 .xls 格式'}), 400

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"preview_{timestamp}_{file.filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        # 从数据库读取有效收费大类和银行账号 v8.3
        valid_categories = get_valid_categories()
        bank_accounts = get_bank_accounts()
        result = parse_excel_file(filepath, valid_categories, bank_accounts)
        return jsonify({
            'code': 200,
            'data': {
                'preview': result['records'],  # 返回全部记录，前端自行分页
                'total': len(result['records']),
                'stats': result['stats'],
                'check_report': result.get('check_report', {}),
                'errors': result['errors']
            }
        })
    except Exception as e:
        return jsonify({'code': 500, 'message': f'预览失败: {str(e)}'})
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass

