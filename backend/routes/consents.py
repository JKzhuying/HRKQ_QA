"""
知情同意书模块 - v8.5.5
功能：种植手术知情同意书的新建、编辑、电子签名、PDF生成
"""
import os
import uuid
import random
import json
import traceback
from datetime import datetime, date
from flask import Blueprint, request, jsonify, send_file
from database import get_db_connection

consents_bp = Blueprint('consents', __name__)

# 上传目录
CONSENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'consents')


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _generate_consent_no():
    """生成7位随机数字编号"""
    conn = get_db_connection()
    cursor = conn.cursor()
    for _ in range(100):
        no = ''.join([str(random.randint(0, 9)) for _ in range(7)])
        cursor.execute('SELECT id FROM informed_consents WHERE consent_no = %s', (no,))
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
    """获取客户端IP"""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    return request.remote_addr or 'unknown'


# ========== 1. 列表查询 ==========

@consents_bp.route('/', methods=['GET'])
def get_consents():
    """知情同意书列表查询"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')

    where = ['status != "已作废"']
    params = []
    if keyword:
        where.append('(patient_name LIKE %s OR consent_no LIKE %s)')
        params.extend([f'%{keyword}%', f'%{keyword}%'])
    if status:
        where.append('status = %s')
        params.append(status)

    where_sql = ' AND '.join(where)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(f'SELECT COUNT(*) as cnt FROM informed_consents WHERE {where_sql}', params)
    total = cursor.fetchone()['cnt']

    offset = (page - 1) * page_size
    cursor.execute(f'''
        SELECT id, consent_no, patient_name, patient_gender, patient_age,
               tooth_positions, implant_brand, status,
               patient_signature_path, guardian_signature_path, doctor_signature_path,
               pdf_path, created_at
        FROM informed_consents
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    ''', params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        # v8.5.5-fix1: PyMySQL JSON类型可能已自动解析为Python对象
        tp = d['tooth_positions']
        if isinstance(tp, str):
            d['tooth_positions'] = json.loads(tp) if tp else []
        elif tp is None:
            d['tooth_positions'] = []
        items.append(d)

    return jsonify({
        'code': 200,
        'data': {'items': items, 'total': total, 'page': page, 'page_size': page_size}
    })


# ========== 2. 新建 ==========

@consents_bp.route('/', methods=['POST'])
def create_consent():
    """新建知情同意书"""
    data = request.get_json() or {}
    name = (data.get('patient_name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '患者姓名不能为空'}), 400
    if not data.get('patient_gender'):
        return jsonify({'code': 400, 'message': '性别不能为空'}), 400

    consent_no = _generate_consent_no()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO informed_consents
            (consent_no, patient_name, patient_gender, patient_age,
             implant_brand, implant_model, tooth_positions, implant_count,
             created_by, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '草稿')
        ''', (
            consent_no, name, data['patient_gender'],
            data.get('patient_age') or None,
            data.get('implant_brand'), data.get('implant_model'),
            json.dumps(data.get('tooth_positions', [])),
            data.get('implant_count', 1),
            data.get('operator', '')
        ))
        conn.commit()
        new_id = cursor.lastrowid
        return jsonify({'code': 200, 'message': '新建成功', 'data': {'id': new_id, 'consent_no': consent_no}})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'新建失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 3. 详情 ==========

@consents_bp.route('/<int:cid>', methods=['GET'])
def get_consent(cid):
    """获取知情同意书详情"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM informed_consents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    data = dict(row)
    # v8.5.5-fix1: PyMySQL JSON类型可能已自动解析为Python对象
    tp = data['tooth_positions']
    if isinstance(tp, str):
        data['tooth_positions'] = json.loads(tp) if tp else []
    elif tp is None:
        data['tooth_positions'] = []
    return jsonify({'code': 200, 'data': data})


# ========== 4. 更新基本信息 ==========

