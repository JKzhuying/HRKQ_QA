import pymysql
from pymysql.cursors import DictCursor


def get_db_connection():
    """v9.0: 从加密配置动态读取数据库连接信息"""
    from utils.config_manager import get_db_config
    config = get_db_config()
    if not config:
        raise RuntimeError('Database not configured. Please complete setup first.')
    config['cursorclass'] = DictCursor
    return pymysql.connect(**config)


def _db_name():
    """获取当前配置的数据库名（用于 information_schema 查询）"""
    from utils.config_manager import get_db_config
    cfg = get_db_config()
    return cfg['database'] if cfg else 'dental_finance'


# ========== 编号生成工具 v8.0 ==========

def generate_link_no(cursor, prefix='LS'):
    """生成业务流水号 PREFIX-YYYYMMDD-XXXXX v8.3支持自定义前缀"""
    from datetime import datetime
    today = prefix + '-' + datetime.now().strftime('%Y%m%d-')
    # v8.3: 根据前缀查对应表
    tables = ['income_records', 'expense_records']
    if prefix == 'TF':
        tables = ['transfer_records']
    max_seq = 0
    for table in tables:
        cursor.execute(f"SELECT MAX(link_no) as m FROM {table} WHERE link_no LIKE %s", (today + '%',))
        row = cursor.fetchone()
        if row and row['m']:
            try:
                s = int(row['m'].split('-')[-1])
                if s > max_seq:
                    max_seq = s
            except (ValueError, IndexError):
                pass
    return today + str(max_seq + 1).zfill(5)


def generate_voucher_no(cursor):
    """生成凭证号 PZ-YYYYMMDD-XXX"""
    from datetime import datetime
    today = datetime.now().strftime('PZ-%Y%m%d-')
    cursor.execute("SELECT MAX(voucher_no) as m FROM vouchers WHERE voucher_no LIKE %s", (today + '%',))
    row = cursor.fetchone()
    seq = 1
    if row and row['m']:
        try:
            seq = int(row['m'].split('-')[-1]) + 1
        except (ValueError, IndexError):
            pass
    return today + str(seq).zfill(3)


def _table_exists(cursor, table_name):
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
    ''', (_db_name(), table_name))
    return cursor.fetchone()['cnt'] > 0


def _col_exists(cursor, table_name, col_name):
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
    ''', (_db_name(), table_name, col_name))
    return cursor.fetchone()['cnt'] > 0


def _row_count(cursor, table_name):
    cursor.execute(f'SELECT COUNT(*) as cnt FROM {table_name}')
    return cursor.fetchone()['cnt']


def _drop_if_exists(cursor, table_name):
    if _table_exists(cursor, table_name):
        cursor.execute(f'DROP TABLE {table_name}')


