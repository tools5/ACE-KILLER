#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
配置管理模块
"""

import os
import yaml
from utils.logger import logger
from core.system_utils import check_auto_start, enable_auto_start, disable_auto_start


class ConfigManager:
    """配置管理类"""

    def __init__(self):
        """初始化配置管理器"""
        self.config_dir = os.path.join(os.path.expanduser("~"), ".ace-killer")
        self.log_dir = os.path.join(self.config_dir, "logs")
        self.config_file = os.path.join(self.config_dir, "config.yaml")

        # 应用设置
        self.show_notifications = True  # Windows通知开关默认值
        self.auto_start = False  # 开机自启动开关默认值
        self.monitor_enabled = True  # ACE弹窗监控开关默认值
        self.close_to_tray = True  # 关闭窗口时最小化到后台（True）还是直接退出（False），默认最小化到后台
        self.log_retention_days = 7  # 默认日志保留天数
        self.log_rotation = "1 day"  # 默认日志轮转周期
        self.debug_mode = False  # 调试模式默认值
        self.theme = "light"  # 主题设置默认值（light/dark）

        # 内存清理设置
        self.memory_cleaner_enabled = False  # 内存清理开关默认值
        self.memory_cleaner_brute_mode = True  # 内存清理暴力模式默认值
        self.memory_cleaner_switches = [False] * 6  # 内存清理选项默认值
        self.memory_cleaner_interval = 300  # 内存清理间隔默认值(秒)
        self.memory_cleaner_threshold = 80.0  # 内存占用触发阈值默认值(百分比)
        self.memory_cleaner_cooldown = 60  # 内存清理冷却时间默认值(秒)

        # I/O优先级设置
        self.io_priority_processes = []  # 需要自动设置I/O优先级的进程名列表，格式为[{"name": "进程名", "priority": 0}]

        # 确保配置目录存在
        self._ensure_directories()

        # 加载配置文件
        self.load_config()

    def _ensure_directories(self):
        """确保配置和日志目录存在"""
        # 确保配置目录存在
        if not os.path.exists(self.config_dir):
            try:
                os.makedirs(self.config_dir)
                logger.debug(f"已创建配置目录: {self.config_dir}")
            except Exception as e:
                logger.error(f"创建配置目录失败: {str(e)}")

        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
                logger.debug(f"已创建日志目录: {self.log_dir}")
            except Exception as e:
                logger.error(f"创建日志目录失败: {str(e)}")

    def load_config(self):
        """
        加载配置文件

        Returns:
            bool: 是否加载成功
        """
        default_config = {
            "notifications": {"enabled": True},
            "logging": {"retention_days": 7, "rotation": "1 day", "debug_mode": False},
            "application": {"auto_start": False, "close_to_tray": True, "theme": "light"},
            "monitor": {"enabled": False},
            "memory_cleaner": {
                "enabled": False,
                "brute_mode": True,
                "switches": [True, True, False, False, False, False],
                "interval": 300,
                "threshold": 80.0,
                "cooldown": 60,
            },
            "io_priority": {
                "processes": [{"name": "SGuard64.exe", "priority": 0}, {"name": "ACE-Tray.exe", "priority": 0}]
            },
        }

        # 如果配置文件存在，则读取
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                # 如果配置文件为空或无效，使用默认配置
                if not config_data:
                    config_data = default_config
                    logger.warning("配置文件为空或无效，将使用默认配置")

                # 读取通知设置
                if "notifications" in config_data and "enabled" in config_data["notifications"]:
                    self.show_notifications = bool(config_data["notifications"]["enabled"])
                    logger.debug(f"已从配置文件加载通知设置: {self.show_notifications}")

                # 读取日志设置
                if "logging" in config_data:
                    if "retention_days" in config_data["logging"]:
                        self.log_retention_days = int(config_data["logging"]["retention_days"])
                    if "rotation" in config_data["logging"]:
                        self.log_rotation = config_data["logging"]["rotation"]
                    if "debug_mode" in config_data["logging"]:
                        self.debug_mode = bool(config_data["logging"]["debug_mode"])
                        logger.debug(f"已从配置文件加载调试模式设置: {self.debug_mode}")

                # 读取开机自启设置
                if "application" in config_data and "auto_start" in config_data["application"]:
                    self.auto_start = bool(config_data["application"]["auto_start"])
                    # 检查实际注册表状态与配置是否一致
                    actual_auto_start = check_auto_start()
                    if self.auto_start != actual_auto_start:
                        logger.warning(
                            f"开机自启配置与实际状态不一致，配置为:{self.auto_start}，实际为:{actual_auto_start}，将以配置为准"
                        )

                    # 确保注册表状态与配置一致
                    if self.auto_start:
                        enable_auto_start()
                    else:
                        disable_auto_start()

                    logger.debug(f"已从配置文件加载开机自启设置: {self.auto_start}")
                else:
                    # 如果配置中没有自启设置，检查注册表中是否已设置
                    if check_auto_start():
                        # 如果注册表中已设置，则更新配置
                        self.auto_start = True
                        logger.debug("检测到注册表中已设置开机自启，已更新配置")

                # 读取关闭行为设置
                if "application" in config_data and "close_to_tray" in config_data["application"]:
                    self.close_to_tray = bool(config_data["application"]["close_to_tray"])
                    logger.debug(
                        f"已从配置文件加载关闭行为设置: {'最小化到后台' if self.close_to_tray else '直接退出'}"
                    )

                # 读取主题设置
                if "application" in config_data and "theme" in config_data["application"]:
                    theme_value = config_data["application"]["theme"]
                    if theme_value in ["light", "dark"]:
                        self.theme = theme_value
                        logger.debug(f"已从配置文件加载主题设置: {self.theme}")
                    else:
                        logger.warning(f"配置文件中的主题值无效: {theme_value}，使用默认值: light")
                        self.theme = "light"

                # 读取监控设置
                if "monitor" in config_data and "enabled" in config_data["monitor"]:
                    self.monitor_enabled = bool(config_data["monitor"]["enabled"])
                    logger.debug(f"已从配置文件加载监控设置: {self.monitor_enabled}")

                # 读取内存清理设置
                if "memory_cleaner" in config_data:
                    if "enabled" in config_data["memory_cleaner"]:
                        self.memory_cleaner_enabled = bool(config_data["memory_cleaner"]["enabled"])
                    if "brute_mode" in config_data["memory_cleaner"]:
                        self.memory_cleaner_brute_mode = bool(config_data["memory_cleaner"]["brute_mode"])
                    if "switches" in config_data["memory_cleaner"] and isinstance(
                        config_data["memory_cleaner"]["switches"], list
                    ):
                        for i, switch in enumerate(config_data["memory_cleaner"]["switches"]):
                            if i < len(self.memory_cleaner_switches):
                                self.memory_cleaner_switches[i] = bool(switch)
                    if "interval" in config_data["memory_cleaner"]:
                        self.memory_cleaner_interval = int(config_data["memory_cleaner"]["interval"])
                        # 确保配置值合法
                        if self.memory_cleaner_interval < 60:
                            self.memory_cleaner_interval = 60
                    if "threshold" in config_data["memory_cleaner"]:
                        self.memory_cleaner_threshold = float(config_data["memory_cleaner"]["threshold"])
                        # 确保配置值在合法范围
                        if self.memory_cleaner_threshold < 30:
                            self.memory_cleaner_threshold = 30
                        elif self.memory_cleaner_threshold > 95:
                            self.memory_cleaner_threshold = 95
                    if "cooldown" in config_data["memory_cleaner"]:
                        self.memory_cleaner_cooldown = int(config_data["memory_cleaner"]["cooldown"])
                        # 确保配置值合法
                        if self.memory_cleaner_cooldown < 30:
                            self.memory_cleaner_cooldown = 30
                    logger.debug("已从配置文件加载内存清理设置")

                # 读取I/O优先级设置
                if "io_priority" in config_data and "processes" in config_data["io_priority"]:
                    self.io_priority_processes = config_data["io_priority"]["processes"]
                    logger.debug(f"已从配置文件加载I/O优先级设置，进程数量: {len(self.io_priority_processes)}")

                logger.debug("配置文件加载成功")
                return True
            except Exception as e:
                logger.error(f"加载配置文件失败: {str(e)}")
                # 使用默认配置
                self._create_default_config(default_config)
                return False
        else:
            # 如果配置文件不存在，则创建默认配置文件
            logger.debug("配置文件不存在，将创建默认配置文件")
            self._create_default_config(default_config)
            return True

    def _create_default_config(self, default_config):
        """
        创建默认配置文件

        Args:
            default_config (dict): 默认配置数据
        """
        try:
            # 使用默认配置
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

            # 从默认配置中加载设置
            self.show_notifications = default_config["notifications"]["enabled"]
            self.log_retention_days = default_config["logging"]["retention_days"]
            self.log_rotation = default_config["logging"]["rotation"]
            self.debug_mode = default_config["logging"]["debug_mode"]
            self.auto_start = default_config["application"]["auto_start"]
            self.close_to_tray = default_config["application"]["close_to_tray"]
            self.theme = default_config["application"]["theme"]
            self.monitor_enabled = default_config["monitor"]["enabled"]

            # 加载内存清理默认设置
            if "memory_cleaner" in default_config:
                self.memory_cleaner_enabled = default_config["memory_cleaner"]["enabled"]
                self.memory_cleaner_brute_mode = default_config["memory_cleaner"]["brute_mode"]
                for i, switch in enumerate(default_config["memory_cleaner"]["switches"]):
                    if i < len(self.memory_cleaner_switches):
                        self.memory_cleaner_switches[i] = switch
                if "interval" in default_config["memory_cleaner"]:
                    self.memory_cleaner_interval = default_config["memory_cleaner"]["interval"]
                if "threshold" in default_config["memory_cleaner"]:
                    self.memory_cleaner_threshold = default_config["memory_cleaner"]["threshold"]
                if "cooldown" in default_config["memory_cleaner"]:
                    self.memory_cleaner_cooldown = default_config["memory_cleaner"]["cooldown"]

            # 加载I/O优先级默认设置
            if "io_priority" in default_config and "processes" in default_config["io_priority"]:
                self.io_priority_processes = default_config["io_priority"]["processes"]

            logger.debug("已创建并加载默认配置")
        except Exception as e:
            logger.error(f"创建默认配置文件失败: {str(e)}")

    def save_config(self):
        """
        保存配置到文件

        Returns:
            bool: 保存是否成功
        """
        try:
            # 构建配置数据
            config_data = {
                "notifications": {"enabled": self.show_notifications},
                "logging": {
                    "retention_days": self.log_retention_days,
                    "rotation": self.log_rotation,
                    "debug_mode": self.debug_mode,
                },
                "application": {
                    "auto_start": self.auto_start,
                    "close_to_tray": self.close_to_tray,
                    "theme": self.theme,
                },
                "monitor": {"enabled": self.monitor_enabled},
                "memory_cleaner": {
                    "enabled": self.memory_cleaner_enabled,
                    "brute_mode": self.memory_cleaner_brute_mode,
                    "switches": self.memory_cleaner_switches,
                    "interval": self.memory_cleaner_interval,
                    "threshold": self.memory_cleaner_threshold,
                    "cooldown": self.memory_cleaner_cooldown,
                },
                "io_priority": {"processes": self.io_priority_processes},
            }

            # 保存到文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

            logger.debug("配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
            return False
