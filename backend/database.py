import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'hrkq', 'password': 'Qaz1121zz',
    'database': 'dental_finance', 'charset': 'utf8mb4',
    'cursorclass': DictCursor,
}


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


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
    ''', (DB_CONFIG['database'], table_name))
    return cursor.fetchone()['cnt'] > 0


def _col_exists(cursor, table_name, col_name):
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
    ''', (DB_CONFIG['database'], table_name, col_name))
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
            is_active TINYINT DEFAULT 1,
            is_default TINYINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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

    # ========== 6. 收支表增加 link_no v8.0 ==========
    # income_records
    if not _col_exists(cursor, 'income_records', 'link_no'):
        cursor.execute('ALTER TABLE income_records ADD COLUMN link_no VARCHAR(20) UNIQUE')
    # expense_records
    if not _col_exists(cursor, 'expense_records', 'link_no'):
        cursor.execute('ALTER TABLE expense_records ADD COLUMN link_no VARCHAR(20) UNIQUE')

    # ========== 7. 凭证表 v8.0 ==========
    # 如果旧表有外键约束，先删除重建 v8.0 fix
    if _table_exists(cursor, 'vouchers'):
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM information_schema.KEY_COLUMN_USAGE
            WHERE table_schema = %s AND table_name = 'vouchers'
            AND referenced_table_name IS NOT NULL
        ''', (DB_CONFIG['database'],))
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

    conn.commit()
    conn.close()
    print('MySQL init done v8.3')