def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # ========== 1. 收费大类 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS category_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            trans_type ENUM('income', 'expense') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_name_type (name, trans_type)
        )
    ''')
    if _row_count(cursor, 'category_records') == 0:
        defaults = [
            ('治疗','income'),('治疗加固定修复','income'),('固定修复','income'),
            ('种植','income'),('活动牙','income'),('财务费用','income'),
            ('美学','income'),('治疗加美学','income'),
            ('治疗','expense'),('治疗加固定修复','expense'),('固定修复','expense'),
            ('种植','expense'),('活动牙','expense'),('财务费用','expense'),
            ('美学','expense'),('治疗加美学','expense'),
        ]
        for n, t in defaults:
            cursor.execute('INSERT INTO category_records (name, trans_type) VALUES (%s, %s)', (n, t))

    # ========== 2. 银行账号维护 v8.0 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account_name VARCHAR(100) NOT NULL,
            bank_name VARCHAR(100),
            account_no VARCHAR(30),
            l2_code VARCHAR(15) COMMENT '对应二级科目代码',
            l2_name VARCHAR(50) COMMENT '对应二级科目名称',
            is_active TINYINT DEFAULT 1,
            is_default TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # v8.3.1: 兼容旧表添加新字段
    for new_col in ["l2_code VARCHAR(15)", "l2_name VARCHAR(50)"]:
        try:
            cursor.execute(f'ALTER TABLE bank_accounts ADD COLUMN {new_col}')
        except Exception:
            pass  # 字段已存在
    # v8.3.1: 为旧数据补充分配 l2_code
    cursor.execute('SELECT id, account_name FROM bank_accounts WHERE l2_code IS NULL OR l2_code = ""')
    for row in cursor.fetchall():
        l2_code = f"1002.{row['id']:02d}"
        l2_name = f"银行存款—{row['account_name']}"
        cursor.execute('UPDATE bank_accounts SET l2_code = %s, l2_name = %s WHERE id = %s',
                       (l2_code, l2_name, row['id']))
    if _row_count(cursor, 'bank_accounts') == 0:
        cursor.execute('''
            INSERT INTO bank_accounts (account_name, is_active, is_default) VALUES (%s, 1, 1)
        ''', ('现金',))

    # ========== 3. 一级会计科目 v8.0 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_subjects_l1 (
            id INT AUTO_INCREMENT PRIMARY KEY,
            code VARCHAR(10) NOT NULL UNIQUE,
            name VARCHAR(50) NOT NULL,
            category VARCHAR(20) NOT NULL,
            direction VARCHAR(10) DEFAULT 'debit',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 兼容修复：如果之前创建了 direction VARCHAR(5) 的旧表，扩大到 VARCHAR(10)
    if _col_exists(cursor, 'account_subjects_l1', 'direction'):
        cursor.execute('''
            ALTER TABLE account_subjects_l1
            MODIFY COLUMN direction VARCHAR(10) DEFAULT 'debit'
        ''')
    # L1 默认数据：INSERT IGNORE 补充缺失记录（兼容之前部分插入失败的情况）
    l1_defaults = [
        ('1002','银行存款','资产','debit'),
        ('1001','库存现金','资产','debit'),
        ('1601','固定资产','资产','debit'),
        ('1602','累计折旧','资产','credit'),
        ('2221','应交税费','负债','credit'),
        ('6001','主营业务收入','损益-收入','credit'),
        ('6403','营业税金及附加','损益-费用','debit'),
        ('6602','管理费用','损益-费用','debit'),
        ('6603','财务费用','损益-费用','debit'),
    ]
    for c, n, cat, d in l1_defaults:
        cursor.execute('INSERT IGNORE INTO account_subjects_l1 (code, name, category, direction) VALUES (%s, %s, %s, %s)', (c, n, cat, d))

    # ========== 4. 二级会计科目 v8.0 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_subjects_l2 (
            id INT AUTO_INCREMENT PRIMARY KEY,
            parent_id INT NOT NULL,
            code VARCHAR(15) NOT NULL UNIQUE,
            name VARCHAR(50) NOT NULL,
            is_active TINYINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES account_subjects_l1(id)
        )
    ''')
    if _row_count(cursor, 'account_subjects_l2') == 0:
        # 根据 L1 实际 id 动态插入（不硬编码 parent_id，兼容部分数据缺失场景）
        cursor.execute('SELECT id, code FROM account_subjects_l1')
        l1_id_map = {row['code']: row['id'] for row in cursor.fetchall()}
        l2_defaults = [
            ('1001', '1001.01', '库存现金—现金'),
            ('1002', '1002.01', '银行存款—对公账户'),
            ('6603', '6603.01', '财务费用—手续费'),
            ('6602', '6602.01', '管理费用—折旧费'),
            ('6602', '6602.02', '管理费用—办公费'),
            ('6602', '6602.03', '管理费用—水电费'),
        ]
        for parent_code, code, name in l2_defaults:
            pid = l1_id_map.get(parent_code)
            if pid:
                cursor.execute('INSERT INTO account_subjects_l2 (parent_id, code, name, is_active) VALUES (%s, %s, %s, 1)', (pid, code, name))

    # ========== 5. 科目映射 v8.0 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS category_subject_map (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category_id INT NOT NULL UNIQUE,
            subject_l2_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES category_records(id),
            FOREIGN KEY (subject_l2_id) REFERENCES account_subjects_l2(id)
        )
    ''')

    # ========== 6. 收支表 v8.0 / v9.0 fix ==========
    # v9.0: 补充 income_records 和 expense_records 建表语句（旧版本缺失）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS income_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trans_date DATE NOT NULL,
            counterparty VARCHAR(200),
            category VARCHAR(50),
            item_name VARCHAR(200),
            amount_receivable DECIMAL(12,2) DEFAULT 0,
            amount_real DECIMAL(12,2) DEFAULT 0,
            payment_method VARCHAR(20) DEFAULT 'cash',
            remark TEXT,
            source_file VARCHAR(200),
            link_no VARCHAR(20) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expense_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trans_date DATE NOT NULL,
            counterparty VARCHAR(200),
            category VARCHAR(50),
            item_name VARCHAR(200),
            amount_receivable DECIMAL(12,2) DEFAULT 0,
            amount_real DECIMAL(12,2) DEFAULT 0,
            payment_method VARCHAR(20) DEFAULT 'cash',
            remark TEXT,
            source_file VARCHAR(200),
            link_no VARCHAR(20) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # v8.0 兼容：为旧表补充 link_no 字段
    if not _col_exists(cursor, 'income_records', 'link_no'):
        cursor.execute('ALTER TABLE income_records ADD COLUMN link_no VARCHAR(20) UNIQUE')
    if not _col_exists(cursor, 'expense_records', 'link_no'):
        cursor.execute('ALTER TABLE expense_records ADD COLUMN link_no VARCHAR(20) UNIQUE')

    # ========== 7. 凭证表 v8.0 ==========
    # 如果旧表有外键约束，先删除重建 v8.0 fix
    if _table_exists(cursor, 'vouchers'):
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM information_schema.KEY_COLUMN_USAGE
            WHERE table_schema = %s AND table_name = 'vouchers'
            AND referenced_table_name IS NOT NULL
        ''', (_db_name(),))
        if cursor.fetchone()['cnt'] > 0:
            cursor.execute('DROP TABLE voucher_entries')
            cursor.execute('DROP TABLE vouchers')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vouchers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            voucher_no VARCHAR(20) NOT NULL UNIQUE,
            voucher_date DATE NOT NULL,
            source_type VARCHAR(20),
            source_table VARCHAR(20),
            source_id INT,
            link_no VARCHAR(20),
            total_amount DECIMAL(12,2) DEFAULT 0,
            status ENUM('draft', 'confirmed') DEFAULT 'draft',
            audit_time TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remark TEXT
        )
    ''')
    # v8.3.1: 给link_no加唯一索引，数据库层面阻止重复凭证
    try:
        cursor.execute('ALTER TABLE vouchers ADD UNIQUE INDEX uk_vouchers_link_no (link_no)')
    except Exception:
        pass  # 索引已存在或有重复数据

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voucher_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            voucher_id INT NOT NULL,
            seq_no INT NOT NULL,
            subject_l1_code VARCHAR(10) NOT NULL,
            subject_l2_code VARCHAR(15),
            subject_name VARCHAR(50),
            direction ENUM('debit', 'credit') NOT NULL,
            amount DECIMAL(12,2) NOT NULL,
            bank_account_id INT,
            summary VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE,
            FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
        )
    ''')

    # ========== 8. 旧表迁移 ==========
    _drop_if_exists(cursor, 'income_items')

    if _table_exists(cursor, 'transactions'):
        cursor.execute('''
            INSERT IGNORE INTO income_records (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, source_file, created_at)
            SELECT trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, source_file, created_at FROM transactions WHERE trans_type = 'income'
        ''')
        cursor.execute('''
            INSERT IGNORE INTO expense_records (trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, source_file, created_at)
            SELECT trans_date, counterparty, category, item_name, amount_receivable, amount_real, payment_method, remark, source_file, created_at FROM transactions WHERE trans_type = 'expense'
        ''')
        cursor.execute('DROP TABLE transactions')
        print('Migrated old transactions table')

    # 系统设置
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            `key` VARCHAR(50) PRIMARY KEY, value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    ''')
    if _row_count(cursor, 'system_settings') == 0:
        cursor.execute('INSERT INTO system_settings (`key`, value) VALUES (%s, %s)', ('clinic_name', '我的口腔诊所'))

    # ========== 9. 自动备份配置 v8.1 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_backup_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            is_enabled TINYINT DEFAULT 0,
            interval_hours INT DEFAULT 24,
            save_path VARCHAR(500) DEFAULT '/www/wwwroot/dental-finance/backups',
            last_backup_time TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    ''')
    if _row_count(cursor, 'auto_backup_settings') == 0:
        cursor.execute('''
            INSERT INTO auto_backup_settings (id, is_enabled, interval_hours, save_path)
            VALUES (1, 0, 24, '/www/wwwroot/dental-finance/backups')
        ''')

    # 自动备份日志
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_backup_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            status ENUM('success', 'failed') NOT NULL,
            file_path VARCHAR(500),
            file_size BIGINT DEFAULT 0,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ========== 10. 资金调拨记录 v8.3 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transfer_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trans_date DATE NOT NULL,
            from_account VARCHAR(100) NOT NULL COMMENT '转出账户名称',
            to_account VARCHAR(100) NOT NULL COMMENT '转入账户名称',
            amount DECIMAL(10,2) NOT NULL COMMENT '调拨金额',
            remark TEXT,
            link_no VARCHAR(20) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # v8.3: 兼容旧表，添加新字段
    for new_col in ['from_bank_id INT', 'to_bank_id INT',
                     'amount_planned DECIMAL(10,2) NOT NULL DEFAULT 0',
                     'amount_real DECIMAL(10,2) NOT NULL DEFAULT 0']:
        try:
            cursor.execute(f'ALTER TABLE transfer_records ADD COLUMN {new_col}')
        except Exception:
            pass  # 字段已存在或其他错误

    # ========== 11. 会计期间表 v8.5 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounting_periods (
            id INT AUTO_INCREMENT PRIMARY KEY,
            year INT NOT NULL,
            month INT NOT NULL,
            status ENUM('open', 'closing', 'closed') DEFAULT 'open',
            is_year_end BOOLEAN DEFAULT FALSE,
            closed_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_year_month (year, month)
        )
    ''')

    # ========== 12. 科目期初余额表 v8.5 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subject_balances (
            id INT AUTO_INCREMENT PRIMARY KEY,
            period_id INT NOT NULL,
            subject_l1_code VARCHAR(10) NOT NULL,
            subject_l2_code VARCHAR(15) NULL COMMENT 'NULL表示一级科目直接录入',
            opening_balance DECIMAL(12,2) NOT NULL DEFAULT 0,
            current_debit DECIMAL(12,2) NOT NULL DEFAULT 0,
            current_credit DECIMAL(12,2) NOT NULL DEFAULT 0,
            closing_balance DECIMAL(12,2) NOT NULL DEFAULT 0,
            is_l1_entry BOOLEAN DEFAULT FALSE COMMENT '是否一级科目直接录入',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_period_subject (period_id, subject_l1_code, subject_l2_code)
        )
    ''')

    # ========== 13. 期初余额跳过记录 v8.5 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opening_balance_skip_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            skipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ========== 14. 扩展一级科目预设 v8.5 ==========
    # v8.5: 增加口腔诊所常用一级科目
    l1_extended = [
        # 资产类
        ('1012', '其他货币资金', '资产', 'debit'),
        ('1121', '应收票据', '资产', 'debit'),
        ('1401', '材料采购', '资产', 'debit'),
        ('1408', '委托加工物资', '资产', 'debit'),
        ('1603', '固定资产清理', '资产', 'debit'),
        ('1701', '无形资产', '资产', 'debit'),
        ('1801', '长期待摊费用', '资产', 'debit'),
        ('1901', '待处理财产损溢', '资产', 'debit'),
        # 负债类
        ('2101', '交易性金融负债', 'liability', 'credit'),
        ('2201', '应付票据', 'liability', 'credit'),
        ('2211', '应付职工薪酬', 'liability', 'credit'),
        ('2231', '应付利息', 'liability', 'credit'),
        ('2232', '应付股利', 'liability', 'credit'),
        ('2241', '其他应付款', 'liability', 'credit'),
        ('2401', '递延收益', 'liability', 'credit'),
        # 权益类
        ('4002', '资本公积', 'equity', 'credit'),
        ('4101', '盈余公积', 'equity', 'credit'),
        # 成本类
        ('5101', '制造费用', 'cost', 'debit'),
        ('5301', '研发支出', 'cost', 'debit'),
        # 损益 - 收入
        ('6051', '其他业务收入', 'income', 'credit'),
        ('6111', '投资收益', 'income', 'credit'),
        ('6301', '营业外收入', 'income', 'credit'),
        # 损益 - 费用
        ('6401', '主营业务成本', 'expense', 'debit'),
        ('6411', '利息支出', 'expense', 'debit'),
        ('6601', '销售费用', 'expense', 'debit'),
        ('6701', '资产减值损失', 'expense', 'debit'),
        ('6711', '营业外支出', 'expense', 'debit'),
        ('6801', '所得税费用', 'expense', 'debit'),
    ]
    for c, n, cat, d in l1_extended:
        cursor.execute(
            'INSERT IGNORE INTO account_subjects_l1 (code, name, category, direction) VALUES (%s, %s, %s, %s)',
            (c, n, cat, d)
        )

    # ========== 15. 库存管理表 v8.5 ==========
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_photos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            original_name VARCHAR(255),
            storage_path VARCHAR(500) NOT NULL,
            file_size INT,
            upload_method ENUM('手机拍照','本地上传','扫描') DEFAULT '本地上传',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            contact_person VARCHAR(100),
            phone VARCHAR(50),
            address TEXT,
            business_license_no VARCHAR(200),
            status ENUM('启用','停用') DEFAULT '启用',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS supplier_photos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            supplier_id INT NOT NULL,
            photo_type ENUM('营业执照','医疗器械经营许可证','其他') NOT NULL,
            storage_path VARCHAR(500) NOT NULL,
            file_size INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(50) NOT NULL DEFAULT '耗材',
            name VARCHAR(200) NOT NULL,
            specification VARCHAR(200),
            quantity DECIMAL(10,2) NOT NULL,
            unit VARCHAR(20) NOT NULL,
            production_date DATE,
            expiry_date DATE,
            batch_no VARCHAR(50),
            manufacturer VARCHAR(200),
            manufacturer_license VARCHAR(100),
            unit_price DECIMAL(12,4),
            tax_amount DECIMAL(12,4),
            total_price DECIMAL(12,4) NOT NULL,
            is_qualified ENUM('合格','不合格','待检') DEFAULT '合格',
            photo_id INT,
            supplier_id INT,
            batch_no_rk VARCHAR(50),
            operator VARCHAR(50),
            remark TEXT,
            status ENUM('在库','已出库','报废') DEFAULT '在库',
            current_stock DECIMAL(10,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            inventory_id INT,
            action_type ENUM('入库','出库','盘点','报废') NOT NULL,
            quantity DECIMAL(10,2),
            operator VARCHAR(50),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_batch_counters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            entry_date DATE NOT NULL UNIQUE,
            counter INT NOT NULL DEFAULT 0
        )
    ''')

    # v8.6.6: 文件签署中心 - 通用同意书表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consent_documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doc_no CHAR(7) NOT NULL UNIQUE COMMENT '7位编号',
            doc_type ENUM('种植手术','补牙','拔牙','根管治疗') NOT NULL DEFAULT '种植手术',
            patient_name VARCHAR(50) NOT NULL,
            patient_gender ENUM('男','女') NOT NULL,
            patient_age INT,
            patient_id VARCHAR(50) COMMENT '病历号',
            allergy_history VARCHAR(255) COMMENT '过敏史: 无 / 有:xxx',
            tooth_positions JSON COMMENT '牙位数组如[11,12,21]',
            extra_fields JSON COMMENT '各类型特有的动态字段',
            patient_signature_path VARCHAR(255) COMMENT '患者签名PNG路径',
            patient_sign_date DATE,
            patient_sign_ip VARCHAR(50),
            guardian_signature_path VARCHAR(255) COMMENT '亲属签名PNG路径',
            guardian_relation ENUM('父子','母子','父女','母女','兄弟','姐妹','其他监护人'),
            guardian_sign_date DATE,
            guardian_sign_ip VARCHAR(50),
            doctor_signature_path VARCHAR(255) COMMENT '主治医生签名PNG路径',
            doctor_sign_date DATE,
            doctor_sign_ip VARCHAR(50),
            pdf_path VARCHAR(255) COMMENT '生成PDF路径',
            barcode_image_path VARCHAR(255) COMMENT '种植体标签照片路径',
            status ENUM('草稿','已完成','已作废') DEFAULT '草稿',
            created_by VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    ''')

    # v8.6.6: 同意书模板表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consent_templates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doc_type VARCHAR(50) NOT NULL UNIQUE,
            title VARCHAR(100),
            clauses JSON COMMENT '条款数组',
            field_schema JSON COMMENT '表单字段定义',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()

    # v8.6.6: 新增 barcode_image_path 字段（已有表时）
    try:
        cursor.execute('ALTER TABLE consent_documents ADD COLUMN barcode_image_path VARCHAR(255) COMMENT %s', ('种植体标签照片照片路径',))
    except Exception:
        pass  # 字段已存在

    # v8.6.6: 更新数据库中旧的路径记录（backend/uploads → uploads）
    _migrate_upload_paths(cursor)

    # v8.6.6: 迁移旧数据 + 初始化模板
    _migrate_consent_data(cursor)
    _init_consent_templates(cursor)

    conn.commit()
    conn.close()
    print('MySQL init done v8.6.6')


