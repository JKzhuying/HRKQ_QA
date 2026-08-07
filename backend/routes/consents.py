"""
文件签署中心 - v8.6.8
通用同意书引擎：种植手术/补牙/拔牙/根管治疗/固定义齿修复
"""
import os
import uuid
import random
import json
import traceback
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, request, jsonify, send_file
from database import get_db_connection

consents_bp = Blueprint('consents', __name__)
# v8.6.8: 上传目录在项目根目录（backend 外部），避免替换 backend 文件夹时丢失
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CONSENT_DIR = os.path.join(PROJECT_ROOT, 'uploads', 'consents')


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _to_url_path(abs_path):
    """将服务器绝对路径转为前端可访问的 /uploads/... URL 路径"""
    if not abs_path:
        return None
    # 提取 uploads/ 之后的部分
    idx = abs_path.find('/uploads/')
    if idx >= 0:
        return abs_path[idx:]
    idx = abs_path.find('uploads/')
    if idx >= 0:
        return '/' + abs_path[idx:]
    return abs_path


def _generate_doc_no():
    """生成7位随机数字编号"""
    conn = get_db_connection()
    cursor = conn.cursor()
    for _ in range(100):
        no = ''.join([str(random.randint(0, 9)) for _ in range(7)])
        cursor.execute('SELECT id FROM consent_documents WHERE doc_no = %s', (no,))
        if not cursor.fetchone():
            conn.close()
            return no
    conn.close()
    raise RuntimeError('无法生成唯一编号')


def _save_signature(base64_data, subdir, prefix):
    """保存Base64签名为PNG文件"""
    try:
        import base64
        if not base64_data or ',' not in base64_data:
            return None
        header, data = base64_data.split(',', 1)
        if 'png' not in header.lower():
            return None
        _ensure_dir(subdir)
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(subdir, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(data))
        return filepath
    except Exception as e:
        print(f'[Signature Save Error] {e}')
        return None


def _get_client_ip():
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _parse_json_field(value):
    """安全解析JSON字段（处理PyMySQL自动解析）"""
    if value is None:
        return {}
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


# ========== 模板接口 ==========

@consents_bp.route('/templates/refresh', methods=['POST'])
def refresh_templates():
    """手动刷新模板数据（从代码重新加载条款和字段定义，无需重启服务）"""
    import database as db_module
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        db_module._init_consent_templates(cursor)
        conn.commit()
        # 清除前端缓存用的版本标记
        return jsonify({'code': 200, 'message': '模板数据已刷新'})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': '刷新失败: ' + str(e)})
    finally:
        conn.close()


@consents_bp.route('/templates', methods=['GET'])
def get_templates():
    """获取所有同意书模板"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT doc_type, title, field_schema FROM consent_templates ORDER BY id')
    rows = cursor.fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        d['field_schema'] = _parse_json_field(d.get('field_schema'))
        items.append(d)
    return jsonify({'code': 200, 'data': items})


@consents_bp.route('/templates/<doc_type>', methods=['GET'])
def get_template_detail(doc_type):
    """获取指定类型的模板详情"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM consent_templates WHERE doc_type = %s', (doc_type,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '模板不存在'}), 404
    data = dict(row)
    data['clauses'] = _parse_json_field(data.get('clauses'))
    data['field_schema'] = _parse_json_field(data.get('field_schema'))
    return jsonify({'code': 200, 'data': data})


# ========== 列表查询 ==========

