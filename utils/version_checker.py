#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
版本检查和更新模块
"""

import os
import json
import threading
import requests
from packaging import version
from PySide6.QtCore import QObject, Signal
from utils.logger import logger


# 版本信息 - 通过 GitHub Actions 构建时会被替换
__version__ = "1.0.0"  # 默认版本号，构建时会被替换


class VersionChecker(QObject):
    """版本检查器"""
    
    # 版本检查完成信号 - (有更新, 当前版本, 最新版本, 更新信息, 错误信息)
    check_finished = Signal(bool, str, str, str, str)
    
    def __init__(self):
        super().__init__()
        self.github_api_url = "https://api.github.com/repos/cassianvale/ACE-KILLER/releases/latest"
        self.github_releases_url = "https://github.com/cassianvale/ACE-KILLER/releases"
        self.timeout = 10  # 网络请求超时时间（秒）
    
    def get_current_version(self):
        """
        获取当前版本号
        
        Returns:
            str: 当前版本号
        """
        # 首先尝试从环境变量获取版本号（GitHub Actions 构建时设置）
        env_version = os.environ.get('ACE_KILLER_VERSION')
        if env_version:
            return env_version.strip()
        
        # 尝试从版本文件获取
        try:
            version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION')
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    file_version = f.read().strip()
                    if file_version:
                        return file_version
        except Exception as e:
            logger.debug(f"读取版本文件失败: {str(e)}")
        
        # 返回默认版本号
        return __version__
    

    
    def check_for_updates_async(self):
        """
        异步检查更新
        """
        thread = threading.Thread(target=self._check_for_updates_thread)
        thread.daemon = True
        thread.start()
    
    def _check_for_updates_thread(self):
        """
        检查更新的线程函数
        """
        try:
            current_ver = self.get_current_version()
            
            # 发送 HTTP 请求获取最新版本信息
            headers = {
                'User-Agent': f'ACE-KILLER/{current_ver}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            logger.debug(f"正在检查更新，当前版本: {current_ver}")
            
            response = requests.get(
                self.github_api_url, 
                headers=headers, 
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # 请求成功
            release_data = response.json()
            
            # 解析最新版本信息
            latest_version = release_data.get('tag_name', '').lstrip('v')
            release_name = release_data.get('name', '')
            release_body = release_data.get('body', '')
            release_url = release_data.get('html_url', self.github_releases_url)
            
            if not latest_version:
                raise ValueError("无法获取最新版本号")
            
            # 比较版本号
            has_update = self._compare_versions(current_ver, latest_version)
            
            # 查找下载链接（优先查找.zip文件）
            assets = release_data.get('assets', [])
            download_url = None
            for asset in assets:
                asset_name = asset.get('name', '').lower()
                if asset_name.endswith('.zip') and 'x64' in asset_name:
                    download_url = asset.get('browser_download_url')
                    break
            
            # 如果没找到x64的zip，查找任何zip文件
            if not download_url:
                for asset in assets:
                    asset_name = asset.get('name', '').lower()
                    if asset_name.endswith('.zip'):
                        download_url = asset.get('browser_download_url')
                        break
            
            # 构建更新信息
            update_info = {
                'version': latest_version,
                'name': release_name,
                'body': release_body,
                'url': release_url,
                'download_url': download_url,  # 直接下载链接
                'published_at': release_data.get('published_at', ''),
                'assets': assets
            }
            
            update_info_str = json.dumps(update_info, ensure_ascii=False, indent=2)
            
            logger.debug(f"版本检查完成 - 当前: {current_ver}, 最新: {latest_version}, 有更新: {has_update}")
            
            # 发送检查完成信号
            self.check_finished.emit(
                has_update, 
                current_ver, 
                latest_version, 
                update_info_str, 
                ""
            )
            
        except requests.exceptions.Timeout:
            error_msg = "网络请求超时，请检查网络连接后稍后重试"
            logger.warning(f"检查更新失败: {error_msg}")
            self.check_finished.emit(False, self.get_current_version(), "", "", error_msg)
            
        except requests.exceptions.ConnectionError:
            error_msg = "网络连接失败，请检查网络连接后稍后重试"
            logger.warning(f"检查更新失败: {error_msg}")
            self.check_finished.emit(False, self.get_current_version(), "", "", error_msg)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                error_msg = "网络请求被拒绝(403)，可能是网络代理、防火墙或GitHub访问限制导致"
                logger.warning(f"检查更新失败: {error_msg}")
            else:
                error_msg = f"GitHub API 请求失败: {e.response.status_code}"
                logger.warning(f"检查更新失败: {error_msg}")
            self.check_finished.emit(False, self.get_current_version(), "", "", error_msg)
            
        except Exception as e:
            error_msg = f"检查更新时发生错误: {str(e)}"
            logger.error(f"检查更新失败: {error_msg}")
            self.check_finished.emit(False, self.get_current_version(), "", "", error_msg)
    
    def _compare_versions(self, current_ver, latest_ver):
        """
        比较版本号
        
        Args:
            current_ver: 当前版本号
            latest_ver: 最新版本号
            
        Returns:
            bool: 如果有更新返回 True，否则返回 False
        """
        try:
            # 清理版本号格式
            current_clean = self._clean_version(current_ver)
            latest_clean = self._clean_version(latest_ver)
            
            # 使用 packaging 库进行版本比较
            return version.parse(latest_clean) > version.parse(current_clean)
            
        except Exception as e:
            logger.error(f"版本比较失败: {str(e)}")
            # 如果版本比较失败，进行简单的字符串比较
            return current_ver != latest_ver
    
    def _clean_version(self, ver_str):
        """
        清理版本号字符串
        
        Args:
            ver_str: 原始版本号字符串
            
        Returns:
            str: 清理后的版本号
        """
        if not ver_str:
            return "0.0.0"
        
        # 移除 'v' 前缀
        cleaned = ver_str.lstrip('v')
        
        # 移除可能的后缀（如 -beta, -alpha 等）
        import re
        cleaned = re.split(r'[-+]', cleaned)[0]
        
        # 确保版本号格式正确
        parts = cleaned.split('.')
        while len(parts) < 3:
            parts.append('0')
        
        return '.'.join(parts[:3])


def get_version_checker():
    """
    获取版本检查器实例（单例模式）
    
    Returns:
        VersionChecker: 版本检查器实例
    """
    if not hasattr(get_version_checker, '_instance'):
        get_version_checker._instance = VersionChecker()
    return get_version_checker._instance


def get_current_version():
    """
    获取当前版本号的便捷函数
    
    Returns:
        str: 当前版本号
    """
    return get_version_checker().get_current_version()


def format_version_info(current_version, latest_version=None, has_update=False):
    """
    格式化版本信息显示
    
    Args:
        current_version: 当前版本号
        latest_version: 最新版本号（可选）
        has_update: 是否有更新
        
    Returns:
        str: 格式化的版本信息
    """
    if has_update and latest_version:
        return f"当前版本: v{current_version} | 最新版本: v{latest_version} 🆕"
    else:
        return f"当前版本: v{current_version}"


def create_update_message(has_update, current_ver, latest_ver, update_info_str, error_msg):
    """
    创建更新检查结果消息
    
    Args:
        has_update: 是否有更新
        current_ver: 当前版本
        latest_ver: 最新版本
        update_info_str: 更新信息JSON字符串
        error_msg: 错误信息
        
    Returns:
        tuple: (标题, 消息内容, 消息类型, 额外数据)
    """

    # 处理其他错误
    if error_msg:
        return (
            "检查更新失败",
            f"检查更新时遇到问题：\n{error_msg}\n\n"
            f"当前版本: v{current_ver}\n\n"
            f"建议操作：\n"
            f"• 检查网络连接\n"
            f"• 稍后重试\n"
            f"• 直接访问GitHub项目页面获取最新版本\n\n"
            f"是否打开GitHub项目页面？",
            "error",
            {"github_url": "https://github.com/cassianvale/ACE-KILLER/releases"}
        )
    
    # 处理有更新的情况
    if has_update:
        try:
            update_info = json.loads(update_info_str)
            release_name = update_info.get('name', f'v{latest_ver}')
            release_body = update_info.get('body', '').strip()
            release_url = update_info.get('url', 'https://github.com/cassianvale/ACE-KILLER/releases')
            direct_download_url = update_info.get('download_url')
            
            # 限制更新日志长度
            if len(release_body) > 300:
                release_body = release_body[:300] + "..."
            
            message = (
                f"发现新版本！\n\n"
                f"当前版本: v{current_ver}\n"
                f"最新版本: v{latest_ver}\n\n"
                f"版本名称: {release_name}\n\n"
            )
            
            if release_body:
                message += f"更新内容:\n{release_body}\n\n"
            
            # 根据是否有直接下载链接调整消息
            if direct_download_url:
                message += "是否立即下载新版本？"
            else:
                message += "是否前往下载页面？"
            
            return (
                "发现新版本", 
                message, 
                "update",
                {
                    "download_url": direct_download_url if direct_download_url else release_url,
                    "is_direct_download": bool(direct_download_url)
                }
            )
            
        except Exception as e:
            logger.error(f"解析更新信息失败: {str(e)}")
            return (
                "发现新版本",
                f"发现新版本！\n\n当前版本: v{current_ver}\n最新版本: v{latest_ver}\n\n是否前往下载页面？",
                "update",
                {
                    "download_url": "https://github.com/cassianvale/ACE-KILLER/releases",
                    "is_direct_download": False
                }
            )
    else:
        return (
            "已是最新版本",
            f"您当前使用的已经是最新版本。\n\n当前版本: v{current_ver}",
            "info",
            {}
        ) 