def _migrate_upload_paths(cursor):
    """v8.6.6: 更新数据库中存储的旧路径（backend/uploads → uploads）"""
    import os
    # consent_documents 表中的文件路径字段
    path_fields = ['patient_signature_path', 'guardian_signature_path',
                   'doctor_signature_path', 'barcode_image_path', 'pdf_path']
    for field in path_fields:
        try:
            cursor.execute(f"""
                UPDATE consent_documents
                SET {field} = REPLACE({field}, 'backend/uploads/', 'uploads/')
                WHERE {field} IS NOT NULL AND {field} LIKE '%backend/uploads/%'
            """)
            if cursor.rowcount > 0:
                print(f'[MIGRATE] 已更新 {field} 中 {cursor.rowcount} 条旧路径')
        except Exception:
            pass  # 字段可能不存在，忽略


def _migrate_consent_data(cursor):
    """v8.6.6: 从旧表 informed_consents 迁移数据到 consent_documents"""
    # 检查旧表是否存在
    cursor.execute("SHOW TABLES LIKE 'informed_consents'")
    if not cursor.fetchone():
        return
    # 检查新表是否已有数据
    cursor.execute('SELECT COUNT(*) as cnt FROM consent_documents')
    if cursor.fetchone()['cnt'] > 0:
        return
    # 迁移数据
    try:
        cursor.execute('''
            INSERT INTO consent_documents
            (doc_no, doc_type, patient_name, patient_gender, patient_age,
             tooth_positions, extra_fields, allergy_history,
             patient_signature_path, patient_sign_date, patient_sign_ip,
             guardian_signature_path, guardian_relation, guardian_sign_date, guardian_sign_ip,
             doctor_signature_path, doctor_sign_date, doctor_sign_ip,
             pdf_path, status, created_by, created_at, updated_at)
            SELECT
                consent_no, '种植手术', patient_name, patient_gender, patient_age,
                tooth_positions,
                JSON_OBJECT('implant_brand', implant_brand, 'implant_model', implant_model, 'implant_count', implant_count),
                NULL,
                patient_signature_path, patient_sign_date, patient_sign_ip,
                guardian_signature_path, guardian_relation, guardian_sign_date, guardian_sign_ip,
                doctor_signature_path, doctor_sign_date, doctor_sign_ip,
                pdf_path, status, created_by, created_at, updated_at
            FROM informed_consents
        ''')
    except Exception as e:
        print(f'[Migrate Warning] {e}')


