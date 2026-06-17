from flask import Blueprint, request, jsonify
from database import get_db_connection
import pymysql

subjects_bp = Blueprint('subjects', __name__)


@subjects_bp.route('/l1', methods=['GET'])
def get_l1():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM account_subjects_l1 ORDER BY code')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


@subjects_bp.route('/l2', methods=['GET'])
def get_l2():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l2.*, l1.name as parent_name, l1.code as parent_code
        FROM account_subjects_l2 l2
        JOIN account_subjects_l1 l1 ON l2.parent_id = l1.id
        WHERE l2.is_active = 1
        ORDER BY l2.code
    ''')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


@subjects_bp.route('/l2', methods=['POST'])
def add_l2():
    data = request.get_json()
    name = data.get('name', '').strip()
    parent_id = data.get('parent_id')
    if not name or not parent_id:
        return jsonify({'code': 400, 'message': '名称和上级科目不能为空'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code FROM account_subjects_l1 WHERE id=%s', (parent_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '上级科目不存在'}), 404
    p_code = row['code']
    cursor.execute('SELECT COUNT(*) as cnt FROM account_subjects_l2 WHERE parent_id=%s', (parent_id,))
    seq = cursor.fetchone()['cnt'] + 1
    code = f"{p_code}.{seq:02d}"
    try:
        cursor.execute('INSERT INTO account_subjects_l2 (parent_id, code, name) VALUES (%s, %s, %s)', (parent_id, code, name))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '添加成功'})
    except pymysql.IntegrityError:
        conn.close()
        return jsonify({'code': 400, 'message': '科目编码冲突'}), 400


@subjects_bp.route('/l2/<int:sid>', methods=['PUT'])
def update_l2(sid):
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '名称不能为空'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE account_subjects_l2 SET name=%s WHERE id=%s', (name, sid))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


@subjects_bp.route('/l2/<int:sid>', methods=['DELETE'])
def delete_l2(sid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE account_subjects_l2 SET is_active=0 WHERE id=%s', (sid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已禁用'})


# ========== 科目映射 ==========

@subjects_bp.route('/mapping', methods=['GET'])
def get_mapping():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, c.id as category_id, c.name as category_name, c.trans_type,
               s.id as subject_id, s.code as subject_code, s.name as subject_name
        FROM category_subject_map m
        JOIN category_records c ON m.category_id = c.id
        JOIN account_subjects_l2 s ON m.subject_l2_id = s.id
        ORDER BY c.trans_type, c.name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'code': 200, 'data': [dict(r) for r in rows]})


@subjects_bp.route('/mapping', methods=['POST'])
def add_mapping():
    data = request.get_json()
    cat_id = data.get('category_id')
    sub_id = data.get('subject_l2_id')
    if not cat_id or not sub_id:
        return jsonify({'code': 400, 'message': '参数不完整'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO category_subject_map (category_id, subject_l2_id) VALUES (%s, %s)', (cat_id, sub_id))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '映射成功'})
    except pymysql.IntegrityError:
        conn.close()
        return jsonify({'code': 400, 'message': '该收费大类已存在映射'}), 400


@subjects_bp.route('/mapping/<int:mid>', methods=['PUT'])
def update_mapping(mid):
    data = request.get_json()
    sub_id = data.get('subject_l2_id')
    if not sub_id:
        return jsonify({'code': 400, 'message': '科目不能为空'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE category_subject_map SET subject_l2_id=%s WHERE id=%s', (sub_id, mid))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '更新成功'})


@subjects_bp.route('/mapping/<int:mid>', methods=['DELETE'])
def delete_mapping(mid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM category_subject_map WHERE id=%s', (mid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '删除成功'})
