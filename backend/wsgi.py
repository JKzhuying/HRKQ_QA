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

# 导入 Flask 应用
from app import app

# WSGI入口
application = app
