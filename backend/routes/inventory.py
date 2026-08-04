"""
库存管理模块 - v8.6
功能：入库登记（手动录入）、供应商管理、入库历史、库存预警
"""
import os
import uuid
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, request, jsonify
import pymysql
from database import get_db_connection

inventory_bp = Blueprint('inventory', __name__)

# v8.6.5: 上传目录在项目根目录（backend 外部），避免替换 backend 文件夹时丢失
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, 'uploads', 'inventory')
SUPPLIER_PHOTO_DIR = os.path.join(PROJECT_ROOT, 'uploads', 'supplier')


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _save_uploaded_file(file, subdir):
    """保存上传的文件，返回存储路径和文件名"""
    try:
        _ensure_dir(subdir)
        ext = os.path.splitext(file.filename)[1] or '.jpg'
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(subdir, filename)
        file.save(filepath)
        return filepath, filename
    except Exception as e:
        raise RuntimeError(f'保存文件失败: {e}')


def _generate_batch_no():
    """生成入库批次号 RK-YYYYMMDD-XXX"""
    today = date.today().strftime('%Y%m%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO inventory_batch_counters (entry_date, counter)
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE counter = counter + 1
        ''', (today,))
        cursor.execute('SELECT counter FROM inventory_batch_counters WHERE entry_date = %s', (today,))
        seq = cursor.fetchone()['counter']
        conn.commit()
        return f'RK-{today}-{seq:03d}'
    except Exception as e:
        conn.rollback()
        # fallback
        return f'RK-{today}-{datetime.now().strftime("%H%M%S")}'
    finally:
        conn.close()


# ========== 1. 供应商管理 ==========

@inventory_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    """获取供应商列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM suppliers WHERE status = "启用" ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


@inventory_bp.route('/suppliers', methods=['POST'])
def add_supplier():
    """添加供应商"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '供应商名称不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO suppliers (name, contact_person, phone, address, business_license_no, remark)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (name, data.get('contact_person'), data.get('phone'),
          data.get('address'), data.get('business_license_no'), data.get('remark')))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'code': 200, 'message': '添加成功', 'data': {'id': new_id}})


@inventory_bp.route('/suppliers/<int:sid>', methods=['PUT'])
def update_supplier(sid):
    """编辑供应商"""
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE suppliers SET name=%s, contact_person=%s, phone=%s,
        address=%s, business_license_no=%s, remark=%s WHERE id=%s
    ''', (data.get('name'), data.get('contact_person'), data.get('phone'),
          data.get('address'), data.get('business_license_no'), data.get('remark'), sid))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


@inventory_bp.route('/suppliers/<int:sid>', methods=['DELETE'])
def delete_supplier(sid):
    """停用供应商"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE suppliers SET status = "停用" WHERE id = %s', (sid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已停用'})


@inventory_bp.route('/suppliers/<int:sid>/photos', methods=['POST'])
def upload_supplier_photo(sid):
    """上传供应商证照"""
    try:
        if 'file' not in request.files:
            return jsonify({'code': 400, 'message': '请选择文件'}), 400
        file = request.files['file']
        photo_type = request.form.get('photo_type', '其他')

        filepath, filename = _save_uploaded_file(file, SUPPLIER_PHOTO_DIR)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO supplier_photos (supplier_id, photo_type, storage_path, file_size)
            VALUES (%s, %s, %s, %s)
        ''', (sid, photo_type, filepath, os.path.getsize(filepath)))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '上传成功', 'data': {'path': filepath}})
    except Exception as e:
        return jsonify({'code': 500, 'message': f'上传失败: {str(e)}'}), 500


@inventory_bp.route('/suppliers/<int:sid>/photos', methods=['GET'])
def get_supplier_photos(sid):
    """查看供应商证照"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM supplier_photos WHERE supplier_id = %s', (sid,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


# ========== 2. 出库单照片上传 ==========

