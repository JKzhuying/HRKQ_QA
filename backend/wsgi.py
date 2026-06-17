import os
import sys
import traceback

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

# 先初始化数据库（必须在 app 导入之前，确保表存在）
from database import init_database
try:
    init_database()
except Exception as e:
    print('[WSGI] Database init warning:', e)
    traceback.print_exc()

# 导入 Flask 应用
from app import app

# WSGI入口
application = app