@consents_bp.route('/<int:cid>', methods=['PUT'])
def update_consent(cid):
    """更新知情同意书基本信息"""
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE informed_consents SET
                patient_name=%s, patient_gender=%s, patient_age=%s,
                implant_brand=%s, implant_model=%s, tooth_positions=%s, implant_count=%s
            WHERE id=%s
        ''', (
            data.get('patient_name'), data.get('patient_gender'),
            data.get('patient_age'), data.get('implant_brand'),
            data.get('implant_model'),
            json.dumps(data.get('tooth_positions', [])),
            data.get('implant_count', 1), cid
        ))
        conn.commit()
        return jsonify({'code': 200, 'message': '更新成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'code': 500, 'message': f'更新失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 5. 提交签名 ==========

@consents_bp.route('/<int:cid>/sign', methods=['POST'])
def submit_signature(cid):
    """提交电子签名
    body: { sign_type: 'patient'|'guardian'|'doctor', signature: 'base64...', guardian_relation? }
    """
    data = request.get_json() or {}
    sign_type = data.get('sign_type')
    signature_b64 = data.get('signature')
    if not sign_type or not signature_b64:
        return jsonify({'code': 400, 'message': '签名类型和签名数据不能为空'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status, consent_no FROM informed_consents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    if row['status'] == '已作废':
        conn.close()
        return jsonify({'code': 400, 'message': '该同意书已作废'}), 400

    consent_no = row['consent_no']
    subdir = os.path.join(CONSENT_DIR, consent_no)
    _ensure_dir(subdir)

    ip = _get_client_ip()
    today = date.today()

    try:
        if sign_type == 'patient':
            filepath = _save_signature(signature_b64, subdir, 'patient')
            cursor.execute('''
                UPDATE informed_consents SET
                    patient_signature_path=%s, patient_sign_date=%s, patient_sign_ip=%s
                WHERE id=%s
            ''', (filepath, today, ip, cid))
        elif sign_type == 'guardian':
            filepath = _save_signature(signature_b64, subdir, 'guardian')
            relation = data.get('guardian_relation', '')
            cursor.execute('''
                UPDATE informed_consents SET
                    guardian_signature_path=%s, guardian_relation=%s,
                    guardian_sign_date=%s, guardian_sign_ip=%s
                WHERE id=%s
            ''', (filepath, relation, today, ip, cid))
        elif sign_type == 'doctor':
            filepath = _save_signature(signature_b64, subdir, 'doctor')
            cursor.execute('''
                UPDATE informed_consents SET
                    doctor_signature_path=%s, doctor_sign_date=%s, doctor_sign_ip=%s
                WHERE id=%s
            ''', (filepath, today, ip, cid))
            # v8.5.5-fix2: 患者或家属有1个签名 + 医生签名 = 已完成
            cursor.execute('''
                UPDATE informed_consents SET status='已完成'
                WHERE id=%s AND doctor_signature_path IS NOT NULL
                AND (patient_signature_path IS NOT NULL OR guardian_signature_path IS NOT NULL)
            ''', (cid,))
        else:
            conn.close()
            return jsonify({'code': 400, 'message': '签名类型错误'}), 400

        conn.commit()
        return jsonify({'code': 200, 'message': '签名保存成功', 'data': {'path': filepath}})
    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({'code': 500, 'message': f'签名保存失败: {str(e)}'}), 500
    finally:
        conn.close()


# ========== 6. 完成归档 ==========

@consents_bp.route('/<int:cid>/complete', methods=['POST'])
def complete_consent(cid):
    """完成归档：检查签名条件，标记为已完成并生成PDF"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM informed_consents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    data = dict(row)
    # v8.5.5-fix5: 检查签名条件（患者或家属签了 + 医生签了）
    has_patient_or_guardian = data.get('patient_signature_path') or data.get('guardian_signature_path')
    has_doctor = data.get('doctor_signature_path')
    if not has_patient_or_guardian:
        return jsonify({'code': 400, 'message': '患者或亲属签名未完成'}), 400
    if not has_doctor:
        return jsonify({'code': 400, 'message': '主治医生签名未完成'}), 400

    # 解析牙位
    tp = data['tooth_positions']
    if isinstance(tp, str):
        data['tooth_positions'] = json.loads(tp) if tp else []
    elif tp is None:
        data['tooth_positions'] = []

    try:
        # 生成PDF
        pdf_path = _create_consent_pdf(data)
        # 更新状态
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE informed_consents SET status = %s, pdf_path = %s WHERE id = %s',
                       ('已完成', pdf_path, cid))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': '归档成功', 'data': {'pdf_path': pdf_path}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'code': 500, 'message': f'归档失败: {str(e)}'}), 500


# ========== 7. 删除（作废） ==========

@consents_bp.route('/<int:cid>', methods=['DELETE'])
def delete_consent(cid):
    """作废知情同意书"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE informed_consents SET status = "已作废" WHERE id = %s', (cid,))
    conn.commit()
    conn.close()
    return jsonify({'code': 200, 'message': '已作废'})


# ========== 7. PDF生成 ==========

@consents_bp.route('/<int:cid>/pdf', methods=['POST'])
def generate_pdf(cid):
    """生成PDF文件"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM informed_consents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    data = dict(row)
    data['tooth_positions'] = json.loads(data['tooth_positions']) if data['tooth_positions'] else []

    try:
        pdf_path = _create_consent_pdf(data)
        # 更新数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE informed_consents SET pdf_path = %s WHERE id = %s', (pdf_path, cid))
        conn.commit()
        conn.close()
        return jsonify({'code': 200, 'message': 'PDF生成成功', 'data': {'path': pdf_path}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'code': 500, 'message': f'PDF生成失败: {str(e)}'}), 500


@consents_bp.route('/<int:cid>/pdf', methods=['GET'])
def download_pdf(cid):
    """下载PDF文件"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT pdf_path FROM informed_consents WHERE id = %s', (cid,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row['pdf_path']:
        return jsonify({'code': 404, 'message': 'PDF不存在'}), 404
    if os.path.exists(row['pdf_path']):
        return send_file(row['pdf_path'], as_attachment=True)
    return jsonify({'code': 404, 'message': 'PDF文件不存在'}), 404


def _find_cjk_font():
    """查找系统中可用的中日韩字体，返回 (字体名, 字体路径)"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 尝试的字体列表：(注册名, 文件路径)
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
    return None


def _create_consent_pdf(data):
    """使用reportlab生成知情同意书PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    consent_no = data['consent_no']
    subdir = os.path.join(CONSENT_DIR, consent_no)
    _ensure_dir(subdir)
    pdf_path = os.path.join(subdir, f'{consent_no}.pdf')

    # v8.5.5-fix4: 改进字体查找
    cjk_font = _find_cjk_font()
    if cjk_font is None:
        # 使用reportlab内置CID字体作为后备
        try:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            cjk_font = 'STSong-Light'
        except Exception:
            raise RuntimeError('系统中未找到中文字体，请执行: apt-get install -y fonts-wqy-zenhei')

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                           leftMargin=20*mm, rightMargin=20*mm,
                           topMargin=20*mm, bottomMargin=20*mm)

    elements = []

    # 自定义样式（使用找到的CJK字体）
    title_style = ParagraphStyle('Title', fontName=cjk_font, fontSize=22, alignment=TA_CENTER, spaceAfter=6*mm)
    label_style = ParagraphStyle('Label', fontName=cjk_font, fontSize=10, alignment=TA_LEFT)
    body_style = ParagraphStyle('Body', fontName=cjk_font, fontSize=10, alignment=TA_JUSTIFY, leading=16, firstLineIndent=20)
    small_style = ParagraphStyle('Small', fontName=cjk_font, fontSize=9, alignment=TA_LEFT, textColor=colors.grey)

    # 标题
    elements.append(Paragraph('种植手术知情同意书', title_style))
    elements.append(Spacer(1, 2*mm))

    # 编号和日期（右对齐）
    today_str = date.today().strftime('%Y年%m月%d日')
    elements.append(Paragraph(f'<para alignment="right">编号：{consent_no}&nbsp;&nbsp;&nbsp;&nbsp;日期：{today_str}</para>', label_style))
    elements.append(Spacer(1, 4*mm))

    # 患者信息表格
    gender = data.get('patient_gender', '')
    age = data.get('patient_age', '') or ''
    info_data = [
        [Paragraph(f'姓名：{data.get("patient_name", "")}', label_style),
         Paragraph(f'性别：{gender}', label_style),
         Paragraph(f'年龄：{age}', label_style),
         Paragraph(f'NO. {consent_no}', label_style)]
    ]
    info_table = Table(info_data, colWidths=[45*mm, 30*mm, 30*mm, 45*mm])
    info_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5*mm))

    # 正文条款
    clauses = [
        '1、我理解种植手术治疗的目的和程序，在经过比较后我愿意选择并要求做种植治疗，我理解作为患者应配合医生完成整个治疗过程。',
        '2、我将负责地向医生报告自己的健康状况、既往病史、药物过敏史等，如有隐瞒，愿承担后果。',
        '3、医生已向我介绍了有关麻醉、手术的危险性及可能出现的并发症、术后反应等；如肿胀、疼痛、感染、局部麻木（一时性或长久性）、牙齿损伤、颌骨骨折、上颌窦穿孔、延迟愈合、种植体失败等。我理解这些治疗过程中的一系列问题，并在此基础上同意医生实施种植治疗。',
    ]
    for c in clauses:
        elements.append(Paragraph(c, body_style))
        elements.append(Spacer(1, 2*mm))

    # 第4条（含手术信息）
    brand = data.get('implant_brand', '__________')
    model = data.get('implant_model', '__________')
    positions = data.get('tooth_positions', [])
    pos_str = _format_tooth_positions(positions) if positions else '__________'
    count = data.get('implant_count', '__________')

    clause4 = f'4、我同意医生为我选择的种植体品牌为<u>{brand}</u>，型号为<u>{model}</u>，种植牙位为<u>{pos_str}</u>，种植体数目为<u>{count}</u>，医生已经向我详细介绍了整个治疗过程所需的时间和费用，我可以接受，我也同意医生在术中由于新发现的问题而改变原来的种植计划。'
    elements.append(Paragraph(clause4, body_style))
    elements.append(Spacer(1, 2*mm))

    clauses_5_7 = [
        '5、我理解按口腔医学"种植失败"定义：在正常行使口腔功能的情况下，所出现的种植体松动、脱落、折断而需从骨内取出种植体（不包括外伤所致的种植体损害）。当种植失败时，医生可根据情况决定取出种植体及采取必要的治疗措施。',
        '6、我同意医生在治疗过程中照相、录像以及收集各种资料，医生可利用这些资料作为学术交流与研究，但不可公开身份。',
        '7、种植修复完成后，我将遵照医嘱，保证术后控制吸烟，注意饮食，避免咬过硬食物，坚持正确刷牙。保持口腔卫生，避免外伤，同时保证每半年到一年定期复查。',
    ]
    for c in clauses_5_7:
        elements.append(Paragraph(c, body_style))
        elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph('以上牙种植治疗知情同意书，患者已知情同意并签字。', body_style))
    elements.append(Spacer(1, 6*mm))

    # 签名区域（所有标签文本使用CJK字体）
    sign_label_style = ParagraphStyle('SignLabel', fontName=cjk_font, fontSize=10, alignment=TA_LEFT)
    sign_data = []

    # 患者签名行
    p_date = _fmt_date(data.get('patient_sign_date'))
    p_sign = _get_sign_image(data.get('patient_signature_path'), 40*mm, 15*mm, cjk_font) if data.get('patient_signature_path') else Paragraph('________________', sign_label_style)
    sign_data.append([Paragraph('患者签名：', sign_label_style), p_sign, Paragraph(f'日期：{p_date}', sign_label_style)])

    # 亲属签名行
    g_date = _fmt_date(data.get('guardian_sign_date'))
    g_relation = data.get('guardian_relation', '')
    g_sign = _get_sign_image(data.get('guardian_signature_path'), 40*mm, 15*mm, cjk_font) if data.get('guardian_signature_path') else Paragraph('________________', sign_label_style)
    sign_data.append([Paragraph('法定代理人/亲属签名：', sign_label_style), g_sign, Paragraph(f'与患者关系：{g_relation}&nbsp;&nbsp;&nbsp;&nbsp;日期：{g_date}', sign_label_style)])

    # 医生签名行
    d_date = _fmt_date(data.get('doctor_sign_date'))
    d_sign = _get_sign_image(data.get('doctor_signature_path'), 40*mm, 15*mm, cjk_font) if data.get('doctor_signature_path') else Paragraph('________________', sign_label_style)
    sign_data.append([Paragraph('主治医生签名：', sign_label_style), d_sign, Paragraph(f'日期：{d_date}', sign_label_style)])

    sign_table = Table(sign_data, colWidths=[45*mm, 50*mm, 55*mm])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(sign_table)

    # 审计信息
    elements.append(Spacer(1, 10*mm))
    audit_parts = []
    if data.get('patient_sign_ip'):
        audit_parts.append(f'患者签名IP: {data["patient_sign_ip"]}')
    if data.get('guardian_sign_ip'):
        audit_parts.append(f'亲属签名IP: {data["guardian_sign_ip"]}')
    if data.get('doctor_sign_ip'):
        audit_parts.append(f'医生签名IP: {data["doctor_sign_ip"]}')
    if audit_parts:
        elements.append(Paragraph(' | '.join(audit_parts), small_style))

    doc.build(elements)
    return pdf_path


def _fmt_date(d):
    if not d:
        return '____年____月____日'
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return d.strftime('%Y年%m月%d日')


def _get_sign_image(path, w, h, font_name='Helvetica'):
    """将签名图片嵌入PDF"""
    from reportlab.platypus import Image as RLImage
    if path and os.path.exists(path):
        return RLImage(path, width=w, height=h)
    return Paragraph('________________', ParagraphStyle('placeholder', fontName=font_name, fontSize=10))


def _format_tooth_positions(positions):
    """将牙位数组格式化为可读字符串"""
    if not positions:
        return ''
    names = {
        11: '右上1', 12: '右上2', 13: '右上3', 14: '右上4', 15: '右上5', 16: '右上6', 17: '右上7', 18: '右上8',
        21: '左上1', 22: '左上2', 23: '左上3', 24: '左上4', 25: '左上5', 26: '左上6', 27: '左上7', 28: '左上8',
        31: '左下1', 32: '左下2', 33: '左下3', 34: '左下4', 35: '左下5', 36: '左下6', 37: '左下7', 38: '左下8',
        41: '右下1', 42: '右下2', 43: '右下3', 44: '右下4', 45: '右下5', 46: '右下6', 47: '右下7', 48: '右下8',
    }
    return '、'.join([names.get(p, str(p)) for p in positions])
