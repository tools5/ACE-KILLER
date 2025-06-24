#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
通知系统模块
"""

import os
import sys
import queue
import threading
import time
from utils.logger import logger
from windows_toasts import InteractableWindowsToaster, Toast, WindowsToaster, ToastImagePosition, ToastButton, ToastDisplayImage, ToastAudio


# 全局通知对象
_toaster = None


def get_toaster():
    """
    获取通知器实例（单例模式）
    
    Returns:
        InteractableWindowsToaster: 通知器实例
    """
    global _toaster
    if _toaster is None:
        _toaster = InteractableWindowsToaster('')
    return _toaster


def send_notification(title, message, icon_path=None, buttons=None, silent=True):
    """
    发送Windows通知
    
    Args:
        title (str): 通知标题
        message (str): 通知内容
        icon_path (str, optional): 图标路径
        buttons (list, optional): 按钮列表，格式：[{'text': '按钮文本', 'action': '动作'}]
        silent (bool, optional): 是否静音通知
    """
    try:
        toaster = get_toaster()
        
        # 根据silent参数设置音频
        audio = ToastAudio(silent=True) if silent else ToastAudio()
        
        # 创建Toast对象
        toast = Toast(text_fields=[title, message], audio=audio)
        
        # 添加图标
        if icon_path and os.path.exists(icon_path):
            try:
                toast.AddImage(ToastDisplayImage.fromPath(icon_path, position=ToastImagePosition.AppLogo))
            except Exception as e:
                logger.warning(f"添加图标失败: {str(e)}")
        
        # 添加按钮
        if buttons:
            for button in buttons:
                if isinstance(button, dict):
                    # 支持字典格式的按钮
                    text = button.get('text', '确定')
                    action = button.get('action', '')
                    launch = button.get('launch', '')
                    toast.AddAction(ToastButton(text, action, launch=launch))
                elif isinstance(button, str):
                    # 支持简单字符串格式的按钮
                    toast.AddAction(ToastButton(button, f'action={button.lower()}'))
        
        # 显示通知
        toaster.show_toast(toast)
        return True
        
    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}")
        return False


def find_icon_path():
    """
    查找应用图标路径
    
    Returns:
        str or None: 找到的图标路径，如果未找到则返回None
    """
    # 查找图标文件
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_paths = [
        # 标准开发环境路径
        os.path.join(base_path, 'assets', 'icon', 'favicon.ico'),
        # 打包环境路径
        os.path.join(os.path.dirname(sys.executable), 'favicon.ico')
    ]
    
    # 静默查找图标文件，使用第一个存在的路径
    for path in icon_paths:
        if os.path.exists(path):
            return path
    
    return None


def notification_thread(message_queue, icon_path=None, stop_event=None):
    """
    通知线程函数，从队列中获取消息并发送通知
    
    Args:
        message_queue (queue.Queue): 消息队列
        icon_path (str, optional): 图标路径
        stop_event (threading.Event, optional): 停止事件
    """
    logger.debug("通知线程已启动")
    
    # 如果未指定停止事件，则创建一个新的
    if stop_event is None:
        stop_event = threading.Event()
    
    while not stop_event.is_set():
        try:
            # 获取消息，最多等待0.5秒
            message = message_queue.get(timeout=0.5)
            
            # 支持字符串和字典格式的消息
            if isinstance(message, str):
                # 简单字符串消息
                send_notification(
                    title="ACE-KILLER 消息通知",
                    message=message,
                    icon_path=icon_path
                )
            elif isinstance(message, dict):
                # 字典格式消息，支持更多自定义选项
                send_notification(
                    title=message.get('title', "ACE-KILLER 消息通知"),
                    message=message.get('message', ''),
                    icon_path=message.get('icon_path', icon_path),
                    buttons=message.get('buttons'),
                    silent=message.get('silent', True)
                )
            
            # 标记任务完成
            message_queue.task_done()
        except queue.Empty:
            # 队列为空，继续等待
            pass
        except Exception as e:
            logger.error(f"处理通知失败: {str(e)}")
            # 尝试短暂休眠以避免CPU占用过高
            time.sleep(0.1)
    
    logger.debug("通知线程已终止")


def create_notification_thread(message_queue, icon_path=None):
    """
    创建并启动通知线程
    
    Args:
        message_queue (queue.Queue): 消息队列
        icon_path (str, optional): 图标路径
        
    Returns:
        (threading.Thread, threading.Event): 线程对象和停止事件
    """
    # 如果未指定图标路径，则尝试查找
    if icon_path is None:
        icon_path = find_icon_path()
    
    # 创建停止事件
    stop_event = threading.Event()
    
    # 创建通知线程
    thread = threading.Thread(
        target=notification_thread,
        args=(message_queue, icon_path, stop_event),
        daemon=True
    )
    
    # 启动线程
    thread.start()
    
    return thread, stop_event 