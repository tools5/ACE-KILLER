#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
系统工具函数模块
"""

import ctypes
import os
import sys
import win32com.client
from utils.logger import logger


def run_as_admin():
    """
    判断是否以管理员权限运行，如果不是则尝试获取管理员权限
    
    Returns:
        bool: 是否以管理员权限运行
    """
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return False
    return True


def check_single_instance():
    """
    检查程序是否已经在运行，确保只有一个实例
    
    Returns:
        bool: 如果是首次运行返回True，否则返回False
    """
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ACE-KILLER_MUTEX")
    if ctypes.windll.kernel32.GetLastError() == 183:
        logger.warning("程序已经在运行中，无法启动多个实例！")
        
        # 显示提醒弹窗
        show_already_running_dialog()
        return False
    return True


def show_already_running_dialog():
    """
    显示程序已运行的提醒对话框
    """
    try:
        # 使用Windows API显示消息框
        message = (
            "ACE-KILLER 已经在运行中！\n\n"
            "程序只允许运行一个实例。\n"
            "请检查系统托盘是否有ACE-KILLER图标。\n\n"
            "如果找不到运行中的程序，请尝试：\n"
            "• 检查任务管理器中是否有ACE-KILLER进程\n"
            "• 重启电脑后再次运行程序"
        )
        
        title = "ACE-KILLER - 程序已运行"
        
        # 使用Windows API显示消息框
        # MB_OK = 0x00000000, MB_ICONINFORMATION = 0x00000040, MB_TOPMOST = 0x00040000
        ctypes.windll.user32.MessageBoxW(
            0,  # 父窗口句柄
            message,  # 消息内容
            title,  # 标题
            0x00000040 | 0x00040000  # MB_ICONINFORMATION | MB_TOPMOST
        )
        
        logger.debug("已显示程序重复运行提醒对话框")
        
    except Exception as e:
        logger.error(f"显示程序重复运行对话框失败: {str(e)}")
        # 如果显示对话框失败，至少在控制台输出信息
        print("ACE-KILLER 已经在运行中，无法启动多个实例！")


def get_program_path():
    """
    获取程序完整路径
    
    Returns:
        str: 程序完整路径
    """
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        # 直接运行的python脚本
        return os.path.abspath(sys.argv[0])


def check_auto_start(app_name="ACE-KILLER"):
    """
    检查是否设置了开机自启（通过检查startup文件夹中的快捷方式）
    
    Args:
        app_name (str): 应用名称，默认为ACE-KILLER
    
    Returns:
        bool: 是否设置了开机自启
    """
    try:
        # 获取startup文件夹路径
        startup_folder = os.path.join(os.path.expanduser("~"), 
                                    "AppData", "Roaming", "Microsoft", "Windows", 
                                    "Start Menu", "Programs", "Startup")
        
        # 快捷方式文件路径
        shortcut_path = os.path.join(startup_folder, f"{app_name}.lnk")
        
        # 检查快捷方式是否存在
        if not os.path.exists(shortcut_path):
            return False
        
        # 检查快捷方式是否指向当前程序
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            target_path = shortcut.TargetPath
            arguments = shortcut.Arguments
            
            current_path = get_program_path()
            expected_args = "--minimized"
            
            # 比较路径和参数
            if (target_path.lower() == current_path.lower() and 
                arguments.strip() == expected_args):
                return True
            else:
                logger.warning(f"快捷方式路径或参数不一致，将更新。目标:{target_path}，参数:{arguments}，当前:{current_path}")
                return False
                
        except Exception as e:
            logger.error(f"读取快捷方式信息失败: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"检查开机自启状态失败: {str(e)}")
        return False


def enable_auto_start(app_name="ACE-KILLER"):
    """
    设置开机自启（通过在startup文件夹中创建快捷方式）
    
    Args:
        app_name (str): 应用名称，默认为ACE-KILLER
        
    Returns:
        bool: 操作是否成功
    """
    try:
        # 获取startup文件夹路径
        startup_folder = os.path.join(os.path.expanduser("~"), 
                                    "AppData", "Roaming", "Microsoft", "Windows", 
                                    "Start Menu", "Programs", "Startup")
        
        # 确保startup文件夹存在
        if not os.path.exists(startup_folder):
            os.makedirs(startup_folder, exist_ok=True)
        
        # 快捷方式文件路径
        shortcut_path = os.path.join(startup_folder, f"{app_name}.lnk")
        
        # 创建快捷方式
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = get_program_path()
        shortcut.Arguments = "--minimized"  # 开机自启时自动最小化到托盘
        shortcut.Description = f"{app_name}"
        shortcut.WorkingDirectory = os.path.dirname(get_program_path())
        
        # 保存快捷方式
        shortcut.save()
        
        logger.debug(f"已设置开机自启（将最小化到托盘启动），快捷方式路径: {shortcut_path}")
        return True
        
    except Exception as e:
        logger.error(f"设置开机自启失败: {str(e)}")
        return False


def disable_auto_start(app_name="ACE-KILLER"):
    """
    取消开机自启（删除startup文件夹中的快捷方式）
    
    Args:
        app_name (str): 应用名称，默认为ACE-KILLER
        
    Returns:
        bool: 操作是否成功
    """
    try:
        # 获取startup文件夹路径
        startup_folder = os.path.join(os.path.expanduser("~"), 
                                    "AppData", "Roaming", "Microsoft", "Windows", 
                                    "Start Menu", "Programs", "Startup")
        
        # 快捷方式文件路径
        shortcut_path = os.path.join(startup_folder, f"{app_name}.lnk")
        
        # 删除快捷方式文件
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)
            logger.debug(f"已取消开机自启，删除快捷方式: {shortcut_path}")
        else:
            logger.debug("快捷方式不存在，无需删除")
        
        return True
        
    except Exception as e:
        logger.error(f"取消开机自启失败: {str(e)}")
        return False 