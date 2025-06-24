#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
日志系统模块
"""

import os
import sys
import datetime
from loguru import logger as _logger

# 统一logger实例
logger = _logger


def setup_logger(log_dir, log_retention_days=7, log_rotation="1 day", debug_mode=False):
    """
    配置日志系统
    
    Args:
        log_dir (str): 日志保存目录
        log_retention_days (int): 日志保留天数
        log_rotation (str): 日志轮转周期
        debug_mode (bool): 是否启用调试模式
    
    Returns:
        logger: 配置好的logger实例
    """
    # 移除默认的日志处理器
    logger.remove()
    
    # 设置日志级别，调试模式为True时输出DEBUG级别日志，否则输出INFO级别
    log_level = "DEBUG" if debug_mode else "INFO"
    
    # 获取当前日期作为日志文件名的一部分
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"{today}.log")

    # 添加文件日志处理器，配置轮转和保留策略，写入到文件中
    logger.add(
        log_file,
        rotation=log_rotation,  # 日志轮转周期
        retention=f"{log_retention_days} days",  # 日志保留天数
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}",
        level=log_level,
        encoding="utf-8"
    )
    
    # 判断是否为打包的可执行文件，以及是否有控制台
    is_frozen = getattr(sys, 'frozen', False)
    has_console = True
    
    # 在Windows下，检查是否有控制台窗口
    if is_frozen and sys.platform == 'win32':
        try:
            # 检查标准错误输出是否存在
            if sys.stderr is None or not sys.stderr.isatty():
                has_console = False
        except (AttributeError, IOError):
            has_console = False
    
    # 只有在有控制台的情况下才添加控制台日志处理器
    if has_console:
        # 添加控制台日志处理器，输出到控制台
        logger.add(
            sys.stderr,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}",
            level=log_level,
            colorize=True
        )
        logger.debug("已添加控制台日志处理器")
    else:
        logger.debug("检测到无控制台环境，不添加控制台日志处理器")
    
    logger.debug(f"日志系统已初始化，日志文件: {log_file}")
    logger.debug(f"日志保留天数: {log_retention_days}，轮转周期: {log_rotation}")
    logger.debug(f"调试模式: {'开启' if debug_mode else '关闭'}")
    
    return logger