#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
模拟VALORANT游戏主进程的测试脚本
用于测试ACE-KILLER的进程监控功能

pyinstaller --onefile --name VALORANT-Win64-Shipping mock_valorant.py
"""

import os
import sys
import time
import signal
import psutil
import subprocess
import win32event
import win32api
import winerror
from loguru import logger

EXPECTED_PROCESS_NAME = "VALORANT-Win64-Shipping.exe"
SGUARD_PROCESS_NAME = "SGuard64.exe"
MUTEX_NAME = "Global\\MOCK_VALORANT_MUTEX"

def setup_logging():
    """配置日志"""
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_valorant.log")
    logger.add(log_path, rotation="1 day", retention="3 days", level="INFO")

def check_already_running():
    """检查是否已有实例在运行"""
    try:
        mutex = win32event.CreateMutex(None, 1, MUTEX_NAME)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            logger.warning("另一个实例已经在运行")
            return True
        return False
    except Exception as e:
        logger.error(f"检查进程互斥失败: {e}")
        return False

def signal_handler(signum, frame):
    """信号处理函数"""
    logger.info(f"收到信号: {signum}")
    sys.exit(0)

def main():
    """主函数"""
    # 设置日志
    setup_logging()
    
    # 检查是否已有实例在运行
    if check_already_running():
        logger.error("程序已经在运行中")
        sys.exit(1)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 获取进程信息
    current_process = psutil.Process()
    logger.info(f"模拟游戏进程已启动 - PID: {current_process.pid}")
    logger.info(f"请手动启动 {SGUARD_PROCESS_NAME} 进行测试")
    
    try:
        while True:
            # 模拟游戏进程活动
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"运行时错误: {e}")
    finally:
        logger.info("模拟游戏进程正在退出")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"程序异常退出: {e}")
        sys.exit(1) 