#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
模拟SGuard64.exe进程的测试脚本
用于测试ACE-KILLER的进程监控和优化功能

pyinstaller --onefile --name SGuard64 mock_sguard64.py
"""

import os
import sys
import time
import signal
import psutil
import win32api
import win32con
import win32process
from loguru import logger

EXPECTED_PROCESS_NAME = "SGuard64.exe"

def setup_logging():
    """配置日志"""
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_sguard64.log")
    logger.add(log_path, rotation="1 day", retention="3 days", level="INFO")

def verify_process_name():
    """验证进程名称"""
    current_process = psutil.Process()
    process_name = current_process.name()
    
    if process_name != EXPECTED_PROCESS_NAME:
        logger.warning(f"当前进程名称为 {process_name}，与期望的 {EXPECTED_PROCESS_NAME} 不符")
        logger.info("请使用PyInstaller将此脚本打包为SGuard64.exe")
        logger.info("打包命令: pyinstaller --name SGuard64 mock_sguard64.py")
        return False
    return True

def set_process_priority(priority=win32process.NORMAL_PRIORITY_CLASS):
    """设置进程优先级"""
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, os.getpid())
        win32process.SetPriorityClass(handle, priority)
        priority_name = {
            win32process.IDLE_PRIORITY_CLASS: "IDLE",
            win32process.BELOW_NORMAL_PRIORITY_CLASS: "BELOW_NORMAL",
            win32process.NORMAL_PRIORITY_CLASS: "NORMAL",
            win32process.ABOVE_NORMAL_PRIORITY_CLASS: "ABOVE_NORMAL",
            win32process.HIGH_PRIORITY_CLASS: "HIGH",
            win32process.REALTIME_PRIORITY_CLASS: "REALTIME"
        }.get(priority, "UNKNOWN")
        logger.info(f"进程优先级已设置为: {priority_name}")
    except Exception as e:
        logger.error(f"设置进程优先级失败: {e}")

def signal_handler(signum, frame):
    """信号处理函数"""
    logger.info(f"收到信号: {signum}")
    sys.exit(0)

def main():
    """主函数"""
    # 设置日志
    setup_logging()
    
    # 验证进程名称
    if not verify_process_name():
        logger.warning("进程名称验证失败，但将继续运行")
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 获取进程信息
    current_process = psutil.Process()
    logger.info(f"模拟进程已启动 - PID: {current_process.pid}")
    
    # 设置较高的进程优先级
    set_process_priority(win32process.HIGH_PRIORITY_CLASS)
    
    try:
        while True:
            # 模拟一些CPU使用
            for _ in range(1000000):
                _ = 1 + 1
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"运行时错误: {e}")
    finally:
        logger.info("模拟进程正在退出")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"程序异常退出: {e}")
        sys.exit(1)