@consents_bp.route('/', methods=['GET'])
def get_consents():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    keyword = request.args.get('keyword', '')
    doc_type = request.args.get('doc_type', '')
    status = request.args.get('status', '')

    where = ['status != "已作废"']
    params = []
    if keyword:
        where.append('(patient_name LIKE %s OR doc_no LIKE %s)')
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    if doc_type:
        where.append('doc_type = %s')
        params.append(doc_type)
    if status:
        where.append('status = %s')
        params.append(status)

    where_sql = ' AND '.join(where)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT COUNT(*) as cnt FROM consent_documents WHERE {where_sql}', params)
    total = cursor.fetchone()['cnt']

    offset = (page - 1) * page_size
    cursor.execute(f'''
        SELECT id, doc_no, doc_type, patient_name, patient_gender, patient_age,
               tooth_positions, extra_fields, pdf_path, status,
               patient_signature_path, guardian_signature_path, doctor_signature_path,
               created_at
        FROM consent_documents
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    ''', params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        d['tooth_positions'] = _parse_json_field(d.get('tooth_positions'))
        d['extra_fields'] = _parse_json_field(d.get('extra_fields'))
        items.append(d)

    return jsonify({'code': 200, 'data': {'items': items, 'total': total, 'page': page, 'page_size': page_size}})


# ========== 新建 ==========

@consents_bp.route('/', methods=['POST'])
def create_consent():
    """新建同意书"""
    data = request.get_json() or {}
    name = (data.get('patient_name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '患者姓名不能为空'}), 400
    if not data.get('patient_gender'):
        return jsonify({'code': 400, 'message': '性别不能为空'}), 400
    if not data.get('doc_type'):
        return jsonify({'code': 400, 'message': '同意书类型不能为空'}), 400

    doc_no = _generate_doc_no()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO consent_documents
            (doc_no, doc_type, patient_name, patient_gender, patient_age,
             patient_id, allergy_history, tooth_positions, extra_fields, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '草稿')
        ''', (
            doc_no, data['doc_type'], name, data['patient_gender'],
            data.get('patient_age') or None,
            data.get('patient_id') or None,
            data.get('allergy_history') or None,
            json.dumps(data.get('tooth_positions', [])),
            json.dumps(data.get('extra_fields', {})),
        ))
        conn.commit()
        new_id = cursor.lastrowid
        return jsonify({'code': 200, 'message': '新建成功', 'data': {'id': new_id, 'doc_no': doc_no}})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'新建失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 详情 ==========

@consents_bp.route('/<int:cid>', methods=['GET'])
def get_consent(cid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    data = dict(row)
    data['tooth_positions'] = _parse_json_field(data.get('tooth_positions'))
    data['extra_fields'] = _parse_json_field(data.get('extra_fields'))
    data['barcode_image_path'] = _to_url_path(data.get('barcode_image_path'))
    data['patient_signature_path'] = _to_url_path(data.get('patient_signature_path'))
    data['guardian_signature_path'] = _to_url_path(data.get('guardian_signature_path'))
    data['doctor_signature_path'] = _to_url_path(data.get('doctor_signature_path'))
    return jsonify({'code': 200, 'data': data})


# ========== 更新基本信息 ==========

@consents_bp.route('/<int:cid>', methods=['PUT'])
def update_consent(cid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE consent_documents SET
                patient_name=%s, patient_gender=%s, patient_age=%s,
                patient_id=%s, allergy_history=%s, tooth_positions=%s, extra_fields=%s
            WHERE id=%s
        ''', (
            data.get('patient_name'), data.get('patient_gender'),
            data.get('patient_age'), data.get('patient_id'),
            data.get('allergy_history'),
            json.dumps(data.get('tooth_positions', [])),
            json.dumps(data.get('extra_fields', {})),
            cid
        ))
        conn.commit()
        return jsonify({'code': 200, 'message': '更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'更新失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 手写内容签名（用于补牙诊断/根管主诉PE/患者陈述/医生陈述/拔牙建议） ==========

@consents_bp.route('/<int:cid>/handwrite', methods=['POST'])
def save_handwrite(cid):
    """保存手写内容
    body: { field_name: 'treatment_plan', signature: 'base64...' }
    """
    data = request.get_json() or {}
    field_name = data.get('field_name')
    signature_b64 = data.get('signature')
    if not field_name or not signature_b64:
        return jsonify({'code': 400, 'message': '字段名和签名数据不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT doc_no, status FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    if row['status'] == '已作废':
        conn.close()
        return jsonify({'code': 400, 'message': '该同意书已作废'}), 400

    doc_no = row['doc_no']
    subdir = os.path.join(CONSENT_DIR, doc_no)
    filepath = _save_signature(signature_b64, subdir, f'hw_{field_name}')

    if filepath:
        # 保存手写文件路径到extra_fields
        cursor.execute('SELECT extra_fields FROM consent_documents WHERE id = %s', (cid,))
        ef_row = cursor.fetchone()
        ef = _parse_json_field(ef_row.get('extra_fields'))
        ef[f'{field_name}_path'] = filepath
        cursor.execute('UPDATE consent_documents SET extra_fields = %s WHERE id = %s',
                       (json.dumps(ef), cid))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '手写内容保存成功', 'data': {'path': filepath}})
    conn.close()
    return jsonify({'code': 500, 'message': '保存失败'}), 500


# ========== 电子签名 ==========

@consents_bp.route('/<int:cid>/sign', methods=['POST'])
def submit_signature(cid):
    data = request.get_json() or {}
    sign_type = data.get('sign_type')
    signature_b64 = data.get('signature')
    if not sign_type or not signature_b64:
        return jsonify({'code': 400, 'message': '签名类型和签名数据不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status, doc_no FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    if row['status'] == '已作废':
        conn.close()
        return jsonify({'code': 400, 'message': '该同意书已作废'}), 400

    doc_no = row['doc_no']
    subdir = os.path.join(CONSENT_DIR, doc_no)
    _ensure_dir(subdir)
    ip = _get_client_ip()
    today = date.today()

    try:
        if sign_type == 'patient':
            filepath = _save_signature(signature_b64, subdir, 'patient')
            cursor.execute('''UPDATE consent_documents SET patient_signature_path=%s, patient_sign_date=%s, patient_sign_ip=%s WHERE id=%s''',
                           (filepath, today, ip, cid))
        elif sign_type == 'guardian':
            filepath = _save_signature(signature_b64, subdir, 'guardian')
            relation = data.get('guardian_relation', '')
            cursor.execute('''UPDATE consent_documents SET guardian_signature_path=%s, guardian_relation=%s, guardian_sign_date=%s, guardian_sign_ip=%s WHERE id=%s''',
                           (filepath, relation, today, ip, cid))
        elif sign_type == 'doctor':
            filepath = _save_signature(signature_b64, subdir, 'doctor')
            cursor.execute('''UPDATE consent_documents SET doctor_signature_path=%s, doctor_sign_date=%s, doctor_sign_ip=%s WHERE id=%s''',
                           (filepath, today, ip, cid))
            # v8.6.8: 患者或家属有1个签名 + 医生签名 = 已完成
            cursor.execute('''UPDATE consent_documents SET status='已完成'
                WHERE id=%s AND doctor_signature_path IS NOT NULL
                AND (patient_signature_path IS NOT NULL OR guardian_signature_path IS NOT NULL)''', (cid,))
        else:
            conn.close()
            return jsonify({'code': 400, 'message': '签名类型错误'}), 400
        conn.commit()
        return jsonify({'code': 200, 'message': '签名保存成功'})
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'code': 500, 'message': f'签名保存失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 种植体标签照片上传 ==========

@consents_bp.route('/<int:cid>/barcode', methods=['POST'])
def upload_barcode_image(cid):
    """v8.6.8: 上传种植体标签照片（仅种植手术同意书）"""
    if 'image' not in request.files:
        return jsonify({'code': 400, 'message': '请选择图片文件'}), 400

    file = request.files['image']
    if not file or file.filename == '':
        return jsonify({'code': 400, 'message': '未选择文件'}), 400

    # 验证文件类型
    allowed_ext = {'.jpg', '.jpeg', '.png'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'code': 400, 'message': '仅支持 JPG/PNG 格式'}), 400

    # 验证文件大小（10MB）
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 10 * 1024 * 1024:
        return jsonify({'code': 400, 'message': '图片大小不能超过10MB'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT doc_type, doc_no, barcode_image_path FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    if row['doc_type'] != '种植手术':
        conn.close()
        return jsonify({'code': 400, 'message': '仅种植手术同意书支持上传标签照片'}), 400

    doc_no = row['doc_no']
    subdir = os.path.join(CONSENT_DIR, doc_no)
    _ensure_dir(subdir)

    # 删除旧图片
    old_path = row.get('barcode_image_path')
    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except Exception:
            pass

    # 保存新图片
    filename = f'barcode_{uuid.uuid4().hex[:8]}{ext}'
    filepath = os.path.join(subdir, filename)
    file.save(filepath)

    # 更新数据库
    cursor.execute('UPDATE consent_documents SET barcode_image_path = %s WHERE id = %s',
                   (filepath, cid))
    conn.commit()
    conn.close()

    return jsonify({'code': 200, 'message': '上传成功', 'data': {'barcode_image_path': _to_url_path(filepath)}})


# ========== 删除（作废） ==========

@consents_bp.route('/<int:cid>', methods=['DELETE'])
def delete_consent(cid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE consent_documents SET status = "已作废" WHERE id = %s', (cid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已作废'})


# ========== 完成归档 ==========

@consents_bp.route('/<int:cid>/complete', methods=['POST'])
def complete_consent(cid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    data = dict(row)
    has_patient_or_guardian = data.get('patient_signature_path') or data.get('guardian_signature_path')
    has_doctor = data.get('doctor_signature_path')
    if not has_patient_or_guardian:
        return jsonify({'code': 400, 'message': '患者或亲属签名未完成'}), 400
    if not has_doctor:
        return jsonify({'code': 400, 'message': '主治医生签名未完成'}), 400

    data['tooth_positions'] = _parse_json_field(data.get('tooth_positions'))
    data['extra_fields'] = _parse_json_field(data.get('extra_fields'))
    # 获取模板
    t_conn = get_db_connection()
    t_cursor = t_conn.cursor()
    t_cursor.execute('SELECT clauses FROM consent_templates WHERE doc_type = %s', (data['doc_type'],))
    t_row = t_cursor.fetchone()
    t_conn.close()
    data['clauses'] = _parse_json_field(t_row.get('clauses')) if t_row else []

    try:
        pdf_path = _create_consent_pdf(data)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE consent_documents SET status = %s, pdf_path = %s WHERE id = %s',
                       ('已完成', pdf_path, cid))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '归档成功', 'data': {'pdf_path': pdf_path}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'code': 500, 'message': f'归档失败: {str(e)}'}), 500


# ========== PDF下载 ==========

@consents_bp.route('/<int:cid>/pdf', methods=['GET'])
def download_pdf(cid):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT pdf_path FROM consent_documents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row['pdf_path']:
        return jsonify({'code': 404, 'message': 'PDF不存在'}), 404
    if os.path.exists(row['pdf_path']):
        return send_file(row['pdf_path'], as_attachment=True)
    return jsonify({'code': 404, 'message': 'PDF文件不存在'}), 404


# ========== PDF生成 ==========

def _find_cjk_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [
        ('CJKFont', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
        ('CJKFont', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'),
        ('CJKFont', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        ('CJKFont', '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'),
        ('CJKFont', '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'),
        ('CJKFont', '/usr/share/fonts/truetype/arphic/uming.ttc'),
        ('CJKFont', '/usr/share/fonts/truetype/arphic/ukai.ttc'),
    ]
    for name, path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return 'STSong-Light'
    except Exception:
        raise RuntimeError('系统中未找到中文字体，请执行: apt-get install -y fonts-wqy-zenhei')


def _tooth_names(positions):
    names = {
        11:'右上1',12:'右上2',13:'右上3',14:'右上4',15:'右上5',16:'右上6',17:'右上7',18:'右上8',
        21:'左上1',22:'左上2',23:'左上3',24:'左上4',25:'左上5',26:'左上6',27:'左上7',28:'左上8',
        31:'左下1',32:'左下2',33:'左下3',34:'左下4',35:'左下5',36:'左下6',37:'左下7',38:'左下8',
        41:'右下1',42:'右下2',43:'右下3',44:'右下4',45:'右下5',46:'右下6',47:'右下7',48:'右下8',
    }
    return '、'.join([names.get(p, str(p)) for p in positions])


def _fmt_date(d):
    if not d:
        return '____年____月____日'
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return d.strftime('%Y年%m月%d日')


def _get_sign_image(path, w, h, font_name='Helvetica'):
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    if path and os.path.exists(path):
        return RLImage(path, width=w, height=h)
    return Paragraph('________________', ParagraphStyle('ph', fontName=font_name, fontSize=10))


def _create_consent_pdf(data):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    doc_no = data['doc_no']
    subdir = os.path.join(CONSENT_DIR, doc_no)
    _ensure_dir(subdir)
    pdf_path = os.path.join(subdir, f'{doc_no}.pdf')

    cjk = _find_cjk_font()

    title_s = ParagraphStyle('T', fontName=cjk, fontSize=20, alignment=TA_CENTER, spaceAfter=6*mm)
    label_s = ParagraphStyle('L', fontName=cjk, fontSize=10, alignment=TA_LEFT)
    body_s = ParagraphStyle('B', fontName=cjk, fontSize=10, alignment=TA_JUSTIFY, leading=16, firstLineIndent=20)
    small_s = ParagraphStyle('S', fontName=cjk, fontSize=9, alignment=TA_LEFT, textColor=colors.grey)
    sign_s = ParagraphStyle('SG', fontName=cjk, fontSize=10, alignment=TA_LEFT)

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    elements = []

    # 标题
    title_map = {'种植手术':'种植手术知情同意书', '补牙':'补牙知情同意书', '拔牙':'拔牙知情同意书', '根管治疗':'根管治疗知情同意书', '固定义齿修复':'固定义齿修复知情同意书'}
    elements.append(Paragraph(title_map.get(data['doc_type'], '知情同意书'), title_s))
    elements.append(Spacer(1, 2*mm))

    # 编号和日期
    today_str = date.today().strftime('%Y年%m月%d日')
    elements.append(Paragraph(f'<para alignment="right">编号：{doc_no}&nbsp;&nbsp;&nbsp;&nbsp;日期：{today_str}</para>', label_s))
    elements.append(Spacer(1, 4*mm))

    # 患者信息
    info_rows = [[
        Paragraph(f'姓名：{data.get("patient_name","")}', label_s),
        Paragraph(f'性别：{data.get("patient_gender","")}', label_s),
        Paragraph(f'年龄：{data.get("patient_age","")}', label_s),
        Paragraph(f'NO. {doc_no}', label_s)
    ]]
    info_t = Table(info_rows, colWidths=[45*mm,30*mm,30*mm,45*mm])
    info_t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),8)]))
    elements.append(info_t)
    elements.append(Spacer(1, 4*mm))

    # 病历号/诊断/过敏史
    extra = data.get('extra_fields', {})
    meta_lines = []
    if data.get('patient_id'):
        meta_lines.append(f'病历号：{data["patient_id"]}')
    if extra.get('diagnosis'):
        meta_lines.append(f'诊断：{extra["diagnosis"]}')
    if data.get('allergy_history'):
        meta_lines.append(f'过敏史：{data["allergy_history"]}')
    if meta_lines:
        elements.append(Paragraph(' | '.join(meta_lines), label_s))
        elements.append(Spacer(1, 3*mm))

    # 条款（带变量替换）
    clauses = data.get('clauses', [])
    tp = data.get('tooth_positions', [])
    tp_str = _tooth_names(tp) if tp else ''

    # 构建变量替换字典
    repl = {
        'patient_name': data.get('patient_name', ''),
        'patient_gender': data.get('patient_gender', ''),
        'patient_age': str(data.get('patient_age', '')),
        'patient_id': data.get('doc_no', ''),
        'tooth_positions': tp_str,
        'implant_brand': extra.get('implant_brand', ''),
        'implant_model': extra.get('implant_model', ''),
        'implant_count': str(extra.get('implant_count', '')),
        'diagnosis': extra.get('diagnosis', ''),
        'treatment_plan': '(手写内容见下方)',
        'allergy_history': data.get('allergy_history', ''),
        'chief_complaint': '(手写内容见下方)',
        'pe': '(手写内容见下方)',
        'imp': extra.get('imp', ''),
        'patient_statement': '(手写内容见下方)',
        'doctor_statement': '(手写内容见下方)',
        'doctor_name': extra.get('doctor_name', ''),
    }
    # 拔牙病史是 yesno 类型
    for i in range(1, 8):
        key = f'has_history_{i}'
        val = extra.get(key, '')
        repl[key] = '有' if val == 'yes' else ('无' if val == 'no' else '')
    repl['patient_decline_1'] = extra.get('patient_decline_1', '')
    repl['patient_decline_2'] = extra.get('patient_decline_2', '')
    repl['custom_note'] = extra.get('custom_note', '')

    for clause in clauses:
        try:
            text = clause.format(**repl)
        except Exception:
            text = clause
        # 检测是否为手写区域标记
        if text.startswith('【') and '（手写）' in text:
            # 手写区域：显示标签+图片
            field_key = None
            for key in ['treatment_plan', 'chief_complaint', 'pe', 'patient_statement', 'doctor_statement']:
                if key in clause:
                    field_key = key
                    break
            if field_key:
                hw_path = extra.get(f'{field_key}_path')
                elements.append(Paragraph(text.replace('【', '').replace('】', ''), label_s))
                if hw_path and os.path.exists(hw_path):
                    fname = hw_path.split('/').pop()
                    elements.append(_get_sign_image(hw_path, 60*mm, 20*mm, cjk))
                else:
                    elements.append(Paragraph('________________（未手写）', sign_s))
                elements.append(Spacer(1, 2*mm))
            else:
                elements.append(Paragraph(text, body_s))
                elements.append(Spacer(1, 2*mm))
        elif '【' in text and '】' in text:
            # 带变量的高亮显示
            text = text.replace('【', '<u>').replace('】', '</u>')
            elements.append(Paragraph(text, body_s))
            elements.append(Spacer(1, 2*mm))
        else:
            elements.append(Paragraph(text, body_s))
            elements.append(Spacer(1, 2*mm))

    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph('以上知情同意书，患者已知情同意并签字。', body_s))
    elements.append(Spacer(1, 4*mm))

    # 签名区域
    sign_data = []
    p_date = _fmt_date(data.get('patient_sign_date'))
    p_sign = _get_sign_image(data.get('patient_signature_path'), 40*mm, 15*mm, cjk)
    sign_data.append([Paragraph('患者签名：', sign_s), p_sign, Paragraph(f'日期：{p_date}', sign_s)])

    g_date = _fmt_date(data.get('guardian_sign_date'))
    g_relation = data.get('guardian_relation', '')
    g_sign = _get_sign_image(data.get('guardian_signature_path'), 40*mm, 15*mm, cjk)
    sign_data.append([Paragraph('法定代理人/亲属签名：', sign_s), g_sign, Paragraph(f'与患者关系：{g_relation}&nbsp;&nbsp;&nbsp;&nbsp;日期：{g_date}', sign_s)])

    d_date = _fmt_date(data.get('doctor_sign_date'))
    d_sign = _get_sign_image(data.get('doctor_signature_path'), 40*mm, 15*mm, cjk)
    sign_data.append([Paragraph('主治医生签名：', sign_s), d_sign, Paragraph(f'日期：{d_date}', sign_s)])

    sign_t = Table(sign_data, colWidths=[45*mm,50*mm,55*mm])
    sign_t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    elements.append(sign_t)

    # v8.6.8: 种植体标签照片
    barcode_path = data.get('barcode_image_path')
    if barcode_path and os.path.exists(barcode_path):
        from reportlab.platypus import Image as RLImage
        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph('种植体标签：', label_s))
        elements.append(Spacer(1, 2*mm))
        # A4可用宽度170mm，等比缩放
        img_w = 170 * mm
        # 读取图片原始尺寸计算高度
        try:
            from PIL import Image as PILImage
            with PILImage.open(barcode_path) as img:
                orig_w, orig_h = img.size
                img_h = img_w * (orig_h / orig_w)
                # 最大高度限制60mm
                if img_h > 60 * mm:
                    img_h = 60 * mm
                    img_w = img_h * (orig_w / orig_h)
        except Exception:
            img_h = 40 * mm
        elements.append(RLImage(barcode_path, width=img_w, height=img_h))

    # 审计
    elements.append(Spacer(1, 8*mm))
    audit = []
    if data.get('patient_sign_ip'): audit.append(f'患者签名IP: {data["patient_sign_ip"]}')
    if data.get('guardian_sign_ip'): audit.append(f'亲属签名IP: {data["guardian_sign_ip"]}')
    if data.get('doctor_sign_ip'): audit.append(f'医生签名IP: {data["doctor_sign_ip"]}')
    if audit:
        elements.append(Paragraph(' | '.join(audit), small_s))

    doc.build(elements)
    return pdf_path