def _init_consent_templates(cursor):
    """v8.6.6: 初始化/刷新同意书模板数据。每次启动无条件更新，确保条款内容与代码一致。"""
    templates = _get_consent_template_data()
    for t in templates:
        cursor.execute('SELECT id FROM consent_templates WHERE doc_type = %s', (t['doc_type'],))
        row = cursor.fetchone()
        if row:
            cursor.execute('''
                UPDATE consent_templates
                SET title = %s, clauses = %s, field_schema = %s
                WHERE doc_type = %s
            ''', (t['title'], json.dumps(t['clauses'], ensure_ascii=False), json.dumps(t['field_schema'], ensure_ascii=False), t['doc_type']))
        else:
            cursor.execute('''
                INSERT INTO consent_templates (doc_type, title, clauses, field_schema)
                VALUES (%s, %s, %s, %s)
            ''', (t['doc_type'], t['title'], json.dumps(t['clauses'], ensure_ascii=False), json.dumps(t['field_schema'], ensure_ascii=False)))


def _get_consent_template_data():
    """v8.6.6: 4种同意书的条款和字段定义"""
    return [
        {
            'doc_type': '种植手术',
            'title': '种植手术知情同意书',
            'clauses': [
                '1、我理解种植手术治疗的目的和程序，在经过比较后我愿意选择并要求做种植治疗，我理解作为患者应配合医生完成整个治疗过程。',
                '2、我将负责地向医生报告自己的健康状况、既往病史、药物过敏史等，如有隐瞒，愿承担后果。',
                '3、医生已向我介绍了有关麻醉、手术的危险性及可能出现的并发症、术后反应等；如肿胀、疼痛、感染、局部麻木（一时性或长久性）、牙齿损伤、颌骨骨折、上颌窦穿孔、延迟愈合、种植体失败等。我理解这些治疗过程中的一系列问题，并在此基础上同意医生实施种植治疗。',
                '4、我同意医生为我选择的种植体品牌为【{implant_brand}】，型号为【{implant_model}】，种植牙位为【{tooth_positions}】，种植体数目为【{implant_count}】，医生已经向我详细介绍了整个治疗过程所需的时间和费用，我可以接受，我也同意医生在术中由于新发现的问题而改变原来的种植计划。',
                '5、我理解按口腔医学"种植失败"定义：在正常行使口腔功能的情况下，所出现的种植体松动、脱落、折断而需从骨内取出种植体（不包括外伤所致的种植体损害）。当种植失败时，医生可根据情况决定取出种植体及采取必要的治疗措施。',
                '6、我同意医生在治疗过程中照相、录像以及收集各种资料，医生可利用这些资料作为学术交流与研究，但不可公开身份。',
                '7、种植修复完成后，我将遵照医嘱，保证术后控制吸烟，注意饮食，避免咬过硬食物，坚持正确刷牙。保持口腔卫生，避免外伤，同时保证每半年到一年定期复查。',
            ],
            'field_schema': [
                {'name': 'implant_brand', 'label': '植体品牌', 'type': 'text', 'required': True},
                {'name': 'implant_model', 'label': '型号', 'type': 'text', 'required': True},
                {'name': 'tooth_positions', 'label': '种植牙位', 'type': 'tooth_selector', 'required': True},
                {'name': 'implant_count', 'label': '种植体数目', 'type': 'number', 'required': True, 'default': 1},
            ]
        },
        {
            'doc_type': '补牙',
            'title': '补牙知情同意书',
            'clauses': [
                '一、患者基本情况',
                '临床诊断：【{diagnosis}】',
                '二、拟实施的诊断方案',
                '【{treatment_plan}】（医生手写）',
                '三、需要患者确认的基本情况：根据医生的询问及您的陈述，医生会在对应处打（√）',
                '过敏史：{allergy_history}',
                '四、治疗过程中或治疗后可能出现的风险和意外：',
                '1、用于修复龋坏、外伤、磨损等原因造成的牙体缺损，充填材料主要有复合树脂和嵌体等，性能不同价格也有差异，可根据实际情况做选择。',
                '2、对于缺损较大的牙齿，重度磨耗的牙齿以及咬合紧的牙齿，充填时有可能调磨对颌牙敏感或疼痛等症状。',
                '3、牙体缺损充填治疗后数日至数周内，患牙有轻微冷热敏感症状多属于正常反应，一般可自行缓解。为增加保护生活牙髓的机会，对于不能诊断为牙髓炎的深龋，医生按常规采取充填治疗，如果出现自发疼痛、咬合疼痛或冷热敏感长期无好转，则可能牙髓已有炎症，一旦出现上诉症状则需要牙髓治疗，需要承担继续治疗的费用。',
                '4、由于洞型固位不佳、唾液多隔湿效果差等因素可能导致充填物脱落，我们建议三个月到半年复查一次。对于充填后质保期内出现充填脱落的情况，除事先约定的试探保留治疗外，只收取继续治疗的费用，不收取本次治疗的充填材料费用；如改用其他材料和方法只有去差价部分。',
                '5、医学学科在相当程度上是一个实践学科，治疗的成功率有很大的差异，尤其牙齿的复杂多变性及个体差异，存在一定失败风险，在操作中医生可以根据病情对预定的操作方式作出调整。',
                '6、根据术前检查及体质情况，除上述风险外，您在治疗中或治疗后还有可能出现下列风险和意外。',
                '五、补牙注意事项：',
                '1、补牙后24小时内不能用补牙侧咀嚼食物；一周内先用补牙侧进软食，以后逐渐适应。',
                '2、补牙后感觉松动或脱落出现食物嵌塞、疼痛等情况应及时与经治医生联系复诊。',
                '3、不能用补牙侧咬过硬、过韧食物，以免充填物磨损或脱落。',
                '4、补牙后需认真维持口腔卫生，每年复诊2次。',
                '5、根据术前检查及体质情况，除上述注意事项外，您在治疗后，还要特别注意下列事项。',
                '六、患者知情选择：',
                '1、对本知情同意书一至五部分内容，医生均详细对我进行了告知，根据术前检查及体质情况，可能出现意外及风险和需要特别注意事项，是医生告知我之后书写的，对此我表示充分理解并给予确认。',
                '2、在实施治疗前，医生除将上述内容详细告知我之外，还通过口头方式，向我详细介绍了有关替代医疗方案。',
                '3、在充分了解拟实施治疗方案和替代医疗方案优劣利弊、治疗中或治疗后可能出现的风险和意外的基础上，我自愿做如下决定：',
                '（1）同意实施本知情同意书第二项记载的治疗方案。',
                '（2）授权医师对本治疗中采集的照片、X光片及病例资料用于非商业意图的学术交流。',
                '（3）治疗中或治疗后，一旦出现医生告知的风险和意外，我完全理解并积极配合医生完成治疗及支付所有及支付所需相关费用。',
                '（4）我同意在治疗中，如果发生紧急情况，医师无法或来不及征得本人或家属意见时，授权医师按照医学常规予以紧急处理和救治，我自愿承担相关紧急处理和救治费用。',
            ],
            'field_schema': [
                {'name': 'patient_id', 'label': '病历号', 'type': 'text', 'required': True},
                {'name': 'diagnosis', 'label': '临床诊断', 'type': 'text', 'required': True},
                {'name': 'treatment_plan', 'label': '拟实施的诊断方案', 'type': 'handwrite', 'required': True},
                {'name': 'tooth_positions', 'label': '补牙牙位', 'type': 'tooth_selector', 'required': True},
            ]
        },
        {
            'doc_type': '拔牙',
            'title': '拔牙知情同意书',
            'clauses': [
                '姓名：【{patient_name}】 性别：【{patient_gender}】 年龄：【{patient_age}】',
                '诊断：【{diagnosis}】',
                '在拔牙过程中，医生需要综合分析患者的身体状况，以便决定是否施行拔牙术和拔牙时间。如有以下情况请主动告知医生。若患者隐瞒病史造成不良后果，由患者自行负责。',
                '1、有无拔牙史（{has_history_1}）  2、有无药物及麻醉过敏史（{has_history_2}）',
                '3、有无血液病（血友病、血小板减少性紫癜、白血病、贫血等）（{has_history_3}）',
                '4、有无心脏病、高血压、肝脏病、肾脏病、糖尿病、甲亢、口腔恶性肿瘤等疾病（{has_history_4}）',
                '5、是否处于月经期或妊娠期（{has_history_5}）',
                '6、是否空腹（{has_history_6}）  7、是否急性炎症期（{has_history_7}）',
                '8、建议：',
                '①、此牙可以进行治疗，患者拒绝（{patient_decline_1}）',
                '②、此牙可经正畸治疗，患者拒绝（{patient_decline_2}）',
                '9、【{custom_note}】',
                '在实行牙齿拔除术时，一般无并发症，但因病人个体差异，局部解剖结构异常变化等原因，有可能出现麻醉并发症、晕厥、牙根折断、软组织损伤、邻牙或对颌牙损伤、牙槽骨及下颌骨骨折、颞下颌关节脱位、上颌窦穿孔、下颌管损伤、下唇麻木、拔牙后出血、拔牙后感染、皮下气肿等并发症，如出现拔牙并发症患者应积极主动配合医生进行治疗。',
                '拔牙注意事项：',
                '1.紧咬棉球40分钟后，轻轻吐出；',
                '2.24小时内不能刷牙漱口，不食过热食物，不用舌吮拔牙创面，避免剧烈运动；',
                '3.24小时内吐出唾液带血丝为正常状况，如为血块应立即到医院复诊；',
                '4.拔牙后出现感染、疼痛可口服抗生素及止痛药或到医院复诊；',
                '5.一般拔牙后1-3月需镶假牙（阻生牙除外）。',
                '上述内容医生已向我详细解释，我已完全理解，我愿意承担因治疗可能出现的风险并遵从医嘱，配合医生完成全部治疗并同意支付所需全部费用。',
            ],
            'field_schema': [
                {'name': 'diagnosis', 'label': '诊断', 'type': 'text', 'required': True},
                {'name': 'tooth_positions', 'label': '拔牙牙位', 'type': 'tooth_selector', 'required': True},
                {'name': 'has_history_1', 'label': '1.有无拔牙史', 'type': 'yesno', 'required': True},
                {'name': 'has_history_2', 'label': '2.有无药物及麻醉过敏史', 'type': 'yesno', 'required': True},
                {'name': 'has_history_3', 'label': '3.有无血液病', 'type': 'yesno', 'required': True},
                {'name': 'has_history_4', 'label': '4.有无心脏病等疾病', 'type': 'yesno', 'required': True},
                {'name': 'has_history_5', 'label': '5.是否处于月经期或妊娠期', 'type': 'yesno', 'required': True},
                {'name': 'has_history_6', 'label': '6.是否空腹', 'type': 'yesno', 'required': True},
                {'name': 'has_history_7', 'label': '7.是否急性炎症期', 'type': 'yesno', 'required': True},
                {'name': 'patient_decline_1', 'label': '8①.此牙可治疗患者拒绝', 'type': 'handwrite', 'required': False},
                {'name': 'patient_decline_2', 'label': '8②.此牙可正畸治疗患者拒绝', 'type': 'handwrite', 'required': False},
                {'name': 'custom_note', 'label': '9.补充说明', 'type': 'text', 'required': False},
            ]
        },
        {
            'doc_type': '根管治疗',
            'title': '根管治疗知情同意书',
            'clauses': [
                '姓名：【{patient_name}】 性别：【{patient_gender}】 年龄：【{patient_age}】 NO.【{patient_id}】',
                '主诉：【{chief_complaint}】（医生手写）',
                'PE：【{pe}】（医生手写）',
                'IMP：【{imp}】',
                '1、牙髓治疗应用于牙髓炎或已坏死导致根尖周病变的牙齿，目前国际上普通采用的治疗是根管治疗，其过程较为复杂，费用较高，（目前国际上成功率达到95%以上，如若再治疗成功率能达65%）。',
                '2、根管治疗是一种较为复杂的牙髓治疗方法，需要经过根管预备、封药、充填和拍摄多张X线片（一般两到三张）才能完成整个疗程。',
                '3、由于牙根埋伏在颌骨中，术前医生只能根据X线片或根尖定位仪对根管系统进行大致了解，遇复杂根管，如弯曲、细窄、钙化阻塞或变异根管等其他特殊情况，导致根管不通畅，炎症不能完全消除，偶尔可能发生器械折断的情况，对于取不出的器械而无症状的患牙，不要强行取出器械，其可以作为根管充填材料的一部分留在根管中，不会对机体有损伤，对于取不出的器械而有炎症的患牙，建议拔除再行修复。',
                '4、根管治疗过程中通常需要配合局部麻醉，通常麻醉反应有：①恶心、呕吐②晕厥③神经麻痹和损伤④皮疹等症状到严重的过敏性休克⑤血肿⑥注射区溃疡及水肿⑦感染⑧暂时性面瘫或暂时性牙关紧闭⑨断针及其他麻醉意外，请治疗前如实告知您的全身情况，以便医生根据您自身情况为您选择适当的麻醉方法，若因患者隐瞒病史而引起的任何意外，自行负责。',
                '5、根管预备或根管充填后数周内可能会出现疼痛反应，多数属正常反应。如果疼痛严重，伴有局部肿胀和全身反应，应及时复诊，进一步治疗。',
                '6、根管治疗完成后，机体有一个修复过程，在相当一段时间内（少则数周，多则数月），个别人会感到患牙不适，如酸、麻、胀等感觉，可采取观察方法，极少数患者会感觉到疼痛，如果逐渐加重请及时复查。',
                '7、因患牙炎症较重，常规根管治疗无法彻底消除炎症，甚至治疗失败的病例，后期可采用根尖手术的方法继续治疗，甚至拔除。费用另计。',
                '8、根管治疗后的牙齿抗折断能力降低，易劈裂，治疗后必须进行全冠修复或桩核冠修复。冠修复前请避免使用患牙咀嚼硬物。',
                '9、治疗过程中由于张口时间过长，有可能发生颞下颌关节不舒服甚至脱落。',
                '10、在根管治疗过程中，要清洗消毒根管。根据患者情况需换药2-3次，封药后一定遵医嘱按时复诊，如若因不能及时复诊而导致的患牙不适甚至治疗失败及全身反应后果自负。消炎药有一定的刺激性，有可能引起疼痛甚至肿胀，通常几天后会好转，可配合口服消炎药、止痛药，如症状加重，可随时复诊。',
                '11、治疗过程中，如患者未与医生沟通，擅自取出根管内药物或充填材料或私自去别院就诊，所出现问题由患者负全责，治疗费用概不退还。',
                '12、需通过根管治疗而姑息保留的患牙（经试验性治疗）成功与否及治疗术后患牙使用的时间长短均不能给予保证，并且治疗后患者不能正常行使其功能的应拔除时，所需费用自付。',
                '患者陈述：【{patient_statement}】（医生手写）',
                '我同意在操作中医生可以根据我的病情对预定的操作方式作出调整。配合医生完成全部治疗并同意支付所需全部费用。',
                '我理解我的操作需要多位医生共同进行，我并未得到操作百分之百成功的许诺。',
                '同意我的病历及影像资料被用于学术交流与临床研究。',
                '医生陈述：【{doctor_statement}】（医生手写）',
                '我已告知患者将要进行的治疗方式和此次操作后可能发生的并发症和风险，可能存在的其他治疗方法并且解答了患者关于此次操作的相关问题。',
            ],
            'field_schema': [
                {'name': 'tooth_positions', 'label': '治疗牙位', 'type': 'tooth_selector', 'required': True},
                {'name': 'chief_complaint', 'label': '主诉', 'type': 'handwrite', 'required': True},
                {'name': 'pe', 'label': 'PE', 'type': 'handwrite', 'required': True},
                {'name': 'imp', 'label': 'IMP', 'type': 'text', 'required': False},
                {'name': 'patient_statement', 'label': '患者陈述', 'type': 'handwrite', 'required': True},
                {'name': 'doctor_statement', 'label': '医生陈述', 'type': 'handwrite', 'required': True},
            ]
        },
    ]
