"""
安装向导 API - v9.0
功能：环境检测、MySQL连接测试、全自动安装（创建库/用户/表）
安全：root 密码用后即焚，不保存；生成随机强密码和用户名
"""
import random
from flask import Blueprint, request, jsonify
import pymysql
from pymysql.cursors import DictCursor

from utils.config_manager import (
    get_db_config,
    mark_installed,
    generate_secure_password,
    config_exists,
)

setup_bp = Blueprint('setup', __name__)

# 固定数据库名
DB_NAME = 'dental_finance'
# 用户名前缀
DB_USER_PREFIX = 'hrkq'


def _connect_root(data):
    """使用 root 凭据连接 MySQL Server（不指定 database）"""
    return pymysql.connect(
        host=data.get('host', 'localhost'),
        port=data.get('port', 3306),
        user=data.get('root_user', 'root'),
        password=data.get('root_password', ''),
        connect_timeout=5,
        cursorclass=DictCursor,
    )


@setup_bp.route('/check', methods=['GET'])
def check_setup():
    """检查安装状态和环境"""
    # 已安装且配置有效
    existing = get_db_config()
    if existing:
        return jsonify({'code': 200, 'installed': True})

    # 未安装，检测 MySQL 是否可访问
    mysql_running = False
    try:
        # 尝试无密码连接 localhost root（部分环境允许）
        conn = pymysql.connect(
            host='localhost', port=3306, user='root',
            connect_timeout=2, cursorclass=DictCursor,
        )
        conn.close()
        mysql_running = True
    except Exception:
        pass

    return jsonify({
        'code': 200,
        'installed': False,
        'env': {
            'mysql_running': mysql_running,
            'default_host': 'localhost',
            'default_port': 3306,
        }
    })


@setup_bp.route('/test-connection', methods=['POST'])
def test_connection():
    """测试 root 账号能否连接 MySQL"""
    data = request.get_json() or {}
    root_password = data.get('root_password', '')

    try:
        conn = _connect_root(data)
        cursor = conn.cursor()
        cursor.execute('SELECT VERSION() as ver')
        version = cursor.fetchone()['ver']

        # 检查是否有 CREATE DATABASE 权限
        cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
        grants = cursor.fetchall()
        has_create_priv = any('ALL PRIVILEGES' in str(g) or 'CREATE' in str(g) for g in grants)

        conn.close()
        return jsonify({
            'code': 200,
            'message': f'连接成功，MySQL {version}',
            'data': {
                'version': version,
                'has_create_priv': has_create_priv,
            }
        })
    except pymysql.err.OperationalError as e:
        return jsonify({'code': 400, 'message': f'连接失败: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': f'未知错误: {str(e)}'}), 500


@setup_bp.route('/install', methods=['POST'])
def do_install():
    """
    执行全自动安装：
    1. 用 root 连接
    2. 创建数据库（如果不存在）
    3. 生成随机用户名和密码
    4. 创建用户并授权（如果已存在则重置密码）
    5. 保存加密配置
    6. 调用 init_database() 创建表和默认数据
    """
    data = request.get_json() or {}
    root_password = data.get('root_password', '')

    conn = None
    try:
        conn = _connect_root(data)
        cursor = conn.cursor()

        # 1. 创建数据库（固定名，已存在则忽略）
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

        # 2. 生成随机用户名和密码
        suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))
        db_user = f"{DB_USER_PREFIX}_{suffix}"
        db_password = generate_secure_password()

        # 3. 创建用户（兼容已存在场景：先删除旧同名用户再重建，或更新密码）
        # 先尝试删除可能存在的同名用户，避免冲突
        cursor.execute(f"DROP USER IF EXISTS '{db_user}'@'%'")
        cursor.execute(f"DROP USER IF EXISTS '{db_user}'@'localhost'")
        cursor.execute(
            f"CREATE USER '{db_user}'@'%' IDENTIFIED BY '{db_password}'"
        )
        cursor.execute(
            f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{db_user}'@'%'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        conn.commit()
        conn.close()
        conn = None

        # 4. 保存配置
        db_config = {
            'host': data.get('host', 'localhost'),
            'port': data.get('port', 3306),
            'name': DB_NAME,
            'user': db_user,
            'password': db_password,
        }
        mark_installed(db_config)

        # 5. 初始化数据库表（使用新创建的凭据）
        from database import init_database
        try:
            init_database()
        except Exception as e:
            # 建表失败时清理配置，让用户可以重试
            from utils.config_manager import reset_installation
            reset_installation()
            return jsonify({
                'code': 500,
                'message': f'数据库用户创建成功，但建表失败: {str(e)}。请检查权限后重试。'
            }), 500

        return jsonify({
            'code': 200,
            'message': '安装成功',
            'data': {
                'database': DB_NAME,
                'user': db_user,
            }
        })

    except pymysql.err.OperationalError as e:
        return jsonify({'code': 400, 'message': f'安装失败: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': f'安装失败: {str(e)}'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
