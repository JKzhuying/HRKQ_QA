"""
配置管理模块 - v9.0
功能：机器绑定加密、配置读写、安装状态管理
安全策略：
  - 密钥由机器 MAC + 主机名派生（PBKDF2），配置文件仅本机可用
  - Fernet 对称加密，AES-128-CBC
  - 文件权限 600（仅所有者可读写）
  - 不保存 root 密码，不暴露数据库密码给用户
"""
import os
import json
import base64
import hashlib
import uuid
import socket
import secrets
import string
from datetime import datetime

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 固定的盐值（增加熵，防止同机器不同项目密钥碰撞）
_SALT = b'dental-finance-salt-v1-2026'


def _get_config_path():
    """
    获取配置文件存储路径。
    优先级：环境变量 > 项目目录下的 .config/ > 用户主目录
    自动处理权限问题，确保配置可写。
    """
    # 1. 环境变量指定（运维人员可自定义）
    env_path = os.environ.get('DENTAL_FINANCE_CONFIG_PATH', '').strip()
    if env_path:
        return os.path.join(env_path, 'config.enc')

    # 2. 项目目录下的 .config/（推荐，宝塔/www用户都兼容）
    # 从当前文件位置推导：utils/ 的父目录是 backend/，再父级是项目根
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_config_dir = os.path.join(project_root, '.config')

    # 3. 测试项目目录是否可写（尝试创建目录）
    try:
        os.makedirs(project_config_dir, exist_ok=True)
        # 测试写权限：尝试创建一个临时文件
        test_file = os.path.join(project_config_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('1')
        os.remove(test_file)
        return os.path.join(project_config_dir, 'config.enc')
    except (OSError, PermissionError, IOError):
        pass  # 项目目录不可写，降级

    # 4. 降级：用户主目录
    home_dir = os.path.expanduser('~/.dental-finance')
    return os.path.join(home_dir, 'config.enc')


# 配置文件路径
CONFIG_FILE = _get_config_path()
CONFIG_DIR = os.path.dirname(CONFIG_FILE)


def _get_machine_key():
    """基于机器特征生成 Fernet 密钥"""
    mac = uuid.getnode()
    hostname = socket.gethostname()
    raw = f'dental-finance-setup-v1-{mac}-{hostname}'

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(raw.encode('utf-8')))
    return key


def _get_fernet():
    return Fernet(_get_machine_key())


def config_exists():
    """检查配置文件是否存在"""
    return os.path.exists(CONFIG_FILE)


def load_config():
    """加载并解密配置，返回字典或 None"""
    if not config_exists():
        return None
    try:
        with open(CONFIG_FILE, 'rb') as f:
            encrypted = f.read()
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode('utf-8'))
    except Exception:
        return None


def save_config(config_dict):
    """加密并保存配置"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    fernet = _get_fernet()
    plaintext = json.dumps(config_dict, ensure_ascii=False, indent=2).encode('utf-8')
    encrypted = fernet.encrypt(plaintext)
    with open(CONFIG_FILE, 'wb') as f:
        f.write(encrypted)
    # 设置文件权限为仅所有者可读写
    os.chmod(CONFIG_FILE, 0o600)


def get_db_config():
    """
    获取数据库连接配置，返回 pymysql 可用的字典。
    未安装时返回 None。
    """
    config = load_config()
    if not config or not config.get('installed'):
        return None
    db = config.get('database', {})
    if not db.get('user') or not db.get('password'):
        return None
    return {
        'host': db.get('host', 'localhost'),
        'port': db.get('port', 3306),
        'user': db.get('user', ''),
        'password': db.get('password', ''),
        'database': db.get('name', 'dental_finance'),
        'charset': 'utf8mb4',
    }


def mark_installed(db_config_dict):
    """标记安装完成并保存数据库配置"""
    config = {
        'installed': True,
        'installed_at': datetime.now().isoformat(),
        'database': db_config_dict,
    }
    save_config(config)


def generate_secure_password(length=16):
    """生成包含大小写+数字+符号的随机强密码"""
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in '!@#$%^&*' for c in password)
        ):
            return password


def reset_installation():
    """删除配置文件，用于重新安装（谨慎使用）"""
    if config_exists():
        os.remove(CONFIG_FILE)
