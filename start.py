#!/usr/bin/env python3
"""
口腔诊所财务管理系统 - 启动脚本
适用于宝塔面板部署
"""
import os
import sys
import traceback

# 添加backend目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.app import app
from backend.database import init_database

# 初始化数据库（失败不阻断启动）
try:
    init_database()
except Exception as e:
    print('[START] Database init error:', e)
    traceback.print_exc()

if __name__ == '__main__':
    # 生产环境建议使用gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:5000 start:app
    app.run(host='0.0.0.0', port=5000, debug=False)