@inventory_bp.route('/upload-photo', methods=['POST'])
def upload_inventory_photo():
    """上传出库单照片"""
    try:
        if 'file' not in request.files:
            return jsonify({'code': 400, 'message': '请选择文件'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'code': 400, 'message': '文件名为空'}), 400

        filepath, filename = _save_uploaded_file(file, UPLOAD_DIR)
        file_size = os.path.getsize(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO inventory_photos (original_name, storage_path, file_size)
            VALUES (%s, %s, %s)
        ''', (file.filename, filepath, file_size))
        photo_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            'code': 200,
            'message': '上传成功',
            'data': {
                'photo_id': photo_id,
                'filename': filename,
                'path': filepath
            }
        })
    except Exception as e:
        return jsonify({'code': 500, 'message': f'上传失败: {str(e)}'}), 500


# ========== 3. 入库登记（核心） ==========

@inventory_bp.route('/', methods=['POST'])
def create_inventory():
    """
    确认入库：保存多行库存记录
    请求: { photo_id, supplier_id, operator, remark, items: [...] }
    """
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'code': 400, 'message': '请至少录入一个商品'}), 400

    # 校验
    for i, item in enumerate(items):
        if not item.get('name'):
            return jsonify({'code': 400, 'message': f'第{i+1}行：名称不能为空'}), 400
        if not item.get('quantity'):
            return jsonify({'code': 400, 'message': f'第{i+1}行：数量不能为空'}), 400
        if not item.get('unit'):
            return jsonify({'code': 400, 'message': f'第{i+1}行：单位不能为空'}), 400
        if not item.get('total_price'):
            return jsonify({'code': 400, 'message': f'第{i+1}行：总价不能为空'}), 400

    batch_no = _generate_batch_no()
    photo_id = data.get('photo_id')
    supplier_id = data.get('supplier_id')
    operator = data.get('operator', '')
    remark = data.get('remark', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        inserted_ids = []
        for item in items:
            qty = Decimal(str(item.get('quantity', 0)))
            unit_price = Decimal(str(item.get('unit_price'))) if item.get('unit_price') else None
            total_price = Decimal(str(item.get('total_price', 0)))
            tax = None
            if unit_price is not None:
                tax = total_price - unit_price
                if tax < 0:
                    tax = Decimal('0')

            cursor.execute('''
                INSERT INTO inventory_records
                (category, name, specification, quantity, unit, production_date,
                 expiry_date, batch_no, manufacturer, manufacturer_license,
                 unit_price, tax_amount, total_price, is_qualified, photo_id,
                 supplier_id, batch_no_rk, operator, remark, current_stock)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                item.get('category', '耗材'), item['name'],
                item.get('specification'), qty, item['unit'],
                item.get('production_date') or None,
                item.get('expiry_date') or None,
                item.get('batch_no'), item.get('manufacturer'),
                item.get('manufacturer_license'),
                unit_price, tax, total_price, '合格', photo_id,
                supplier_id, batch_no, operator, remark, qty
            ))
            inserted_ids.append(cursor.lastrowid)

        conn.commit()
        return jsonify({
            'code': 200,
            'message': f'成功入库 {len(items)} 条商品，批次号：{batch_no}',
            'data': {'batch_no': batch_no, 'ids': inserted_ids}
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'入库失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 4. 入库历史查询 ==========

@inventory_bp.route('/', methods=['GET'])
def get_inventory_list():
    """入库历史查询（分页+搜索）"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    keyword = request.args.get('keyword', '')
    supplier_id = request.args.get('supplier_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    where = ['r.status != "报废"']
    params = []
    if keyword:
        where.append('(r.name LIKE %s OR r.batch_no LIKE %s)')
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    if supplier_id:
        where.append('r.supplier_id = %s')
        params.append(supplier_id)
    if date_from:
        where.append('DATE(r.created_at) >= %s')
        params.append(date_from)
    if date_to:
        where.append('DATE(r.created_at) <= %s')
        params.append(date_to)

    where_sql = ' AND '.join(where)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 总数
    cursor.execute(f'SELECT COUNT(*) as cnt FROM inventory_records r WHERE {where_sql}', params)
    total = cursor.fetchone()['cnt']

    # 数据
    offset = (page - 1) * page_size
    cursor.execute(f'''
        SELECT r.*, s.name as supplier_name, p.storage_path as photo_path
        FROM inventory_records r
        LEFT JOIN suppliers s ON r.supplier_id = s.id
        LEFT JOIN inventory_photos p ON r.photo_id = p.id
        WHERE {where_sql}
        ORDER BY r.created_at DESC
        LIMIT %s OFFSET %s
    ''', params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        'code': 200,
        'data': {
            'items': [dict(r) for r in rows],
            'total': total,
            'page': page,
            'page_size': page_size
        }
    })


# ========== 5. 单条详情（含照片） ==========

@inventory_bp.route('/<int:inv_id>', methods=['GET'])
def get_inventory_detail(inv_id):
    """单条入库详情"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, s.name as supplier_name, p.storage_path as photo_path
        FROM inventory_records r
        LEFT JOIN suppliers s ON r.supplier_id = s.id
        LEFT JOIN inventory_photos p ON r.photo_id = p.id
        WHERE r.id = %s
    ''', (inv_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    return jsonify({'code': 200, 'data': dict(row)})


# ========== 6. 库存预警 ==========

@inventory_bp.route('/warnings', methods=['GET'])
def get_inventory_warnings():
    """库存预警列表"""
    level = request.args.get('level', 'all')
    today = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()

    where = 'r.status = "在库" AND r.expiry_date IS NOT NULL'
    if level == 'expired':
        where += ' AND r.expiry_date < %s'
        params = (today,)
    elif level == 'critical':
        where += ' AND r.expiry_date BETWEEN %s AND %s'
        params = (today, today.strftime('%Y-%m-%d'))  # 30天内
        # 修正：使用DATE_ADD
        cursor.execute(f'''
            SELECT r.*, DATEDIFF(r.expiry_date, %s) as remain_days,
            CASE
                WHEN r.expiry_date < %s THEN 'expired'
                WHEN DATEDIFF(r.expiry_date, %s) <= 30 THEN 'critical'
                WHEN DATEDIFF(r.expiry_date, %s) <= 90 THEN 'warning'
                ELSE 'normal'
            END as warn_level
            FROM inventory_records r
            WHERE r.status = '在库' AND r.expiry_date IS NOT NULL
            HAVING warn_level != 'normal'
            ORDER BY r.expiry_date ASC
        ''', (today, today, today, today))
    else:
        cursor.execute('''
            SELECT r.*, DATEDIFF(r.expiry_date, %s) as remain_days,
            CASE
                WHEN r.expiry_date < %s THEN 'expired'
                WHEN DATEDIFF(r.expiry_date, %s) <= 30 THEN 'critical'
                WHEN DATEDIFF(r.expiry_date, %s) <= 90 THEN 'warning'
                ELSE 'normal'
            END as warn_level
            FROM inventory_records r
            WHERE r.status = '在库' AND r.expiry_date IS NOT NULL
            ORDER BY r.expiry_date ASC
        ''', (today, today, today, today))

    if level == 'all':
        rows = cursor.fetchall()
    else:
        all_rows = cursor.fetchall()
        rows = [r for r in all_rows if r['warn_level'] == level]

    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


# ========== 7. 编辑入库记录 ==========

@inventory_bp.route('/<int:inv_id>', methods=['PUT'])
def update_inventory(inv_id):
    """编辑入库记录"""
    data = request.get_json() or {}

    # 校验必填
    if not data.get('name'):
        return jsonify({'code': 400, 'message': '名称不能为空'}), 400
    if not data.get('quantity'):
        return jsonify({'code': 400, 'message': '数量不能为空'}), 400
    if not data.get('unit'):
        return jsonify({'code': 400, 'message': '单位不能为空'}), 400
    if not data.get('total_price'):
        return jsonify({'code': 400, 'message': '总价不能为空'}), 400

    qty = Decimal(str(data.get('quantity', 0)))
    unit_price = Decimal(str(data.get('unit_price'))) if data.get('unit_price') else None
    total_price = Decimal(str(data.get('total_price', 0)))
    tax = None
    if unit_price is not None:
        tax = total_price - unit_price
        if tax < 0:
            tax = Decimal('0')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE inventory_records SET
                category=%s, name=%s, specification=%s, quantity=%s, unit=%s,
                production_date=%s, expiry_date=%s, batch_no=%s, manufacturer=%s,
                manufacturer_license=%s, unit_price=%s, tax_amount=%s, total_price=%s,
                supplier_id=%s, remark=%s, current_stock=%s
            WHERE id=%s
        ''', (
            data.get('category', '耗材'), data['name'],
            data.get('specification'), qty, data['unit'],
            data.get('production_date') or None,
            data.get('expiry_date') or None,
            data.get('batch_no'), data.get('manufacturer'),
            data.get('manufacturer_license'),
            unit_price, tax, total_price,
            data.get('supplier_id'), data.get('remark', ''), qty, inv_id
        ))
        conn.commit()
        return jsonify({'code': 200, 'message': '更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'更新失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 8. 删除供应商证照 ==========

@inventory_bp.route('/supplier-photos/<int:photo_id>', methods=['DELETE'])
def delete_supplier_photo(photo_id):
    """删除供应商证照"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT storage_path FROM supplier_photos WHERE id = %s', (photo_id,))
        row = cursor.fetchone()
        if row and row['storage_path'] and os.path.exists(row['storage_path']):
            os.remove(row['storage_path'])
        cursor.execute('DELETE FROM supplier_photos WHERE id = %s', (photo_id,))
        conn.commit()
        return jsonify({'code': 200, 'message': '已删除'})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'删除失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 9. 删除入库记录 ==========

@inventory_bp.route('/<int:inv_id>', methods=['DELETE'])
def delete_inventory(inv_id):
    """删除入库记录（软删除：标记为报废）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE inventory_records SET status = "报废" WHERE id = %s', (inv_id,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已删除'})


