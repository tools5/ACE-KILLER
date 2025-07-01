#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PySide6 GUI界面模块
"""

import os
import sys
import webbrowser  
import threading
import subprocess
import time
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QCheckBox, QSystemTrayIcon, QMenu, 
    QGroupBox, QTabWidget, QFrame, QMessageBox, QScrollArea,
    QGridLayout, QProgressDialog, QProgressBar, QComboBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QIcon, QAction, QPainterPath, QRegion, QPainter, QBrush, QPen, QColor
from utils.logger import logger
from utils.version_checker import get_version_checker, get_current_version, create_update_message
from utils.notification import send_notification
from core.system_utils import enable_auto_start, disable_auto_start
from utils.memory_cleaner import get_memory_cleaner
from utils.process_io_priority import get_io_priority_manager, IO_PRIORITY_HINT
from ui.process_io_priority_manager import show_process_io_priority_manager
from ui.components.custom_titlebar import CustomTitleBar
from ui.styles import (
    ColorScheme, StyleHelper, theme_manager, StatusHTMLGenerator, StyleApplier,
    AntColors, AntColorsDark
)


class MainWindow(QWidget):
    """主窗口"""
    
    # 进度更新信号
    progress_update_signal = Signal(int)
    
    # 删除服务相关信号
    delete_progress_signal = Signal(int)
    delete_result_signal = Signal(str, int, int)
    
    # 停止服务相关信号
    stop_progress_signal = Signal(int)
    stop_result_signal = Signal(str, int, int)
    
    def __init__(self, monitor, icon_path=None, start_minimized=False):
        super().__init__()
        
        self.monitor = monitor
        self.icon_path = icon_path
        self.current_theme = monitor.config_manager.theme
        self.start_minimized = start_minimized
        
        # 自定义标题栏最小化相关
        self.is_custom_minimized = False
        self.original_geometry = None
        
        # 初始化内存清理管理器
        self.memory_cleaner = get_memory_cleaner()
        
        # 初始化版本检查器
        self.version_checker = get_version_checker()
        self.version_checker.check_finished.connect(self._on_version_check_finished)
        
        # 连接信号到槽函数
        self.progress_update_signal.connect(self._update_progress_dialog_value)
        self.delete_progress_signal.connect(self._update_delete_progress)
        self.delete_result_signal.connect(self._show_delete_services_result)
        self.stop_progress_signal.connect(self._update_stop_progress)
        self.stop_result_signal.connect(self._show_stop_services_result)
        
        self.setup_ui()
        self.setup_tray()
        
        # 连接主题切换信号 - 当主题改变时自动应用组件属性
        theme_manager.theme_changed.connect(self.apply_component_properties)
        
        # 初始化定时器和设置
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)
        
        # 应用初始主题
        theme_manager.set_theme(self.current_theme)
        
        # 初始加载设置
        self.load_settings()
        
        # 初始应用组件属性
        self.apply_component_properties()
        
        # 初始应用圆角遮罩
        QTimer.singleShot(10, self.apply_rounded_mask)
    
    def paintEvent(self, event):
        """绘制圆角窗口背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        # 获取当前主题颜色
        colors = AntColorsDark if theme_manager.get_current_theme() == "dark" else AntColors
        
        # 绘制圆角背景
        painter.setBrush(QBrush(QColor(colors.GRAY_1)))
        painter.setPen(QPen(QColor(colors.GRAY_4), 1))
        
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.drawPath(path)
    
    def showEvent(self, event):
        """窗口显示时应用圆角遮罩"""
        super().showEvent(event)
        # 延迟应用圆角遮罩
        QTimer.singleShot(10, self.apply_rounded_mask)
    
    def apply_rounded_mask(self):
        """应用圆角遮罩到窗口"""
        try:
            # 创建圆角路径
            path = QPainterPath()
            path.addRoundedRect(self.rect(), 12, 12)
            
            # 应用遮罩
            region = QRegion(path.toFillPolygon().toPolygon())
            self.setMask(region)
            
        except Exception as e:
            logger.error(f"应用圆角遮罩失败: {str(e)}")
    
    def resizeEvent(self, event):
        """窗口大小改变时重新应用圆角遮罩"""
        super().resizeEvent(event)
        # 延迟应用遮罩以确保窗口完全调整大小后再应用
        QTimer.singleShot(10, self.apply_rounded_mask)
    
    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("ACE-KILLER")
        self.setMinimumSize(600, 780)
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        
        if self.icon_path and os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))
        
        # 创建主布局 - 直接在QWidget上
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 添加自定义标题栏
        self.custom_titlebar = CustomTitleBar(self)
        main_layout.addWidget(self.custom_titlebar)
        
        # 创建内容区域
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 0, 8, 8)
        main_layout.addWidget(content_widget)
        
        # 创建选项卡
        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs)
        
        # 状态选项卡
        status_tab = QWidget()
        status_layout = QVBoxLayout(status_tab)
        
        # 状态信息框
        status_group = QGroupBox("程序状态")
        status_box_layout = QVBoxLayout()
        
        # 创建一个QLabel用于显示状态信息
        self.status_label = QLabel("加载中...")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.status_label.setContentsMargins(5, 5, 5, 5)
        
        # 创建滚动区域
        status_scroll = QScrollArea()
        status_scroll.setWidgetResizable(True)
        status_scroll.setWidget(self.status_label)
        status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        status_scroll.setFrameShape(QFrame.NoFrame)
        
        status_box_layout.addWidget(status_scroll)
        status_group.setLayout(status_box_layout)
        status_layout.addWidget(status_group)
        
        # 进程监控选项卡
        process_tab = QWidget()
        process_layout = QVBoxLayout(process_tab)
        
        # 进程监控组
        process_group = QGroupBox("🚫 ACE反作弊弹窗监控")
        process_box_layout = QVBoxLayout()
        
        # 添加ACE反作弊说明标签
        self.ace_info_label = QLabel(
            "🎯 监控目标：ACE-Tray.exe（反作弊安装弹窗进程）\n"
            "⚡ 功能说明：自动检测并终止ACE反作弊安装弹窗，防止强制安装\n"
            "💡 提示: 进程优化设置在进程重启后会恢复默认值，建议将常用进程添加到自动优化列表中实现持续优化。\n"
            "🪜 VPN出海加速网站：ktcat.su\n"
        )
        self.ace_info_label.setWordWrap(True)
        StyleHelper.set_label_type(self.ace_info_label, "info")
        process_box_layout.addWidget(self.ace_info_label)
        
        # 添加监控状态显示
        status_layout = QHBoxLayout()
        
        # 添加监控开关
        self.monitor_checkbox = QCheckBox("启用ACE弹窗监控")
        self.monitor_checkbox.setChecked(self.monitor.running)
        self.monitor_checkbox.stateChanged.connect(self.toggle_process_monitor)
        status_layout.addWidget(self.monitor_checkbox)
        
        status_layout.addStretch()
        
        process_box_layout.addLayout(status_layout)
        
        process_group.setLayout(process_box_layout)
        process_layout.addWidget(process_group)
        
        # 添加I/O优先级设置功能到进程监控选项卡
        io_priority_group = QGroupBox("🚀 进程优先级管理")
        io_priority_layout = QVBoxLayout()
        
        # 添加说明标签
        self.io_priority_label = QLabel(
            "🎯 通过调整进程优先级可以显著改善系统响应速度和性能表现。\n"
            "💡 支持完整优化：I/O优先级、CPU优先级、CPU亲和性和性能模式设置。\n"
            "✨ 特别适用于优化反作弊、杀毒、下载等后台程序，减少对前台应用的影响。\n"
            "💡 提示: 进程优化设置在进程重启后会恢复默认值，建议将常用进程添加到自动优化列表中实现持续优化。"
        )
        self.io_priority_label.setWordWrap(True)
        StyleHelper.set_label_type(self.io_priority_label, "success")
        io_priority_layout.addWidget(self.io_priority_label)
        
        # 主要功能按钮布局
        main_buttons_layout = QHBoxLayout()
        
        # 进程管理按钮（主要功能）
        self.process_manager_btn = QPushButton("🔍 进程管理器")
        self.process_manager_btn.clicked.connect(self.show_process_manager)
        self.process_manager_btn.setToolTip("打开进程管理器，查看所有进程并进行完整优化")
        main_buttons_layout.addWidget(self.process_manager_btn)
        
        # 管理自动优化列表按钮
        self.manage_io_list_btn = QPushButton("⚙️ 自动优化列表")
        self.manage_io_list_btn.clicked.connect(self.show_auto_optimize_tab)
        self.manage_io_list_btn.setToolTip("查看和管理自动优化列表")
        main_buttons_layout.addWidget(self.manage_io_list_btn)
        
        main_buttons_layout.addStretch()
        io_priority_layout.addLayout(main_buttons_layout)
        
        # 快捷操作分组
        quick_actions_group = QGroupBox("🚀 快捷操作")
        quick_actions_layout = QVBoxLayout()
        
        # 优化反作弊进程按钮
        self.optimize_anticheat_btn = QPushButton("🛡️ 一键优化反作弊进程")
        self.optimize_anticheat_btn.clicked.connect(self.optimize_anticheat_processes)
        self.optimize_anticheat_btn.setToolTip("一键优化所有已知反作弊进程，提升游戏体验")
        quick_actions_layout.addWidget(self.optimize_anticheat_btn)
        
        quick_actions_group.setLayout(quick_actions_layout)
        io_priority_layout.addWidget(quick_actions_group)
        
        io_priority_group.setLayout(io_priority_layout)
        process_layout.addWidget(io_priority_group)
        
        # 内存清理选项卡
        memory_tab = QWidget()
        memory_layout = QVBoxLayout(memory_tab)
        
        # 自动清理选项
        auto_group = QGroupBox("自动清理")
        auto_layout = QVBoxLayout()
        
        # 定时选项
        self.clean_option1 = QCheckBox("定时清理(每5分钟)，截取进程工作集")
        self.clean_option1.stateChanged.connect(lambda state: self.toggle_clean_option(0, state))
        auto_layout.addWidget(self.clean_option1)
        
        self.clean_option2 = QCheckBox("定时清理(每5分钟)，清理系统缓存")
        self.clean_option2.stateChanged.connect(lambda state: self.toggle_clean_option(1, state))
        auto_layout.addWidget(self.clean_option2)
        
        self.clean_option3 = QCheckBox("定时清理(每5分钟)，用全部可能的方法清理内存")
        self.clean_option3.stateChanged.connect(lambda state: self.toggle_clean_option(2, state))
        auto_layout.addWidget(self.clean_option3)
        
        auto_layout.addSpacing(10)
        
        # 使用比例超出80%的选项
        self.clean_option4 = QCheckBox("若内存使用量超出80%，截取进程工作集")

        self.clean_option4.stateChanged.connect(lambda state: self.toggle_clean_option(3, state))
        auto_layout.addWidget(self.clean_option4)
        
        self.clean_option5 = QCheckBox("若内存使用量超出80%，清理系统缓存")
        self.clean_option5.stateChanged.connect(lambda state: self.toggle_clean_option(4, state))
        auto_layout.addWidget(self.clean_option5)
        
        self.clean_option6 = QCheckBox("若内存使用量超出80%，用全部可能的方法清理内存")
        self.clean_option6.stateChanged.connect(lambda state: self.toggle_clean_option(5, state))
        auto_layout.addWidget(self.clean_option6)
        
        auto_group.setLayout(auto_layout)
        memory_layout.addWidget(auto_group)
        
        # 其他选项
        options_group = QGroupBox("选项")
        options_layout = QHBoxLayout()

        # 启用内存清理
        self.memory_checkbox = QCheckBox("启用内存清理")
        self.memory_checkbox.stateChanged.connect(self.toggle_memory_cleanup)
        options_layout.addWidget(self.memory_checkbox)
        
        # 暴力模式
        self.brute_mode_checkbox = QCheckBox("深度清理模式(调用Windows系统API)")
        self.brute_mode_checkbox.stateChanged.connect(self.toggle_brute_mode)
        self.brute_mode_checkbox.setToolTip("深度清理模式会使用Windows系统API清理所有进程的工作集，效率更高但更激进；\n"
                                           "不开启则会逐个进程分别清理工作集，相对温和但效率较低。")
        options_layout.addWidget(self.brute_mode_checkbox)
        
        options_group.setLayout(options_layout)
        memory_layout.addWidget(options_group)
        
        # 自定义配置选项
        custom_group = QGroupBox("自定义配置")
        custom_layout = QGridLayout()
        # 设置列间距
        custom_layout.setHorizontalSpacing(8)
        custom_layout.setVerticalSpacing(8)
        
        # 清理间隔设置
        interval_label = QLabel("清理间隔(秒):")
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimum(60)  # 最小1分钟
        self.interval_spinbox.setMaximum(3600)  # 最大1小时
        self.interval_spinbox.setSingleStep(30)  # 步长30秒
        self.interval_spinbox.setValue(300)  # 默认5分钟
        self.interval_spinbox.valueChanged.connect(self.update_clean_interval)
        self.interval_spinbox.setToolTip("定时清理的时间间隔，最小60秒")
        custom_layout.addWidget(interval_label, 0, 0)
        custom_layout.addWidget(self.interval_spinbox, 0, 1)
        
        # 在第一列QSpinBox后面添加弹簧
        custom_layout.setColumnStretch(2, 1)
        
        # 内存占用阈值设置
        threshold_label = QLabel("内存阈值(%):")
        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setMinimum(15)  # 最小30%
        self.threshold_spinbox.setMaximum(95)  # 最大95%
        self.threshold_spinbox.setSingleStep(5)  # 步长5%
        self.threshold_spinbox.setValue(80)  # 默认80%
        self.threshold_spinbox.valueChanged.connect(self.update_memory_threshold)
        self.threshold_spinbox.setToolTip("当内存使用率超过此阈值时触发清理")
        custom_layout.addWidget(threshold_label, 0, 3)
        custom_layout.addWidget(self.threshold_spinbox, 0, 4)
        
        # 在第二列QSpinBox后面添加弹簧
        custom_layout.setColumnStretch(5, 1)
        
        # 冷却时间设置
        cooldown_label = QLabel("冷却时间(秒):")
        self.cooldown_spinbox = QSpinBox()
        self.cooldown_spinbox.setMinimum(30)  # 最小30秒
        self.cooldown_spinbox.setMaximum(300)  # 最大5分钟
        self.cooldown_spinbox.setSingleStep(10)  # 步长10秒
        self.cooldown_spinbox.setValue(60)  # 默认60秒
        self.cooldown_spinbox.valueChanged.connect(self.update_cooldown_time)
        self.cooldown_spinbox.setToolTip("两次内存占用触发清理之间的最小时间间隔，防止短时间内频繁清理")
        custom_layout.addWidget(cooldown_label, 1, 0)
        custom_layout.addWidget(self.cooldown_spinbox, 1, 1)
        
        # 添加描述标签
        description_label = QLabel("⚠ 注意: 清理间隔不能小于1分钟，冷却时间用于防止短时间内重复触发清理")
        description_label.setWordWrap(True)
        StyleHelper.set_label_type(description_label, "warning")
        custom_layout.addWidget(description_label, 1, 3, 1, 3)
        
        custom_group.setLayout(custom_layout)
        memory_layout.addWidget(custom_group)
        
        # 手动清理按钮
        buttons_group = QGroupBox("手动清理")
        buttons_layout = QVBoxLayout()

        # 按钮水平布局
        btn_row_layout = QHBoxLayout()
        
        # 截取进程工作集按钮
        self.clean_workingset_btn = QPushButton("截取进程工作集")
        self.clean_workingset_btn.clicked.connect(self.manual_clean_workingset)
        btn_row_layout.addWidget(self.clean_workingset_btn)
        
        # 清理系统缓存按钮
        self.clean_syscache_btn = QPushButton("清理系统缓存")
        self.clean_syscache_btn.clicked.connect(self.manual_clean_syscache)
        btn_row_layout.addWidget(self.clean_syscache_btn)
        
        # 全面清理按钮
        self.clean_all_btn = QPushButton("执行全部已知清理(不推荐)")
        self.clean_all_btn.clicked.connect(self.manual_clean_all)
        btn_row_layout.addWidget(self.clean_all_btn)
        
        buttons_layout.addLayout(btn_row_layout)
        
        # 添加提示文本
        warning_label = QLabel("❗ 如果已经开启游戏不建议点击全部已知清理，否则清理时可能导致现有游戏卡死，或者清理后一段时间内游戏变卡")
        warning_label.setWordWrap(True)
        StyleHelper.set_label_type(warning_label, "error")
        buttons_layout.addWidget(warning_label)
        
        buttons_group.setLayout(buttons_layout)
        memory_layout.addWidget(buttons_group)
        
        # 添加状态显示
        memory_status = QGroupBox("内存状态")
        memory_status_layout = QVBoxLayout()
        
        # 创建内存信息标签
        self.memory_info_label = QLabel("加载中...")
        self.memory_info_label.setAlignment(Qt.AlignCenter)
        memory_status_layout.addWidget(self.memory_info_label)
        
        # 创建系统缓存信息标签
        self.cache_info_label = QLabel("系统缓存: 加载中...")
        self.cache_info_label.setAlignment(Qt.AlignCenter)
        memory_status_layout.addWidget(self.cache_info_label)
        
        # 创建配置信息标签
        self.config_info_label = QLabel("配置信息: 加载中...")
        self.config_info_label.setAlignment(Qt.AlignCenter)
        memory_status_layout.addWidget(self.config_info_label)
        
        # 创建内存使用进度条
        self.memory_progress = QProgressBar()
        self.memory_progress.setMinimum(0)
        self.memory_progress.setMaximum(100)
        self.memory_progress.setValue(0)
        memory_status_layout.addWidget(self.memory_progress)
        
        # 创建清理统计信息标签
        self.clean_stats_label = QLabel("清理统计: 暂无数据")
        self.clean_stats_label.setAlignment(Qt.AlignCenter)
        memory_status_layout.addWidget(self.clean_stats_label)
        
        memory_status.setLayout(memory_status_layout)
        memory_layout.addWidget(memory_status)
        
        # 填充剩余空间
        memory_layout.addStretch()
        
        # 设置选项卡
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        
        # 通知设置
        notify_group = QGroupBox("通知设置")
        notify_layout = QVBoxLayout()
        self.notify_checkbox = QCheckBox("启用Windows通知")
        self.notify_checkbox.stateChanged.connect(self.toggle_notifications)
        notify_layout.addWidget(self.notify_checkbox)
        notify_group.setLayout(notify_layout)
        settings_layout.addWidget(notify_group)
        
        # 启动设置
        startup_group = QGroupBox("启动设置")
        startup_layout = QVBoxLayout()
        self.startup_checkbox = QCheckBox("开机自启动")
        self.startup_checkbox.stateChanged.connect(self.toggle_auto_start)
        startup_layout.addWidget(self.startup_checkbox)
        startup_group.setLayout(startup_layout)
        settings_layout.addWidget(startup_group)
        
        # 窗口行为设置
        window_group = QGroupBox("窗口行为设置")
        window_layout = QVBoxLayout()
        
        # 关闭行为选择
        close_behavior_layout = QHBoxLayout()
        close_behavior_label = QLabel("关闭窗口时:")
        close_behavior_layout.addWidget(close_behavior_label)
        
        self.close_behavior_combo = QComboBox()
        self.close_behavior_combo.addItem("最小化到系统托盘", True)
        self.close_behavior_combo.addItem("直接退出程序", False)
        self.close_behavior_combo.currentIndexChanged.connect(self.on_close_behavior_changed)
        close_behavior_layout.addWidget(self.close_behavior_combo)
        
        close_behavior_layout.addStretch()
        window_layout.addLayout(close_behavior_layout)
        
        # 添加说明文本
        close_behavior_info = QLabel("💡 最小化到系统托盘：程序将继续在后台运行\n💡 直接退出程序：完全关闭程序进程")
        close_behavior_info.setWordWrap(True)
        StyleHelper.set_label_type(close_behavior_info, "info")
        window_layout.addWidget(close_behavior_info)
        
        window_group.setLayout(window_layout)
        settings_layout.addWidget(window_group)
        
        # 日志设置
        log_group = QGroupBox("日志设置")
        log_layout = QVBoxLayout()
        self.debug_checkbox = QCheckBox("启用调试模式")
        self.debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        log_layout.addWidget(self.debug_checkbox)
        log_group.setLayout(log_layout)
        settings_layout.addWidget(log_group)
        
        # 主题设置
        theme_group = QGroupBox("主题设置")
        theme_layout = QVBoxLayout()
        
        # 主题选择水平布局
        theme_buttons_layout = QHBoxLayout()
        theme_buttons_layout.setSpacing(8)  # 增加按钮间距
        
        # 浅色主题按钮
        self.light_theme_btn = QPushButton("☀️ 浅色模式")
        self.light_theme_btn.clicked.connect(lambda: self.switch_theme("light"))
        self.light_theme_btn.setToolTip("切换到浅色主题模式")
        self.light_theme_btn.setMinimumHeight(32)  # 增加按钮高度
        theme_buttons_layout.addWidget(self.light_theme_btn)
        
        # 深色主题按钮
        self.dark_theme_btn = QPushButton("🌙 深色模式")
        self.dark_theme_btn.clicked.connect(lambda: self.switch_theme("dark"))
        self.dark_theme_btn.setToolTip("切换到深色主题模式")
        self.dark_theme_btn.setMinimumHeight(32)
        theme_buttons_layout.addWidget(self.dark_theme_btn)
        
        theme_layout.addLayout(theme_buttons_layout)
        theme_group.setLayout(theme_layout)
        settings_layout.addWidget(theme_group)
        
        # 添加ACE服务管理功能
        service_group = QGroupBox("ACE服务管理")
        service_layout = QVBoxLayout()
        
        # 提醒文本
        warning_label = QLabel("⚠️ 警告：以下操作需要管理员权限，并会影响ACE反作弊服务")
        StyleHelper.set_label_type(warning_label, "error")
        service_layout.addWidget(warning_label)
        
        # 创建按钮布局
        service_buttons_layout = QHBoxLayout()
        
        # 开启反作弊程序按钮
        self.start_ace_btn = QPushButton("开启反作弊程序")
        self.start_ace_btn.setToolTip("执行启动ACE反作弊程序命令")
        self.start_ace_btn.clicked.connect(self.start_ace_program)
        service_buttons_layout.addWidget(self.start_ace_btn)
        
        # 卸载ACE程序按钮
        self.uninstall_ace_btn = QPushButton("卸载反作弊程序")
        self.uninstall_ace_btn.setToolTip("执行ACE反作弊程序卸载命令")
        self.uninstall_ace_btn.clicked.connect(self.uninstall_ace_program)
        service_buttons_layout.addWidget(self.uninstall_ace_btn)
        
        # 停止ACE服务按钮
        self.stop_service_btn = QPushButton("停止ACE服务")
        self.stop_service_btn.setToolTip("停止ACE-GAME、ACE-BASE、AntiCheatExpert Service、AntiCheatExpert Protection服务")
        self.stop_service_btn.clicked.connect(self.stop_ace_services)
        service_buttons_layout.addWidget(self.stop_service_btn)
        
        # 删除ACE服务按钮
        self.delete_service_btn = QPushButton("删除ACE服务")
        self.delete_service_btn.setToolTip("删除ACE-GAME、ACE-BASE、AntiCheatExpert Service、AntiCheatExpert Protection服务")
        self.delete_service_btn.clicked.connect(self.delete_ace_services)
        service_buttons_layout.addWidget(self.delete_service_btn)
        
        service_layout.addLayout(service_buttons_layout)
        
        service_group.setLayout(service_layout)
        settings_layout.addWidget(service_group)
        
        # 添加操作按钮
        actions_group = QGroupBox("操作")
        actions_layout = QHBoxLayout()
        
        # 打开配置目录按钮
        self.config_dir_btn = QPushButton("打开配置目录")
        self.config_dir_btn.clicked.connect(self.open_config_dir)
        actions_layout.addWidget(self.config_dir_btn)
        
        # 检查更新按钮
        self.check_update_btn = QPushButton("检查更新")
        self.check_update_btn.clicked.connect(self.check_update)
        actions_layout.addWidget(self.check_update_btn)
        
        # 关于按钮
        self.about_btn = QPushButton("关于")
        self.about_btn.clicked.connect(self.show_about)
        actions_layout.addWidget(self.about_btn)
        
        actions_group.setLayout(actions_layout)
        settings_layout.addWidget(actions_group)
        
        # 版本信息显示
        version_group = QGroupBox("版本信息")
        version_layout = QVBoxLayout()
        
        # 获取当前版本号
        current_version = get_current_version()
        self.version_label = QLabel(f"当前版本: v{current_version}")
        self.version_label.setAlignment(Qt.AlignCenter)
        StyleHelper.set_label_type(self.version_label, "info")
        version_layout.addWidget(self.version_label)
        
        version_group.setLayout(version_layout)
        settings_layout.addWidget(version_group)
        
        # 添加空白占位
        settings_layout.addStretch()
        
        # 添加选项卡
        self.tabs.addTab(status_tab, "  程序状态  ")
        self.tabs.addTab(process_tab, "  进程监控  ")
        self.tabs.addTab(memory_tab, "  内存清理  ")
        self.tabs.addTab(settings_tab, "  设置  ")
    
    def setup_tray(self):
        """设置系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(self.icon_path))

        # 创建托盘菜单
        tray_menu = QMenu()
        
        # 显示主窗口动作
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        tray_menu.addAction(show_action)
        
        # 显示状态动作
        status_action = QAction("显示状态", self)
        status_action.triggered.connect(self.show_status)
        tray_menu.addAction(status_action)
        
        tray_menu.addSeparator()
        
        # 启用通知动作
        self.notify_action = QAction("启用通知", self)
        self.notify_action.setCheckable(True)
        self.notify_action.triggered.connect(self.toggle_notifications_from_tray)
        tray_menu.addAction(self.notify_action)
        
        # 开机自启动动作
        self.startup_action = QAction("开机自启动", self)
        self.startup_action.setCheckable(True)
        self.startup_action.triggered.connect(self.toggle_auto_start_from_tray)
        tray_menu.addAction(self.startup_action)
        
        # 进程监控菜单项
        self.monitor_action = QAction("启用ACE弹窗监控", self)
        self.monitor_action.setCheckable(True)
        self.monitor_action.setChecked(self.monitor.running)
        self.monitor_action.triggered.connect(self.toggle_process_monitor_from_tray)
        tray_menu.addAction(self.monitor_action)
        
        tray_menu.addSeparator()

        # 主题切换子菜单
        theme_menu = QMenu("主题设置")
        
        # 浅色主题动作
        light_theme_action = QAction("浅色", self)
        light_theme_action.triggered.connect(lambda: self.switch_theme("light"))
        theme_menu.addAction(light_theme_action)
        
        # 深色主题动作
        dark_theme_action = QAction("深色", self)
        dark_theme_action.triggered.connect(lambda: self.switch_theme("dark"))
        theme_menu.addAction(dark_theme_action)
        
        tray_menu.addMenu(theme_menu)
        
        tray_menu.addSeparator()
        
        # 内存清理子菜单
        memory_menu = QMenu("内存清理")
        
        # 截取进程工作集动作
        clean_workingset_action = QAction("截取进程工作集", self)
        clean_workingset_action.triggered.connect(self.manual_clean_workingset)
        memory_menu.addAction(clean_workingset_action)
        
        # 清理系统缓存动作
        clean_syscache_action = QAction("清理系统缓存", self)
        clean_syscache_action.triggered.connect(self.manual_clean_syscache)
        memory_menu.addAction(clean_syscache_action)
        
        # 执行全部已知清理动作
        clean_all_action = QAction("执行全部已知清理(不推荐)", self)
        clean_all_action.triggered.connect(self.manual_clean_all)
        memory_menu.addAction(clean_all_action)
        
        tray_menu.addMenu(memory_menu)
        
        tray_menu.addSeparator()
        
        # 打开配置目录动作
        config_dir_action = QAction("打开配置目录", self)
        config_dir_action.triggered.connect(self.open_config_dir)
        tray_menu.addAction(config_dir_action)
        
        tray_menu.addSeparator()
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
        tray_menu.addSeparator()

        # 打开官网动作
        open_website_action = QAction("梯子加速官网", self)
        open_website_action.triggered.connect(lambda: webbrowser.open("https://ktcat.su"))
        tray_menu.addAction(open_website_action)

        tray_menu.addSeparator()

        # 退出动作
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.confirm_exit)
        tray_menu.addAction(exit_action)

    @Slot(str)
    def switch_theme(self, theme):
        """
        切换应用程序主题
        
        Args:
            theme: 主题类型，可以是 "light" 或 "dark"
        """
        if theme != self.current_theme:
            self.current_theme = theme
            
            # 保存主题设置到配置文件
            self.monitor.config_manager.theme = theme
            if self.monitor.config_manager.save_config():
                logger.debug(f"主题设置已保存到配置文件: {theme}")
            else:
                logger.warning(f"主题设置保存失败: {theme}")
            
            # 使用指定主题
            theme_manager.set_theme(theme)
            logger.debug(f"主题已设置为: {theme}")
            
            # 主题切换现在通过信号自动完成，只需要应用组件属性
            self.apply_component_properties()
            
            # 立即更新状态显示
            self.update_status()
    
    def apply_component_properties(self):
        """应用组件属性"""
        try:
            # 设置无边框窗口透明背景属性
            StyleHelper.set_frameless_window_properties(self)
            
            # 设置选项卡透明背景
            if hasattr(self, 'tabs'):
                StyleHelper.set_tab_page_transparent(self.tabs)
            
            # 设置按钮类型属性
            self.setup_button_properties()
            
            # 设置标签类型属性
            self.setup_label_properties()
            
            # 设置进度条类型属性
            self.setup_progress_properties()
            
            # 重新绘制窗口以应用新主题
            self.update()
            
            # 重新应用圆角遮罩
            self.apply_rounded_mask()
            
        except Exception as e:
            logger.error(f"应用组件属性失败: {str(e)}")
    
    def setup_button_properties(self):
        """设置按钮属性"""
        try:
            # 主要功能按钮
            if hasattr(self, 'process_manager_btn'):
                StyleHelper.set_button_type(self.process_manager_btn, "primary")
            if hasattr(self, 'optimize_anticheat_btn'):
                StyleHelper.set_button_type(self.optimize_anticheat_btn, "success")
            if hasattr(self, 'manage_io_list_btn'):
                StyleHelper.set_button_type(self.manage_io_list_btn, "default")
            
            # 内存清理按钮
            if hasattr(self, 'clean_workingset_btn'):
                StyleHelper.set_button_type(self.clean_workingset_btn, "primary")
            if hasattr(self, 'clean_syscache_btn'):
                StyleHelper.set_button_type(self.clean_syscache_btn, "primary")
            if hasattr(self, 'clean_all_btn'):
                StyleHelper.set_button_type(self.clean_all_btn, "warning")
            
            # 设置按钮
            if hasattr(self, 'config_dir_btn'):
                StyleHelper.set_button_type(self.config_dir_btn, "default")
            if hasattr(self, 'check_update_btn'):
                StyleHelper.set_button_type(self.check_update_btn, "default")
            if hasattr(self, 'about_btn'):
                StyleHelper.set_button_type(self.about_btn, "default")
            
            # 主题切换按钮
            if hasattr(self, 'light_theme_btn'):
                btn_type = "selected" if self.current_theme == "light" else "default"
                StyleHelper.set_button_type(self.light_theme_btn, btn_type)
            if hasattr(self, 'dark_theme_btn'):
                btn_type = "selected" if self.current_theme == "dark" else "default"
                StyleHelper.set_button_type(self.dark_theme_btn, btn_type)
            
            # 服务管理按钮
            if hasattr(self, 'start_ace_btn'):
                StyleHelper.set_button_type(self.start_ace_btn, "success")
            if hasattr(self, 'uninstall_ace_btn'):
                StyleHelper.set_button_type(self.uninstall_ace_btn, "warning")
            if hasattr(self, 'stop_service_btn'):
                StyleHelper.set_button_type(self.stop_service_btn, "warning")
            if hasattr(self, 'delete_service_btn'):
                StyleHelper.set_button_type(self.delete_service_btn, "danger")
                
        except Exception as e:
            logger.error(f"设置按钮属性失败: {str(e)}")
    
    def setup_label_properties(self):
        """设置标签属性"""
        try:
            # 重新应用主题状态标签的样式
            if hasattr(self, 'current_theme_label'):
                theme_name = "浅色" if self.current_theme == "light" else "深色"
                icon = "☀️" if self.current_theme == "light" else "🌙"
                status_text = f"{icon} 当前状态：{theme_name}主题"
                label_type = "success" if self.current_theme == "light" else "info"
                
                self.current_theme_label.setText(status_text)
                StyleHelper.set_label_type(self.current_theme_label, label_type)
                    
        except Exception as e:
            logger.error(f"设置标签属性失败: {str(e)}")
    
    def setup_progress_properties(self):
        """设置进度条属性"""
        try:
            # 内存进度条将在update_memory_status方法中动态设置
            pass
        except Exception as e:
            logger.error(f"设置进度条属性失败: {str(e)}")
    
    def get_status_html(self):
        """获取HTML格式的状态信息"""
        if not self.monitor:
            return "<p>程序未启动</p>"
        
        # 使用新的状态HTML生成器
        style = StatusHTMLGenerator.get_html_style()
        
        html = [style]
        
        # 主状态卡片
        html.append('<div class="card">')
        html.append('<div class="section-title">程序状态</div>')
        
        # 监控程序状态
        if self.monitor.running:
            html.append('<p class="status-item"><span class="status-success">🟩 监控程序运行中</span></p>')
        else:
            html.append('<p class="status-item"><span class="status-error">🟥 监控程序已停止</span></p>')
        
        html.append('</div>')
        
        # 进程状态卡片
        html.append('<div class="card">')
        html.append('<div class="section-title">进程状态</div>')
        
        # ACE进程状态(ACE反作弊程序是否安装提示弹窗)
        ace_running = self.monitor.is_process_running(self.monitor.anticheat_name) is not None
        
        if ace_running and self.monitor.anticheat_killed:
            html.append('<p class="status-item">✅ ACE-Tray进程: <span class="status-success">已被终止</span>  (反作弊安装弹窗进程)</p>')
        elif ace_running:
            html.append('<p class="status-item">🔄 ACE-Tray进程: <span class="status-warning">正在处理</span>  (反作弊安装弹窗进程)</p>')
        else:
            html.append('<p class="status-item">ℹ️ ACE-Tray进程: <span class="status-normal">未处理</span>  (反作弊安装弹窗进程)</p>')
        
        # SGuard64进程状态
        scan_running = self.monitor.is_process_running(self.monitor.scanprocess_name) is not None
        
        # 如果进程在运行，直接检查其优化状态并更新全局标志
        if scan_running:
            # 直接检查当前进程的真实优化状态
            _, is_optimized = self.monitor.check_process_status(self.monitor.scanprocess_name)
            # 强制更新全局状态标志
            self.monitor.scanprocess_optimized = is_optimized
            
            if self.monitor.scanprocess_optimized:
                html.append('<p class="status-item">✅ SGuard64进程: <span class="status-success">已被优化</span>  (反作弊扫盘进程)</p>')
            else:
                html.append('<p class="status-item">🔄 SGuard64进程: <span class="status-warning">正在运行 (未优化)</span>  (反作弊扫盘进程)</p>')
        else:
            html.append('<p class="status-item">⚠️ SGuard64进程: <span class="status-error">未在运行</span>  (反作弊扫盘进程)</p>')
        html.append('</div>')
        
        # 反作弊服务状态
        html.append('<div class="card">')
        html.append('<div class="section-title">反作弊服务状态</div>')
        
        # 获取所有反作弊服务的状态
        service_results = self.monitor.monitor_anticheat_service()
        
        # 显示每个服务的状态
        for service_name, service_info in service_results.items():
            service_exists = service_info["exists"]
            status = service_info["status"]
            start_type = service_info["start_type"]
            
            if service_exists:
                if status == 'running':
                    html.append(f'<p class="status-item">✅ {service_name}: <span class="status-success">正在运行</span></p>')
                elif status == 'stopped':
                    html.append(f'<p class="status-item">⚠️ {service_name}: <span class="status-error">已停止</span></p>')
                else:
                    html.append(f'<p class="status-item">ℹ️ {service_name}: <span class="status-normal">{status}</span></p>')
                
                # 服务启动类型
                if start_type == 'auto':
                    html.append(f'<p class="status-item">⚙️ {service_name}启动类型: <span class="status-success">自动启动</span></p>')
                elif start_type == 'disabled':
                    html.append(f'<p class="status-item">⚙️ {service_name}启动类型: <span class="status-error">已禁用</span></p>')
                elif start_type == 'manual':
                    html.append(f'<p class="status-item">⚙️ {service_name}启动类型: <span class="status-normal">手动</span></p>')
                else:
                    html.append(f'<p class="status-item">⚙️ {service_name}启动类型: <span class="status-normal">{start_type}</span></p>')
            else:
                html.append(f'<p class="status-item">❓ {service_name}: <span class="status-disabled">未找到</span></p>')
        
        html.append('</div>')
        
        # 内存状态卡片
        html.append('<div class="card">')
        html.append('<div class="section-title">内存状态</div>')
        
        if self.memory_cleaner.running:
            mem_info = self.memory_cleaner.get_memory_info()
            if mem_info:
                used_percent = mem_info['percent']
                used_gb = mem_info['used'] / (1024**3)
                total_gb = mem_info['total'] / (1024**3)
                
                # 根据内存使用率设置颜色
                bar_color = "#2ecc71"  # 绿色（低）
                status_class = "status-success"
                if used_percent >= 80:
                    bar_color = "#e74c3c"  # 红色（高）
                    status_class = "status-error" 
                elif used_percent >= 60:
                    bar_color = "#f39c12"  # 橙色（中）
                    status_class = "status-warning"
                
                html.append(f'<p class="status-item">🛡️ 内存清理: <span class="status-success">已启用</span></p>')
                html.append(f'<p class="status-item">🍋‍🟩 内存使用: <span class="{status_class}">{used_percent:.1f}%</span> ({used_gb:.1f}GB / {total_gb:.1f}GB)</p>')
                
                # 添加自定义清理配置信息
                html.append(f'<p class="status-item">⏱️ 清理间隔: <span class="status-normal">{self.memory_cleaner.clean_interval}秒</span></p>')
                html.append(f'<p class="status-item">📊 触发阈值: <span class="status-normal">{self.memory_cleaner.threshold}%</span></p>')
                html.append(f'<p class="status-item">⏲️ 冷却时间: <span class="status-normal">{self.memory_cleaner.cooldown_time}秒</span></p>')
                
                # 系统缓存信息
                cache_info = self.memory_cleaner.get_system_cache_info()
                if cache_info:
                    cache_size = cache_info['current_size'] / (1024**3)
                    peak_size = cache_info['peak_size'] / (1024**3)
                    html.append(f'<p class="status-item">💾 系统缓存: <span class="status-normal">{cache_size:.1f}GB</span> (峰值: {peak_size:.1f}GB)</p>')
            else:
                html.append('<p class="status-item">🧠 内存清理: <span class="status-success">已启用</span></p>')
                html.append('<p class="status-item">无法获取内存信息</p>')
        else:
            html.append('<p class="status-item">🧠 内存清理: <span class="status-disabled">已禁用</span></p>')
        
        html.append('</div>')
        
        # 系统设置卡片
        html.append('<div class="card">')
        html.append('<div class="section-title">系统设置</div>')
        
        # 通知状态
        notification_class = "status-success" if self.monitor.config_manager.show_notifications else "status-disabled"
        notification_text = "已启用" if self.monitor.config_manager.show_notifications else "已禁用"
        html.append(f'<p class="status-item">🔔 通知功能: <span class="{notification_class}" style="font-weight: bold;">{notification_text}</span></p>')
        
        # 自启动状态
        autostart_class = "status-success" if self.monitor.config_manager.auto_start else "status-disabled"
        autostart_text = "已启用" if self.monitor.config_manager.auto_start else "已禁用"
        html.append(f'<p class="status-item">🔁 开机自启: <span class="{autostart_class}" style="font-weight: bold;">{autostart_text}</span></p>')
        
        # 关闭行为状态
        close_behavior_text = "最小化到后台" if self.monitor.config_manager.close_to_tray else "直接退出程序"
        close_behavior_class = "status-normal"
        html.append(f'<p class="status-item">🪟 关闭行为: <span class="{close_behavior_class}" style="font-weight: bold;">{close_behavior_text}</span></p>')
        
        # 调试模式状态
        debug_class = "status-success" if self.monitor.config_manager.debug_mode else "status-disabled"
        debug_text = "已启用" if self.monitor.config_manager.debug_mode else "已禁用"
        html.append(f'<p class="status-item">🐛 调试模式: <span class="{debug_class}" style="font-weight: bold;">{debug_text}</span></p>')
        
        # 主题状态
        html.append(f'<p class="status-item">🎨 当前主题: <span class="status-normal" style="font-weight: bold;">{self._get_theme_display_name()}</span></p>')
        
        html.append('</div>')
        
        # 添加更新时间
        import datetime
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html.append(f'<p class="update-time">更新时间: {current_time}</p>')
        
        return "".join(html)
    
    def _get_theme_display_name(self):
        """获取主题的显示名称"""
        if self.current_theme == "light":
            return "浅色"
        else:  # dark
            return "深色"
    
    def load_settings(self):
        """加载设置到UI"""
        # 阻塞信号避免双重触发
        self.blockSignals(True)
        
        # 更新通知设置
        self.notify_checkbox.setChecked(self.monitor.config_manager.show_notifications)
        self.notify_action.setChecked(self.monitor.config_manager.show_notifications)
        
        # 更新自启动设置
        self.startup_checkbox.setChecked(self.monitor.config_manager.auto_start)
        self.startup_action.setChecked(self.monitor.config_manager.auto_start)
        
        # 更新监控状态设置（从配置管理器加载）
        monitor_enabled = self.monitor.config_manager.monitor_enabled
        self.monitor_checkbox.setChecked(monitor_enabled)
        self.monitor_action.setChecked(monitor_enabled)
        
        # 根据配置启动或停止监控
        if monitor_enabled and not self.monitor.running:
            self.monitor.running = True
            self.monitor.start_monitors()
            logger.debug("根据配置启动监控程序")
        elif not monitor_enabled and self.monitor.running:
            self.monitor.running = False
            self.monitor.stop_monitors()
            self.monitor.anticheat_killed = False
            self.monitor.scanprocess_optimized = False
            logger.debug("根据配置停止监控程序")
        
        # 更新调试模式设置
        self.debug_checkbox.setChecked(self.monitor.config_manager.debug_mode)
        
        # 更新关闭行为设置
        # 根据配置值设置下拉框选择
        close_to_tray = self.monitor.config_manager.close_to_tray
        for i in range(self.close_behavior_combo.count()):
            if self.close_behavior_combo.itemData(i) == close_to_tray:
                self.close_behavior_combo.setCurrentIndex(i)
                break
        
        # 加载内存清理设置
        # 使用配置中的enabled属性设置复选框状态
        self.memory_checkbox.setChecked(self.memory_cleaner.enabled)
        
        # 如果enabled为true但未运行，则启动内存清理线程
        if self.memory_cleaner.enabled and not self.memory_cleaner.running:
            self.memory_cleaner.start_cleaner_thread()
        
        # 加载暴力模式设置
        self.brute_mode_checkbox.setChecked(self.memory_cleaner.brute_mode)
        
        # 加载自定义配置设置
        self.interval_spinbox.setValue(self.memory_cleaner.clean_interval)
        self.threshold_spinbox.setValue(self.memory_cleaner.threshold)
        self.cooldown_spinbox.setValue(self.memory_cleaner.cooldown_time)
        
        # 更新清理选项标签文本
        self.clean_option1.setText(f"定时清理(每{self.memory_cleaner.clean_interval}秒)，截取进程工作集")
        self.clean_option2.setText(f"定时清理(每{self.memory_cleaner.clean_interval}秒)，清理系统缓存")
        self.clean_option3.setText(f"定时清理(每{self.memory_cleaner.clean_interval}秒)，用全部可能的方法清理内存")
        self.clean_option4.setText(f"若内存使用量超出{self.memory_cleaner.threshold}%，截取进程工作集")
        self.clean_option5.setText(f"若内存使用量超出{self.memory_cleaner.threshold}%，清理系统缓存")
        self.clean_option6.setText(f"若内存使用量超出{self.memory_cleaner.threshold}%，用全部可能的方法清理内存")
        
        # 加载清理选项设置
        self.clean_option1.setChecked(self.memory_cleaner.clean_switches[0])
        self.clean_option2.setChecked(self.memory_cleaner.clean_switches[1])
        self.clean_option3.setChecked(self.memory_cleaner.clean_switches[2])
        self.clean_option4.setChecked(self.memory_cleaner.clean_switches[3])
        self.clean_option5.setChecked(self.memory_cleaner.clean_switches[4])
        self.clean_option6.setChecked(self.memory_cleaner.clean_switches[5])
        
        self.update_status()
        self.blockSignals(False)
    
    def update_status(self):
        """更新状态信息"""
        if not self.monitor:
            self.status_label.setText("<p>程序未启动</p>")
            return
            
        # 获取状态HTML
        status_html = self.get_status_html()
        
        # 设置状态文本
        self.status_label.setText(status_html)
        
        # 更新内存信息显示
        self.update_memory_status()
        
        # 更新托盘图标提示
        if self.tray_icon:
            mem_info = self.memory_cleaner.get_memory_info() if self.memory_cleaner.running else None
            mem_usage = f" - 内存: {mem_info['percent']:.1f}%" if mem_info else ""
            self.tray_icon.setToolTip(f"ACE-KILLER - {'运行中' if self.monitor.running else '已停止'}{mem_usage}")
    
    def update_memory_status(self):
        """更新内存状态显示"""
        # 更新内存信息
        mem_info = self.memory_cleaner.get_memory_info()
        
        if not mem_info:
            self.memory_info_label.setText("无法获取内存信息")
            self.cache_info_label.setText("系统缓存: 无法获取信息")
            self.config_info_label.setText("配置信息: 无法获取信息")
            self.clean_stats_label.setText("清理统计: 暂无数据")
            self.memory_progress.setValue(0)
            return
            
        used_percent = mem_info['percent']
        used_gb = mem_info['used'] / (1024**3)
        total_gb = mem_info['total'] / (1024**3)
        
        # 获取系统缓存信息
        cache_info = self.memory_cleaner.get_system_cache_info()
        
        # 更新标签文本
        self.memory_info_label.setText(f"物理内存: {used_gb:.1f}GB / {total_gb:.1f}GB ({used_percent:.1f}%)")
        
        # 更新缓存信息标签
        if cache_info:
            cache_size_gb = cache_info['current_size'] / (1024**3)
            cache_peak_gb = cache_info['peak_size'] / (1024**3)
            cache_percent = (cache_size_gb / total_gb) * 100 if total_gb > 0 else 0
            self.cache_info_label.setText(f"系统缓存: 当前 {cache_size_gb:.1f}GB ({cache_percent:.1f}%) | 峰值 {cache_peak_gb:.1f}GB")
            
            # 根据缓存占用设置标签类型
            if cache_percent > 30:
                StyleHelper.set_label_type(self.cache_info_label, "error")
            elif cache_percent > 20:
                StyleHelper.set_label_type(self.cache_info_label, "warning")
            else:
                # 清除标签类型，使用默认样式
                self.cache_info_label.setProperty("labelType", None)
                self.cache_info_label.style().unpolish(self.cache_info_label)
                self.cache_info_label.style().polish(self.cache_info_label)
        else:
            self.cache_info_label.setText("系统缓存: 无法获取信息")
            # 清除标签类型，使用默认样式
            self.cache_info_label.setProperty("labelType", None)
            self.cache_info_label.style().unpolish(self.cache_info_label)
            self.cache_info_label.style().polish(self.cache_info_label)
        
        # 更新配置信息标签
        config_text = (f"配置: 清理间隔 {self.memory_cleaner.clean_interval}秒 | "
                      f"触发阈值 {self.memory_cleaner.threshold}% | "
                      f"冷却时间 {self.memory_cleaner.cooldown_time}秒")
        self.config_info_label.setText(config_text)
        
        # 更新进度条
        self.memory_progress.setValue(int(used_percent))
        
        # 根据内存使用率设置进度条类型
        if used_percent >= 80:
            StyleHelper.set_progress_type(self.memory_progress, "memory-high")
        elif used_percent >= 60:
            StyleHelper.set_progress_type(self.memory_progress, "memory-medium")
        else:
            StyleHelper.set_progress_type(self.memory_progress, "memory-low")
            
        # 更新清理统计信息
        stats = self.memory_cleaner.get_clean_stats()
        stats_text = (f"累计释放: {stats['total_cleaned_mb']:.2f}MB | "
                     f"上次释放: {stats['last_cleaned_mb']:.2f}MB | "
                     f"清理次数: {stats['clean_count']} | "
                     f"最后清理: {stats['last_clean_time']}")
        self.clean_stats_label.setText(stats_text)
    
    def _toggle_notifications(self, from_tray=False):
        """通用通知切换方法"""
        if from_tray:
            self.monitor.config_manager.show_notifications = self.notify_action.isChecked()
            # 同步更新主窗口选项
            self.notify_checkbox.blockSignals(True)
            self.notify_checkbox.setChecked(self.monitor.config_manager.show_notifications)
            self.notify_checkbox.blockSignals(False)
        else:
            self.monitor.config_manager.show_notifications = self.notify_checkbox.isChecked()
            # 同步更新托盘菜单选项
            self.notify_action.blockSignals(True)
            self.notify_action.setChecked(self.monitor.config_manager.show_notifications)
            self.notify_action.blockSignals(False)
        
        # 保存配置
        if self.monitor.config_manager.save_config():
            logger.debug(f"通知状态已更改并保存: {'开启' if self.monitor.config_manager.show_notifications else '关闭'}")
        else:
            logger.warning(f"通知状态已更改但保存失败: {'开启' if self.monitor.config_manager.show_notifications else '关闭'}")
        
        # 立即更新状态显示
        self.update_status()
    
    @Slot()
    def toggle_notifications(self):
        """切换通知开关"""
        self._toggle_notifications(from_tray=False)
    
    @Slot()
    def toggle_notifications_from_tray(self):
        """从托盘菜单切换通知开关"""
        self._toggle_notifications(from_tray=True)
    
    def _toggle_auto_start(self, from_tray=False):
        """通用自启动切换方法"""
        if from_tray:
            self.monitor.config_manager.auto_start = self.startup_action.isChecked()
            # 同步更新主窗口选项
            self.startup_checkbox.blockSignals(True)
            self.startup_checkbox.setChecked(self.monitor.config_manager.auto_start)
            self.startup_checkbox.blockSignals(False)
        else:
            self.monitor.config_manager.auto_start = self.startup_checkbox.isChecked()
            # 同步更新托盘菜单选项
            self.startup_action.blockSignals(True)
            self.startup_action.setChecked(self.monitor.config_manager.auto_start)
            self.startup_action.blockSignals(False)
        
        # 修改注册表
        if self.monitor.config_manager.auto_start:
            enable_auto_start()
        else:
            disable_auto_start()
        
        # 保存配置
        if self.monitor.config_manager.save_config():
            logger.debug(f"开机自启状态已更改并保存: {'开启' if self.monitor.config_manager.auto_start else '关闭'}")
        else:
            logger.warning(f"开机自启状态已更改但保存失败: {'开启' if self.monitor.config_manager.auto_start else '关闭'}")
        
        # 立即更新状态显示
        self.update_status()
    
    @Slot()
    def toggle_auto_start(self):
        """切换开机自启动开关"""
        self._toggle_auto_start(from_tray=False)
    
    @Slot()
    def toggle_auto_start_from_tray(self):
        """从托盘菜单切换开机自启动开关"""
        self._toggle_auto_start(from_tray=True)
    
    def _toggle_process_monitor(self, from_tray=False):
        """通用进程监控切换方法"""
        enabled = self.monitor_action.isChecked() if from_tray else self.monitor_checkbox.isChecked()
        
        if enabled:
            self.monitor.running = True
            self.monitor.start_monitors()
            logger.debug("监控程序已启动")
        else:
            self.monitor.running = False
            self.monitor.stop_monitors()
            self.monitor.anticheat_killed = False
            self.monitor.scanprocess_optimized = False
            logger.debug("监控程序已停止")
        
        # 保存监控状态到配置管理器
        self.monitor.config_manager.monitor_enabled = enabled
        
        # 同步界面状态
        if from_tray:
            # 同步主窗口状态
            self.monitor_checkbox.blockSignals(True)
            self.monitor_checkbox.setChecked(enabled)
            self.monitor_checkbox.blockSignals(False)
        else:
            # 同步托盘菜单状态
            self.monitor_action.blockSignals(True)
            self.monitor_action.setChecked(enabled)
            self.monitor_action.blockSignals(False)
        
        # 保存配置
        if self.monitor.config_manager.save_config():
            logger.debug(f"监控状态已更改并保存: {'开启' if enabled else '关闭'}")
        else:
            logger.warning(f"监控状态已更改但保存失败: {'开启' if enabled else '关闭'}")
        
        # 立即更新状态显示
        self.update_status()
    
    @Slot()
    def toggle_process_monitor(self):
        """切换进程监控开关"""
        self._toggle_process_monitor(from_tray=False)
    
    @Slot()
    def toggle_process_monitor_from_tray(self):
        """从托盘菜单切换进程监控开关"""
        self._toggle_process_monitor(from_tray=True)
    
    @Slot()
    def open_config_dir(self):
        """打开配置目录"""
        try:
            if os.path.exists(self.monitor.config_manager.config_dir):
                if sys.platform == 'win32':
                    os.startfile(self.monitor.config_manager.config_dir)
                else:
                    import subprocess
                    subprocess.Popen(['xdg-open', self.monitor.config_manager.config_dir])
                logger.debug(f"已打开配置目录: {self.monitor.config_manager.config_dir}")
            else:
                os.makedirs(self.monitor.config_manager.config_dir, exist_ok=True)
                if sys.platform == 'win32':
                    os.startfile(self.monitor.config_manager.config_dir)
                else:
                    import subprocess
                    subprocess.Popen(['xdg-open', self.monitor.config_manager.config_dir])
                logger.debug(f"已创建并打开配置目录: {self.monitor.config_manager.config_dir}")
        except Exception as e:
            logger.error(f"打开配置目录失败: {str(e)}")
            QMessageBox.warning(self, "错误", f"打开配置目录失败: {str(e)}")
    
    @Slot()
    def check_update(self):
        """检查更新"""
        # 显示正在检查的消息
        self.check_update_btn.setText("检查中...")
        self.check_update_btn.setEnabled(False)
        
        # 异步检查更新
        self.version_checker.check_for_updates_async()
    
    @Slot(bool, str, str, str, str)
    def _on_version_check_finished(self, has_update, current_ver, latest_ver, update_info_str, error_msg):
        """版本检查完成的处理函数"""
        # 恢复按钮状态
        self.check_update_btn.setText("检查更新")
        self.check_update_btn.setEnabled(True)
        
        # 更新版本显示标签
        if has_update and latest_ver:
            self.version_label.setText(f"当前版本: v{current_ver} | 最新版本: v{latest_ver} 🆕")
            StyleHelper.set_label_type(self.version_label, "warning")
        else:
            self.version_label.setText(f"当前版本: v{current_ver}")
            StyleHelper.set_label_type(self.version_label, "info")
        
        # 创建并显示消息
        result = create_update_message(
            has_update, current_ver, latest_ver, update_info_str, error_msg
        )
        
        # 解包结果
        title, message, msg_type, extra_data = result
        
        import webbrowser
        
        if msg_type == "error":
            # 其他错误消息，询问是否手动访问GitHub
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle(title)
            msg_box.setText(message)
            
            # 添加自定义按钮
            get_version_btn = msg_box.addButton("🌐 前往下载页面", QMessageBox.YesRole)
            cancel_btn = msg_box.addButton("❌ 关闭", QMessageBox.NoRole)
            msg_box.setDefaultButton(cancel_btn)
            
            msg_box.exec()
            if msg_box.clickedButton() == get_version_btn:
                github_url = extra_data.get('github_url', 'https://github.com/tools5/ACE-KILLER/releases')
                webbrowser.open(github_url)
                
        elif msg_type == "update":
            # 有新版本，询问是否前往下载
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle(title)
            msg_box.setText(message)
            
            # 根据是否为直接下载调整按钮配置
            is_direct_download = extra_data.get('is_direct_download', False)
            if is_direct_download:
                # 有直接下载链接时，提供加速镜像和源地址两个选项
                mirror_btn = msg_box.addButton("🚀 国内加速下载", QMessageBox.AcceptRole)
                direct_btn = msg_box.addButton("🌐 源地址下载", QMessageBox.ActionRole)
                cancel_btn = msg_box.addButton("❌ 关闭", QMessageBox.RejectRole)
                msg_box.setDefaultButton(mirror_btn)
            else:
                # 没有直接下载链接时，只提供页面跳转
                download_btn = msg_box.addButton("🌐 前往下载页面", QMessageBox.AcceptRole)
                cancel_btn = msg_box.addButton("❌ 关闭", QMessageBox.RejectRole)
                msg_box.setDefaultButton(download_btn)
            
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            
            # 处理下载按钮点击
            download_url = extra_data.get('download_url')
            should_download = False
            final_download_url = None
            
            if is_direct_download:
                # 有直接下载链接的情况
                if clicked_button == mirror_btn:
                    # 国内加速镜像下载
                    should_download = True
                    final_download_url = f"https://ghfast.top/{download_url}" if download_url else None
                elif clicked_button == direct_btn:
                    # 源地址下载
                    should_download = True
                    final_download_url = download_url
            else:
                # 没有直接下载链接的情况
                if clicked_button == download_btn:
                    should_download = True
                    final_download_url = download_url
            
            # 执行下载
            if should_download and final_download_url:
                import subprocess
                import os
                try:
                    # 在Windows上使用默认浏览器下载
                    if os.name == 'nt':
                        os.startfile(final_download_url)
                    else:
                        # 其他系统使用webbrowser
                        webbrowser.open(final_download_url)
                    
                except Exception as e:
                    logger.error(f"启动下载失败: {str(e)}")
                    # 回退到浏览器打开
                    webbrowser.open(final_download_url)
            elif should_download:
                # 备用方案：打开发布页面
                import json
                try:
                    update_info = json.loads(update_info_str)
                    release_url = update_info.get('url', 'https://github.com/cassianvale/ACE-KILLER/releases/latest')
                    webbrowser.open(release_url)
                except:
                    webbrowser.open("https://github.com/cassianvale/ACE-KILLER/releases/latest")
                    
        else:
            QMessageBox.information(self, title, message)
    
    @Slot()
    def show_about(self):
        """显示关于对话框"""
        # 创建自定义消息框，添加访问官网的选项
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("关于 ACE-KILLER")
        msg_box.setText(
            "ACE-KILLER\n\n"
            "作者: CassianVale\n\n"
            "作者: 煎饺\n\n"
            "ACE-KILLER是一款游戏优化工具，用于监控并优化游戏进程\n\n"
            "💡 如果这个工具对您有帮助，欢迎访问官网：Ktcat.su\n"
            "   • 分享给更多需要的朋友\n\n"
            "您的支持是项目持续改进的动力！\n\n"
            "是否访问项目官网？"
        )
        msg_box.setIcon(QMessageBox.Information)
        
        # 添加自定义按钮
        visit_btn = msg_box.addButton("⭐ 访问官网主页", QMessageBox.ActionRole)
        close_btn = msg_box.addButton("❌ 关闭", QMessageBox.RejectRole)
        
        # 设置默认按钮
        msg_box.setDefaultButton(visit_btn)
        
        # 执行对话框并处理结果
        msg_box.exec()
        clicked_button = msg_box.clickedButton()
        
        # 如果点击了访问官网按钮
        if clicked_button == visit_btn:
            import webbrowser
            webbrowser.open("https://ktcat.su")
            logger.debug("用户通过关于对话框访问了项目官网")
    
    @Slot()
    def show_main_window(self):
        """显示主窗口"""
        # 如果窗口是通过自定义标题栏最小化的，需要特殊处理
        if self.is_custom_minimized:
            self.restore_from_custom_minimize()
        else:
            self.showNormal()
            self.activateWindow()
    
    def restore_from_custom_minimize(self):
        """从自定义标题栏最小化状态恢复窗口"""
        try:
            # 恢复窗口透明度
            self.setWindowOpacity(1.0)
            
            # 恢复原始几何信息
            if self.original_geometry and self.original_geometry.isValid():
                self.setGeometry(self.original_geometry)
            else:
                # 如果没有保存的几何信息，使用默认位置
                screen = self.screen()
                if screen:
                    center = screen.geometry().center()
                    geometry = self.geometry()
                    geometry.moveCenter(center)
                    self.setGeometry(geometry)
            
            # 显示并激活窗口
            self.show()
            self.showNormal()
            self.activateWindow()
            self.raise_()
            
            # 重置标志
            self.is_custom_minimized = False
            
            logger.debug("窗口已从自定义最小化状态恢复")
            
        except Exception as e:
            logger.error(f"从自定义最小化状态恢复窗口失败: {str(e)}")
            # 回退到简单恢复
            self.setWindowOpacity(1.0)
            self.showNormal()
            self.activateWindow()
    
    @Slot()
    def show_status(self):
        """在托盘菜单显示状态通知"""
        status = get_status_info(self.monitor)
        send_notification(
            title="ACE-KILLER 状态",
            message=status,
            icon_path=self.icon_path
        )
    
    @Slot()
    def tray_icon_activated(self, reason):
        """处理托盘图标激活事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main_window()
    
    @Slot()
    def confirm_exit(self):
        """确认退出程序"""
        self.exit_app()
    
    def exit_app(self):
        """退出应用程序"""
        # 停止所有监控
        if self.monitor.running:
            self.monitor.stop_monitors()
            self.monitor.running = False
        
        # 停止定时器（在主线程中处理）
        if hasattr(self, 'update_timer') and self.update_timer:
            self.update_timer.stop()
        
        # 隐藏托盘图标（在主线程中处理）
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
        
        # 退出应用
        QApplication.quit()
    
    def closeEvent(self, event):
        """处理窗口关闭事件"""
        # 根据配置设置执行相应操作
        if self.monitor.config_manager.close_to_tray:
            # 最小化到后台
            event.ignore()
            self.hide()
            # 如果托盘图标可见且通知开启，显示最小化提示
            if hasattr(self, 'tray_icon') and self.tray_icon.isVisible() and self.monitor.config_manager.show_notifications:
                self.tray_icon.showMessage(
                    "ACE-KILLER",
                    "程序已最小化到系统托盘，继续在后台运行",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        else:
            # 直接退出程序
            event.accept()
            self.exit_app()

    @Slot()
    def toggle_debug_mode(self):
        """切换调试模式"""
        # 获取新的调试模式状态
        new_debug_mode = self.debug_checkbox.isChecked()
        self.monitor.config_manager.debug_mode = new_debug_mode
        
        # 保存配置
        if self.monitor.config_manager.save_config():
            logger.debug(f"调试模式已更改并保存: {'开启' if new_debug_mode else '关闭'}")
        else:
            logger.warning(f"调试模式已更改但保存失败: {'开启' if new_debug_mode else '关闭'}")
        
        # 重新初始化日志系统
        from utils.logger import setup_logger
        setup_logger(
            self.monitor.config_manager.log_dir,
            self.monitor.config_manager.log_retention_days,
            self.monitor.config_manager.log_rotation,
            new_debug_mode
        )
        
        # 立即更新状态显示
        self.update_status()

    @Slot()
    def on_close_behavior_changed(self):
        """关闭行为选项变化时的处理"""
        close_to_tray = self.close_behavior_combo.currentData()
        if close_to_tray is not None:
            self.monitor.config_manager.close_to_tray = close_to_tray
            
            # 保存配置
            if self.monitor.config_manager.save_config():
                logger.debug(f"关闭行为设置已更改并保存: {'最小化到后台' if close_to_tray else '直接退出'}")
            else:
                logger.warning(f"关闭行为设置已更改但保存失败: {'最小化到后台' if close_to_tray else '直接退出'}")
            
            # 立即更新状态显示
            self.update_status()

    @Slot()
    def toggle_memory_cleanup(self):
        """切换内存清理功能开关"""
        enabled = self.memory_checkbox.isChecked()
        
        # 更新内存清理器的enabled属性
        self.memory_cleaner.enabled = enabled
        
        # 将设置同步到配置管理器
        self.memory_cleaner.sync_to_config_manager()
        
        # 检查是否应该启动或停止清理线程
        self.memory_cleaner._check_should_run_thread()
        
        if enabled:
            # 检查是否有任何清理选项被启用
            if not any(self.memory_cleaner.clean_switches):
                # 显示提示消息
                QMessageBox.information(
                    self,
                    "内存清理提示",
                    "您已启用内存清理功能，但未勾选任何清理选项。\n请勾选至少一个清理选项以使清理功能生效。",
                    QMessageBox.Ok
                )
                logger.debug("内存清理已启用，但未勾选任何清理选项")
            else:
                logger.debug("内存清理功能已启用")
        else:
            logger.debug("内存清理功能已禁用")
        
        # 立即更新UI状态
        self.update_memory_status()
    
    @Slot()
    def toggle_brute_mode(self):
        """切换暴力模式开关"""
        enabled = self.brute_mode_checkbox.isChecked()
        
        # 更新配置
        self.memory_cleaner.brute_mode = enabled
        
        # 将设置同步到配置管理器
        self.memory_cleaner.sync_to_config_manager()
        
        logger.debug(f"内存清理暴力模式已{'启用' if enabled else '禁用'}")
    
    @Slot(int, int)
    def toggle_clean_option(self, option_index, state):
        """切换清理选项"""
        # PySide6中Qt.Checked的值为2
        enabled = (state == 2)
        
        # 使用内存清理管理器的方法更新选项状态
        self.memory_cleaner.set_clean_option(option_index, enabled)
        
        # 将索引转换为实际的选项编号
        option_number = option_index + 1
        logger.debug(f"内存清理选项 {option_number} 已{'启用' if enabled else '禁用'}")
    
    @Slot(int)
    def update_clean_interval(self, value):
        """更新清理间隔时间"""
        self.memory_cleaner.set_clean_interval(value)
        
        # 更新选项文本
        self.clean_option1.setText(f"定时清理(每{value}秒)，截取进程工作集")
        self.clean_option2.setText(f"定时清理(每{value}秒)，清理系统缓存")
        self.clean_option3.setText(f"定时清理(每{value}秒)，用全部可能的方法清理内存")
        
        logger.debug(f"内存清理间隔已设置为 {value} 秒")
    
    @Slot(int)
    def update_memory_threshold(self, value):
        """更新内存占用触发阈值"""
        self.memory_cleaner.set_memory_threshold(value)
        
        # 更新选项文本
        self.clean_option4.setText(f"若内存使用量超出{value}%，截取进程工作集")
        self.clean_option5.setText(f"若内存使用量超出{value}%，清理系统缓存")
        self.clean_option6.setText(f"若内存使用量超出{value}%，用全部可能的方法清理内存")
        
        logger.debug(f"内存占用触发阈值已设置为 {value}%")
    
    @Slot(int)
    def update_cooldown_time(self, value):
        """更新清理冷却时间"""
        self.memory_cleaner.set_cooldown_time(value)
        logger.debug(f"内存清理冷却时间已设置为 {value} 秒")
    
    @Slot()
    def _update_progress_dialog_value(self, value):
        """更新进度对话框的值（从主线程）"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.setValue(value)
    
    @Slot()
    def manual_clean_workingset(self):
        """手动清理工作集"""
        try:
            cleaned_mb = self.memory_cleaner.trim_process_working_set()
            self.update_memory_status()
            logger.debug(f"手动清理工作集完成，释放了 {cleaned_mb:.2f}MB 内存")
        except Exception as e:
            logger.error(f"手动清理工作集失败: {str(e)}")
    
    @Slot()
    def manual_clean_syscache(self):
        """手动清理系统缓存"""
        try:
            cleaned_mb = self.memory_cleaner.flush_system_buffer()
            self.update_memory_status()
            logger.debug(f"手动清理系统缓存完成，释放了 {cleaned_mb:.2f}MB 内存")
        except Exception as e:
            logger.error(f"手动清理系统缓存失败: {str(e)}")
    
    @Slot()
    def manual_clean_all(self):
        """手动执行全面清理"""
        # 添加二次确认对话框
        reply = QMessageBox.question(
            self,
            "清理确认",
            "如果已经开启游戏不建议点击全部已知清理，否则清理时可能导致现有游戏卡死，或者清理后一段时间内游戏变卡\n\n确定要继续执行全部清理吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 显示进度对话框
        self.progress_dialog = QProgressDialog("正在清理内存...", "取消", 0, 3, self)
        self.progress_dialog.setWindowTitle("全面内存清理")
        self.progress_dialog.setModal(True)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        
        # 创建一个线程来执行清理
        def clean_thread_func():
            try:
                total_cleaned = 0
                
                # 清理工作集
                cleaned_mb = self.memory_cleaner.trim_process_working_set()
                total_cleaned += cleaned_mb
                # 通过信号更新UI，而不是直接修改
                self.progress_update_signal.emit(1)
                
                # 清理系统缓存
                cleaned_mb = self.memory_cleaner.flush_system_buffer()
                total_cleaned += cleaned_mb
                self.progress_update_signal.emit(2)
                
                # 全面清理
                cleaned_mb = self.memory_cleaner.clean_memory_all()
                total_cleaned += cleaned_mb
                self.progress_update_signal.emit(3)
                
                logger.debug(f"全面内存清理已完成，总共释放了 {total_cleaned:.2f}MB 内存")
            except Exception as e:
                logger.error(f"全面内存清理失败: {str(e)}")
        
        # 创建并启动线程
        clean_thread = threading.Thread(target=clean_thread_func)
        clean_thread.daemon = True
        clean_thread.start()
        
        # 显示进度对话框
        self.progress_dialog.exec_()
        
        # 清理引用
        self.progress_dialog = None
        
        # 更新状态
        self.update_memory_status()

    @Slot()
    def delete_ace_services(self):
        """删除ACE相关服务"""
        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认删除反作弊 AntiCheatExpert 服务",
            "此操作将以管理员权限删除以下服务：\n"
            "- ACE-GAME\n"
            "- ACE-BASE\n"
            "- AntiCheatExpert Service\n"
            "- AntiCheatExpert Protection\n\n"
            "这些服务将被永久删除，确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 服务列表
        services = [
            "ACE-GAME",
            "ACE-BASE",
            "AntiCheatExpert Service",
            "AntiCheatExpert Protection"
        ]
        
        # 创建进度对话框
        self.delete_progress_dialog = QProgressDialog("正在删除ACE服务...", "取消", 0, len(services), self)
        self.delete_progress_dialog.setWindowTitle("删除服务")
        self.delete_progress_dialog.setMinimumDuration(0)
        self.delete_progress_dialog.setValue(0)
        self.delete_progress_dialog.show()
        
        # 使用线程执行删除操作
        threading.Thread(target=self._delete_services_thread, args=(services, self.delete_progress_dialog)).start()
    
    def _delete_services_thread(self, services, progress):
        """线程函数：删除服务"""
        results = []
        success_count = 0
        
        for i, service in enumerate(services):
            # 使用信号更新进度
            self.delete_progress_signal.emit(i)
            
            # 检查服务是否存在
            exists, status, _ = self.monitor.check_service_status(service)
            if not exists:
                results.append(f"{service}: 服务不存在")
                continue
            
            # 创建提升权限的命令
            try:
                # 创建临时批处理文件
                temp_bat_path = os.path.join(os.environ['TEMP'], f"delete_service_{i}.bat")
                with open(temp_bat_path, 'w') as f:
                    f.write(f'@echo off\nsc stop "{service}"\nsc delete "{service}"\n')
                
                # 使用管理员权限执行批处理文件 - 添加隐藏窗口参数
                cmd = f'powershell -Command "Start-Process -WindowStyle Hidden -Verb RunAs cmd.exe -ArgumentList \'/c \"{temp_bat_path}\"\'\"'
                subprocess.run(cmd, shell=True, check=False)
                
                # 等待操作完成
                time.sleep(2)
                
                # 校验服务是否已删除
                exists, _, _ = self.monitor.check_service_status(service)
                if exists:
                    results.append(f"{service}: 删除失败")
                else:
                    results.append(f"{service}: 已成功删除")
                    success_count += 1
                    
                # 尝试删除临时文件
                try:
                    if os.path.exists(temp_bat_path):
                        os.remove(temp_bat_path)
                except:
                    pass
            except Exception as e:
                logger.error(f"删除服务 {service} 时出错: {str(e)}")
                results.append(f"{service}: 删除出错 - {str(e)}")
        
        # 更新最终进度并发送结果
        self.delete_progress_signal.emit(len(services))
        
        # 发送结果信号
        result_text = "\n".join(results)
        self.delete_result_signal.emit(result_text, success_count, len(services))
    
    @Slot(int)
    def _update_delete_progress(self, value):
        """更新删除进度对话框的值"""
        if hasattr(self, 'delete_progress_dialog') and self.delete_progress_dialog is not None:
            self.delete_progress_dialog.setValue(value)
    
    @Slot(str, int, int)
    def _show_delete_services_result(self, result_text, success_count, total_count):
        """显示删除服务的结果"""
        # 清理进度对话框引用
        if hasattr(self, 'delete_progress_dialog') and self.delete_progress_dialog is not None:
            self.delete_progress_dialog.close()
            self.delete_progress_dialog = None
        
        QMessageBox.information(
            self,
            "删除服务结果",
            f"操作完成，成功删除 {success_count}/{total_count} 个服务。\n\n详细信息：\n{result_text}"
        )
        
        # 添加通知
        if success_count > 0:
            if self.monitor.config_manager.show_notifications:
                send_notification(
                    title="ACE-KILLER 服务删除",
                    message=f"已成功删除 {success_count} 个ACE服务",
                    icon_path=self.icon_path
                )
            
        # 刷新状态
        self.update_status()

    @Slot()
    def optimize_anticheat_processes(self):
        """一键优化所有反作弊进程的I/O优先级并添加到自动优化列表"""
        # 反作弊相关进程名称列表
        anticheat_processes = [
            "SGuard64.exe", # SGuard64进程
            "ACE-Tray.exe", # ACE进程
            "AntiCheatExpert.exe", # ACE进程
            "AntiCheatExpertBase.sys", # ACE进程
            "FeverGamesService.exe", # FeverGamesService进程
        ]
        
        # 获取I/O优先级管理器
        io_manager = get_io_priority_manager()
        
        # 导入性能模式枚举
        from utils.process_io_priority import PERFORMANCE_MODE
        
        # 显示进度对话框
        progress = QProgressDialog("正在优化反作弊进程...", "取消", 0, len(anticheat_processes), self)
        progress.setWindowTitle("优化I/O优先级")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        
        # 初始化结果统计
        total_processes = 0
        successful_processes = 0
        affected_process_names = []
        added_to_list = []  # 新添加到自动优化列表的进程
        updated_in_list = []  # 在自动优化列表中更新的进程
        
        # 为每个进程设置优先级（使用效能模式）
        for i, process_name in enumerate(anticheat_processes):
            # 更新进度
            progress.setValue(i)
            if progress.wasCanceled():
                break
            
            # 设置为很低优先级和效能模式
            success_count, count = io_manager.set_process_io_priority_by_name(
                process_name, 
                IO_PRIORITY_HINT.IoPriorityVeryLow,
                PERFORMANCE_MODE.ECO_MODE
            )
            
            if count > 0:
                total_processes += count
                successful_processes += success_count
                affected_process_names.append(f"{process_name} ({success_count}/{count})")
                
                # 将成功优化的进程添加到自动优化列表
                if success_count > 0:
                    self._add_to_auto_optimize_list(process_name, PERFORMANCE_MODE.ECO_MODE, added_to_list, updated_in_list)
        
        # 完成进度
        progress.setValue(len(anticheat_processes))
        
        # 保存配置（如果有进程被添加或更新）
        if added_to_list or updated_in_list:
            self.monitor.config_manager.save_config()
        
        # 显示结果
        if total_processes == 0:
            QMessageBox.information(self, "优化结果", "未找到任何反作弊进程")
        else:
            # 构建结果消息
            result_message = (
                f"已成功优化 {successful_processes}/{total_processes} 个反作弊进程\n"
                f"设置为效能模式，降低对系统性能的影响\n\n"
                f"受影响的进程: {', '.join(affected_process_names)}\n\n"
            )
            
            if added_to_list:
                result_message += f"✅ 新添加到自动优化列表: {', '.join(added_to_list)}\n"
            
            if updated_in_list:
                result_message += f"🔄 在自动优化列表中更新: {', '.join(updated_in_list)}\n"
            
            if added_to_list or updated_in_list:
                result_message += "\n💡 这些进程将在程序启动时和每隔30秒自动优化"
            
            QMessageBox.information(self, "优化结果", result_message)
        
        # 更新状态显示
        self.update_status()
    
    def _add_to_auto_optimize_list(self, process_name: str, performance_mode: int, added_list: list, updated_list: list):
        """将进程添加到自动优化列表"""
        # 导入性能模式枚举
        from utils.process_io_priority import PERFORMANCE_MODE
        
        # 检查是否已存在于自动优化列表
        existing_found = False
        for existing_proc in self.monitor.config_manager.io_priority_processes:
            if existing_proc.get('name') == process_name:
                existing_performance_mode = existing_proc.get('performance_mode', PERFORMANCE_MODE.ECO_MODE)
                if existing_performance_mode != performance_mode:
                    # 更新性能模式
                    existing_proc['performance_mode'] = performance_mode
                    existing_proc['updated_time'] = time.time()
                    updated_list.append(process_name)
                    logger.debug(f"更新自动优化列表中的进程 {process_name} 性能模式")
                existing_found = True
                break
        
        if not existing_found:
            # 添加新进程到列表
            self.monitor.config_manager.io_priority_processes.append({
                'name': process_name,
                'performance_mode': performance_mode,
                'added_time': time.time()
            })
            added_list.append(process_name)
            logger.debug(f"添加进程 {process_name} 到自动优化列表")

    @Slot()
    def show_auto_optimize_tab(self):
        """显示自动优化列表选项卡"""
        # 导入对话框类
        from ui.process_io_priority_manager import ProcessIoPriorityManagerDialog
        
        # 创建对话框
        dialog = ProcessIoPriorityManagerDialog(self, self.monitor.config_manager)
        
        # 获取选项卡控件并切换到自动优化列表页面（索引1）
        tab_widget = dialog.findChild(QTabWidget)
        if tab_widget:
            tab_widget.setCurrentIndex(1)  # 切换到"⚙️ 自动优化列表"选项卡
        
        # 显示对话框
        dialog.exec()
        
        # 刷新状态显示，因为用户可能在列表中做了修改
        self.update_status()

    @Slot()
    def show_process_manager(self):
        """显示进程I/O优先级管理器"""
        show_process_io_priority_manager(self, self.monitor.config_manager)
        # 刷新状态显示，因为用户可能在管理器中做了修改
        self.update_status()

    @Slot()
    def stop_ace_services(self):
        """停止ACE相关服务"""
        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认停止反作弊 AntiCheatExpert 服务",
            "此操作将以管理员权限停止以下服务：\n"
            "- ACE-GAME\n"
            "- ACE-BASE\n"
            "- AntiCheatExpert Service\n"
            "- AntiCheatExpert Protection\n\n"
            "确定要停止这些服务吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 服务列表
        services = [
            "ACE-GAME",
            "ACE-BASE", 
            "AntiCheatExpert Service",
            "AntiCheatExpert Protection"
        ]
        
        # 创建进度对话框
        self.stop_progress_dialog = QProgressDialog("正在停止ACE服务...", "取消", 0, len(services), self)
        self.stop_progress_dialog.setWindowTitle("停止服务")
        self.stop_progress_dialog.setMinimumDuration(0)
        self.stop_progress_dialog.setValue(0)
        self.stop_progress_dialog.show()
        
        # 使用线程执行停止操作
        threading.Thread(target=self._stop_services_thread, args=(services, self.stop_progress_dialog)).start()
    
    def _stop_services_thread(self, services, progress):
        """线程函数：停止服务"""
        results = []
        success_count = 0
        
        for i, service in enumerate(services):
            # 使用信号更新进度
            self.stop_progress_signal.emit(i)
            
            # 检查服务是否存在
            exists, status, _ = self.monitor.check_service_status(service)
            if not exists:
                results.append(f"{service}: 服务不存在")
                continue
                
            # 如果服务已经停止，则跳过
            if status.lower() == 'stopped':
                results.append(f"{service}: 服务已经停止")
                success_count += 1
                continue
            
            # 创建提升权限的命令
            try:
                # 创建临时批处理文件
                temp_bat_path = os.path.join(os.environ['TEMP'], f"stop_service_{i}.bat")
                with open(temp_bat_path, 'w') as f:
                    f.write(f'@echo off\nsc stop "{service}"\n')
                
                # 使用管理员权限执行批处理文件 - 添加隐藏窗口参数
                cmd = f'powershell -Command "Start-Process -WindowStyle Hidden -Verb RunAs cmd.exe -ArgumentList \'/c \"{temp_bat_path}\"\'\"'
                subprocess.run(cmd, shell=True, check=False)
                
                # 等待操作完成
                time.sleep(2)
                
                # 校验服务是否已停止
                exists, new_status, _ = self.monitor.check_service_status(service)
                if exists and new_status.lower() != 'stopped':
                    results.append(f"{service}: 停止失败")
                else:
                    results.append(f"{service}: 已成功停止")
                    success_count += 1
                    
                # 尝试删除临时文件
                try:
                    if os.path.exists(temp_bat_path):
                        os.remove(temp_bat_path)
                except:
                    pass
            except Exception as e:
                logger.error(f"停止服务 {service} 时出错: {str(e)}")
                results.append(f"{service}: 停止出错 - {str(e)}")
        
        # 更新最终进度并发送结果
        self.stop_progress_signal.emit(len(services))
        
        # 发送结果信号
        result_text = "\n".join(results)
        self.stop_result_signal.emit(result_text, success_count, len(services))

    @Slot(int)
    def _update_stop_progress(self, value):
        """更新停止进度对话框的值"""
        if hasattr(self, 'stop_progress_dialog') and self.stop_progress_dialog is not None:
            self.stop_progress_dialog.setValue(value)
    
    @Slot(str, int, int)
    def _show_stop_services_result(self, result_text, success_count, total_count):
        """显示停止服务的结果"""
        # 清理进度对话框引用
        if hasattr(self, 'stop_progress_dialog') and self.stop_progress_dialog is not None:
            self.stop_progress_dialog.close()
            self.stop_progress_dialog = None
        
        QMessageBox.information(
            self,
            "停止服务结果",
            f"操作完成，成功停止 {success_count}/{total_count} 个服务。\n\n详细信息：\n{result_text}"
        )
        
        # 添加通知
        if success_count > 0:
            if self.monitor.config_manager.show_notifications:
                send_notification(
                    title="ACE-KILLER 服务停止",
                    message=f"已成功停止 {success_count} 个ACE服务",
                    icon_path=self.icon_path
                )
            
        # 刷新状态
        self.update_status()

    @Slot()
    def start_ace_program(self):
        """启动ACE反作弊程序"""
        try:
            # 检查ACE-Tray.exe文件是否存在
            ace_path = "C:\\Program Files\\AntiCheatExpert\\ACE-Tray.exe"
            if not os.path.exists(ace_path):
                QMessageBox.warning(
                    self,
                    "启动失败",
                    "未找到ACE反作弊程序，请确认已安装ACE反作弊。\n\n如果已经手动卸载ACE程序，想要重新安装，请按以下步骤：\n1. 先关闭本工具的ACE弹窗进程监控\n2. 打开任意TX游戏后在ACE弹窗中重新进行手动安装。\n3. 安装成功后重新启动电脑\n"
                )
                return
                
            # 执行命令启动反作弊程序
            subprocess.Popen([ace_path, "enable"], shell=False, 
                           creationflags=subprocess.CREATE_NO_WINDOW)
            
            logger.debug("已执行ACE反作弊程序启动命令")
            
            # 显示成功消息
            QMessageBox.information(
                self,
                "启动命令已执行",
                "ACE反作弊程序启动命令已执行！\n请重新启动电脑才能生效。"
            )
 
            # 发送通知
            if self.monitor.config_manager.show_notifications:
                send_notification(
                    title="ACE-KILLER",
                    message="ACE反作弊程序启动命令已执行",
                    icon_path=self.icon_path
                )
                
        except Exception as e:
            error_msg = f"启动ACE反作弊程序失败: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "启动失败", error_msg)

    @Slot()
    def uninstall_ace_program(self):
        """卸载ACE反作弊程序"""
        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认卸载ACE反作弊",
            "此操作将卸载ACE反作弊程序，确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        try:
            # 检查卸载程序是否存在
            uninstaller_path = "C:\\Program Files\\AntiCheatExpert\\Uninstaller.exe"
            if not os.path.exists(uninstaller_path):
                QMessageBox.warning(
                    self,
                    "卸载失败",
                    "未找到ACE反作弊卸载程序，请确认已安装ACE反作弊。\n"
                )
                return
                
            # 执行卸载命令
            subprocess.Popen([uninstaller_path], shell=False, 
                           creationflags=subprocess.CREATE_NO_WINDOW)
            
            logger.debug("已执行ACE反作弊程序卸载命令")
            
            # 发送通知
            if self.monitor.config_manager.show_notifications:
                send_notification(
                    title="ACE-KILLER",
                    message="ACE反作弊程序卸载命令已执行。",
                    icon_path=self.icon_path
                )
                
        except Exception as e:
            error_msg = f"卸载ACE反作弊程序失败: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "卸载失败", error_msg)

def get_status_info(monitor):
    """
    获取程序状态信息（托盘通知显示状态文本）
    
    Args:
        monitor: 进程监控器对象
        
    Returns:
        str: 状态信息文本
    """
    if not monitor:
        return "程序未启动"
    
    status_lines = []
    # 检查 ACE-Tray.exe 是否存在 (ACE反作弊程序是否安装提示弹窗)
    ace_proc = monitor.is_process_running(monitor.anticheat_name)
    if not ace_proc and monitor.anticheat_killed:
        status_lines.append("✅ ACE-Tray进程：已终止")
    elif not ace_proc:
        status_lines.append("ℹ️ ACE-Tray进程：未运行")
    elif ace_proc and monitor.anticheat_killed:
        status_lines.append("⏳ ACE-Tray进程：处理中")
    else:
        status_lines.append("❗ ACE-Tray进程：需要处理")
    
    # 检查 SGuard64.exe 是否存在
    scan_proc = monitor.is_process_running(monitor.scanprocess_name) is not None
    if not scan_proc and monitor.scanprocess_optimized:
        status_lines.append("✅ SGuard64进程：已优化")
    elif not scan_proc:
        status_lines.append("ℹ️ SGuard64进程：未运行")
    elif scan_proc and monitor.scanprocess_optimized:
        # 验证是否真的优化了
        try:
            is_running, is_optimized = monitor.check_process_status(monitor.scanprocess_name)
            if is_running and is_optimized:
                status_lines.append("✅ SGuard64进程：已优化")
            else:
                status_lines.append("⏳ SGuard64进程：优化中")
        except Exception:
            # 如果无法检查状态，显示处理中
            status_lines.append("⏳ SGuard64进程：优化中") 
    else:
        status_lines.append("❗ SGuard64进程：需要优化")
    
    # 检查所有反作弊服务状态
    service_results = monitor.monitor_anticheat_service()
    
    # 显示每个服务的状态
    for service_name, service_info in service_results.items():
        service_exists = service_info["exists"]
        status = service_info["status"]
        start_type = service_info["start_type"]
        
        if service_exists:
            if status == 'running':
                status_lines.append(f"✅ {service_name}：正在运行")
            elif status == 'stopped':
                status_lines.append(f"⚠️ {service_name}：已停止")
            else:
                status_lines.append(f"ℹ️ {service_name}：{status}")
                
            # 显示启动类型
            status_lines.append(f"⚙️ {service_name}启动类型：{get_start_type_display(start_type)}")
        else:
            status_lines.append(f"❓ {service_name}：未找到")
    
    status_lines.append("\n⚙️ 系统设置：")
    status_lines.append("  🔔 通知状态：" + ("开启" if monitor.config_manager.show_notifications else "关闭"))
    status_lines.append(f"  🔁 开机自启：{'开启' if monitor.config_manager.auto_start else '关闭'}")
    status_lines.append(f"  🐛 调试模式：{'开启' if monitor.config_manager.debug_mode else '关闭'}")
    status_lines.append(f"  📁 配置目录：{monitor.config_manager.config_dir}")
    status_lines.append(f"  📝 日志目录：{monitor.config_manager.log_dir}")
    status_lines.append(f"  ⏱️ 日志保留：{monitor.config_manager.log_retention_days}天")
    
    return "\n".join(status_lines)


def get_start_type_display(start_type):
    """获取启动类型的显示名称"""
    if start_type == 'auto':
        return "自动启动"
    elif start_type == 'disabled':
        return "已禁用"
    elif start_type == 'manual':
        return "手动"
    elif start_type == 'boot':
        return "系统启动"
    elif start_type == 'system':
        return "系统"
    else:
        return start_type


def create_gui(monitor, icon_path=None):
    """
    创建图形用户界面
    
    Args:
        monitor: 进程监控器对象
        icon_path: 图标路径
        
    Returns:
        (QApplication, MainWindow): 应用程序对象和主窗口对象
    """
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # 应用Ant Design全局主题样式
    StyleApplier.apply_ant_design_theme(app)
    
    # 检查是否需要最小化启动（通过命令行参数传递）
    start_minimized = "--minimized" in sys.argv
    
    window = MainWindow(monitor, icon_path, start_minimized)
    
    # 如果设置了最小化启动，则不显示主窗口
    if not start_minimized:
        window.show()
    else:
        logger.debug("程序以最小化模式启动，隐藏主窗口")
    
    return app, window
