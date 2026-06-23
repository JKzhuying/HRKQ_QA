#!/usr/bin/env python3
"""
口腔诊所财务管理系统 - 启动脚本 v9.0
适用于宝塔面板部署
"""
import os
import sys
import traceback

# 添加backend目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app import app
from utils.config_manager import config_exists, get_db_config

# v9.0: 检测安装状态，未安装时提示访问安装向导
if not (config_exists() and get_db_config()):
    print('=' * 60)
    print('[SETUP] 系统尚未初始化')
    print('[SETUP] 请访问 http://<服务器IP>:5000/ 完成安装向导')
    print('=' * 60)
else:
    # 已安装，尝试初始化数据库表（失败不阻断启动）
    from database import init_database
    try:
        init_database()
    except Exception as e:
        print('[START] Database init warning:', e)
        traceback.print_exc()

if __name__ == '__main__':
    # 生产环境建议使用gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:5000 start:app
    app.run(host='0.0.0.0', port=5000, debug=False)
