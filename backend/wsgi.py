import os
import sys
import traceback

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

# v9.0: 安装状态检测
from utils.config_manager import config_exists, get_db_config

if config_exists() and get_db_config():
    # 已安装：初始化数据库表
    from database import init_database
    try:
        init_database()
    except Exception as e:
        print('[WSGI] Database init warning:', e)
        traceback.print_exc()
else:
    print('[WSGI] System not initialized yet, setup wizard will be served.')

# v8.5: 应用启动时立即启动自动备份（使用文件锁防止多Worker重复启动）
if config_exists() and get_db_config():
    try:
        import fcntl
        lock_fd = os.open('/tmp/dental-finance-wsgi.lock', os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # 获取到锁，说明是第一个Worker，启动调度器
            from routes.auto_backup import start_auto_backup_scheduler
            start_auto_backup_scheduler()
        except (OSError, IOError):
            pass  # 其他Worker已获取锁，跳过
    except ImportError:
        # fcntl 在Windows上不可用，直接启动（Windows通常单进程开发）
        from routes.auto_backup import start_auto_backup_scheduler
        start_auto_backup_scheduler()
    except Exception as e:
        print(f'[WSGI] AutoBackup init error: {e}')

# 导入 Flask 应用
from app import app

# WSGI入口
application = app
