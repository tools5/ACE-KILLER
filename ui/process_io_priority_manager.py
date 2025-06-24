#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import psutil
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QLineEdit, QGroupBox, QProgressBar,
    QMessageBox, QTabWidget, QWidget, QSpinBox,
    QButtonGroup, QRadioButton
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QColor

from utils.logger import logger
from utils.process_io_priority import get_io_priority_manager, IO_PRIORITY_HINT, PERFORMANCE_MODE

from ui.styles import ColorScheme, StyleHelper, theme_manager


class ProcessInfoWorker(QThread):
    """获取进程信息的工作线程"""
    
    # 信号：进程数据更新
    processes_updated = Signal(list)
    # 信号：进度更新
    progress_updated = Signal(int, int)  # (current, total)
    
    def __init__(self):
        super().__init__()
        self.should_stop = False
        
    def run(self):
        """获取所有进程信息"""
        try:
            processes = []
            all_processes = list(psutil.process_iter())
            total_processes = len(all_processes)
            
            for i, proc in enumerate(all_processes):
                if self.should_stop:
                    break
                    
                try:
                    # 发送进度更新
                    self.progress_updated.emit(i + 1, total_processes)
                    
                    # 获取进程基本信息
                    proc_info = proc.as_dict(attrs=[
                        'pid', 'name', 'username', 'status',
                        'create_time', 'memory_percent'
                    ])
                    
                    # 获取内存信息
                    try:
                        memory_info = proc.memory_info()
                        proc_info['memory_mb'] = memory_info.rss / (1024 * 1024)
                    except:
                        proc_info['memory_mb'] = 0
                    
                    # 处理用户名
                    if not proc_info.get('username'):
                        proc_info['username'] = 'N/A'
                    
                    # 处理进程名
                    if not proc_info.get('name'):
                        proc_info['name'] = f'PID-{proc_info["pid"]}'
                    
                    # 判断是否为系统进程
                    username = proc_info.get('username', '')
                    proc_info['is_system'] = username in [
                        'NT AUTHORITY\\SYSTEM', 'NT AUTHORITY\\LOCAL SERVICE', 
                        'NT AUTHORITY\\NETWORK SERVICE', 'N/A'
                    ]
                    
                    processes.append(proc_info)
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    logger.debug(f"获取进程信息失败: {e}")
                    continue
            
            # 按内存使用量排序
            processes.sort(key=lambda x: x.get('memory_mb', 0), reverse=True)
            
            # 发送结果
            if not self.should_stop:
                self.processes_updated.emit(processes)
                
        except Exception as e:
            logger.error(f"获取进程信息时发生错误: {e}")
            
    def stop(self):
        """停止工作线程"""
        self.should_stop = True


class ProcessIoPriorityManagerDialog(QDialog):
    """进程I/O优先级管理对话框"""
    
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.io_manager = get_io_priority_manager()
        self.process_worker = None
        self.all_processes = []
        self.filtered_processes = []
        
        # 防抖动定时器
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self._apply_filters)
        
        # 连接主题切换信号
        theme_manager.theme_changed.connect(self.apply_theme_properties)
        
        self.setup_ui()
        self.setup_timer()
        self.load_auto_optimize_list()
        
        # 应用初始主题属性
        self.apply_theme_properties()
        
        # 延迟加载进程列表，避免阻塞UI
        QTimer.singleShot(100, self.refresh_process_list)
    
    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("进程管理器")
        self.setMinimumSize(1000, 680)
        self.resize(1200, 720)
        
        layout = QVBoxLayout(self)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # 进程列表选项卡
        process_tab = self.create_process_tab()
        tab_widget.addTab(process_tab, "🔍 进程列表")
        
        # 自动优化列表选项卡
        auto_optimize_tab = self.create_auto_optimize_tab()
        tab_widget.addTab(auto_optimize_tab, "⚙️ 自动优化列表")
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新进程列表")
        self.refresh_btn.setFixedSize(140, 35)
        self.refresh_btn.clicked.connect(self.refresh_process_list)
        button_layout.addWidget(self.refresh_btn)
        
        button_layout.addStretch()
        
        # 关闭按钮
        self.close_btn = QPushButton("关闭")
        self.close_btn.setFixedSize(80, 35)
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def create_process_tab(self):
        """创建进程列表选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 顶部过滤器组
        filter_group = QGroupBox("🔍 过滤器")
        filter_layout = QVBoxLayout(filter_group)
        
        # 第一行过滤器
        filter_row1 = QHBoxLayout()
        
        # 进程名过滤
        filter_row1.addWidget(QLabel("进程名:"))
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("输入进程名称进行过滤...")
        self.name_filter.textChanged.connect(self._schedule_filter)
        filter_row1.addWidget(self.name_filter)
        
        # 内存过滤
        filter_row1.addWidget(QLabel("内存大于:"))
        self.memory_filter = QSpinBox()
        self.memory_filter.setRange(0, 10000)
        self.memory_filter.setValue(10)  # 默认显示内存大于10MB的进程
        self.memory_filter.setSuffix(" MB")
        self.memory_filter.valueChanged.connect(self._schedule_filter)
        filter_row1.addWidget(self.memory_filter)
        
        filter_layout.addLayout(filter_row1)
        
        # 第二行过滤器
        filter_row2 = QHBoxLayout()
        
        # 进程类型过滤
        filter_row2.addWidget(QLabel("进程类型:"))
        self.process_type_group = QButtonGroup()
        
        self.show_all_radio = QRadioButton("全部")
        self.show_all_radio.setChecked(True)
        self.show_all_radio.toggled.connect(self._schedule_filter)
        self.process_type_group.addButton(self.show_all_radio)
        filter_row2.addWidget(self.show_all_radio)
        
        self.show_user_radio = QRadioButton("用户进程")
        self.show_user_radio.toggled.connect(self._schedule_filter)
        self.process_type_group.addButton(self.show_user_radio)
        filter_row2.addWidget(self.show_user_radio)
        
        self.show_system_radio = QRadioButton("系统进程")
        self.show_system_radio.toggled.connect(self._schedule_filter)
        self.process_type_group.addButton(self.show_system_radio)
        filter_row2.addWidget(self.show_system_radio)
        
        filter_row2.addStretch()
        
        # 清除过滤器按钮
        self.clear_filter_btn = QPushButton("清除过滤器")
        self.clear_filter_btn.setFixedSize(100, 32)
        self.clear_filter_btn.clicked.connect(self.clear_filters)
        filter_row2.addWidget(self.clear_filter_btn)
        
        filter_layout.addLayout(filter_row2)
        layout.addWidget(filter_group)
        
        # 信息行
        info_layout = QHBoxLayout()
        self.process_count_label = QLabel("进程数量: 0")
        info_layout.addWidget(self.process_count_label)
        
        self.loading_progress = QProgressBar()
        self.loading_progress.setVisible(False)
        self.loading_progress.setMaximumHeight(20)
        info_layout.addWidget(self.loading_progress)
        
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # 进程表格
        self.process_table = QTableWidget()
        self.process_table.setColumnCount(8)
        self.process_table.setHorizontalHeaderLabels([
            "🆔 PID", "📋 进程名", "👤 用户", "⚡ 状态", "💾 内存", "🕐 创建时间", "⚙️ 性能模式", "🛠️ 操作"
        ])
        
        # 应用表格基础设置 - 样式由全局CSS处理
        self.setup_table_properties(self.process_table)
        
        # 设置列宽
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)        # PID
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 进程名
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # 用户
        header.setSectionResizeMode(3, QHeaderView.Fixed)        # 状态
        header.setSectionResizeMode(4, QHeaderView.Fixed)        # 内存
        header.setSectionResizeMode(5, QHeaderView.Interactive)  # 创建时间
        header.setSectionResizeMode(6, QHeaderView.Interactive)  # 性能模式
        header.setSectionResizeMode(7, QHeaderView.Fixed)        # 操作
        
        # 设置合理的初始列宽
        header.resizeSection(0, 70)    # PID
        header.resizeSection(2, 170)   # 用户
        header.resizeSection(3, 100)   # 状态
        header.resizeSection(4, 80)    # 内存
        header.resizeSection(5, 100)   # 创建时间
        header.resizeSection(6, 150)   # 性能模式
        header.resizeSection(7, 120)   # 操作
        
        # 连接信号以限制最小列宽
        header.sectionResized.connect(self.on_process_table_section_resized)
        
        layout.addWidget(self.process_table)
        
        return widget
    
    def create_auto_optimize_tab(self):
        """创建自动优化列表选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 说明信息
        self.auto_info_label = QLabel(
            "自动优化列表中的进程会在程序启动时和每隔30秒自动优化。\n"
            "优化包括：根据性能模式自动设置CPU优先级、CPU亲和性调整、I/O优先级设置。\n"
            "这有助于持续优化这些进程的系统资源占用，减少对前台应用的影响。"
        )
        self.auto_info_label.setWordWrap(True)
        layout.addWidget(self.auto_info_label)
        
        # 自动优化列表表格
        self.auto_optimize_table = QTableWidget()
        self.auto_optimize_table.setColumnCount(4)
        self.auto_optimize_table.setHorizontalHeaderLabels([
            "📋 进程名", "⚙️ 性能模式", "🕐 添加时间", "🛠️ 操作"
        ])
        
        # 应用表格基础设置 - 样式由全局CSS处理
        self.setup_table_properties(self.auto_optimize_table)
        
        # 设置列宽 - 让列填充满表格宽度
        auto_header = self.auto_optimize_table.horizontalHeader()
        auto_header.setSectionResizeMode(0, QHeaderView.Stretch)  # 进程名
        auto_header.setSectionResizeMode(1, QHeaderView.Interactive)  # 性能模式
        auto_header.setSectionResizeMode(2, QHeaderView.Interactive)  # 添加时间
        auto_header.setSectionResizeMode(3, QHeaderView.Fixed)       # 操作
        
        # 设置合理的初始列宽
        auto_header.resizeSection(1, 150)  # 性能模式
        auto_header.resizeSection(2, 150)  # 添加时间
        auto_header.resizeSection(3, 120)  # 操作
        
        # 连接信号以限制最小列宽
        auto_header.sectionResized.connect(self.on_auto_optimize_table_section_resized)
        
        layout.addWidget(self.auto_optimize_table)
        
        # 底部统计信息
        stats_layout = QHBoxLayout()
        self.auto_optimize_count_label = QLabel("自动优化进程数: 0")
        stats_layout.addWidget(self.auto_optimize_count_label)
        stats_layout.addStretch()
        
        # 清空列表按钮
        self.clear_all_btn = QPushButton("🗑️ 清空列表")
        self.clear_all_btn.setFixedSize(110, 32)
        self.clear_all_btn.clicked.connect(self.clear_auto_optimize_list)
        stats_layout.addWidget(self.clear_all_btn)
        
        layout.addLayout(stats_layout)
        
        return widget
    
    def setup_table_properties(self, table):
        """设置表格基础属性 - 样式由CSS处理"""
        # 基本表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(True)
        table.setShowGrid(False)  # 隐藏网格线
        table.setFocusPolicy(Qt.NoFocus)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.clearSelection()
        
        # 设置行高
        table.verticalHeader().setDefaultSectionSize(50)
        table.verticalHeader().setVisible(False)  # 隐藏行号
        
        # 设置表头基础属性
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setMinimumHeight(40)
    
    def apply_theme_properties(self):
        """应用主题属性到组件"""
        try:
            # 设置按钮类型
            if hasattr(self, 'refresh_btn'):
                StyleHelper.set_button_type(self.refresh_btn, "primary")
            if hasattr(self, 'clear_filter_btn'):
                StyleHelper.set_button_type(self.clear_filter_btn, "default")
            if hasattr(self, 'clear_all_btn'):
                StyleHelper.set_button_type(self.clear_all_btn, "warning")
            if hasattr(self, 'close_btn'):
                StyleHelper.set_button_type(self.close_btn, "default")
            
            # 设置信息标签类型
            if hasattr(self, 'auto_info_label'):
                StyleHelper.set_label_type(self.auto_info_label, "success")
                
        except Exception as e:
            logger.error(f"应用主题属性失败: {str(e)}")
    
    def setup_timer(self):
        """设置定时器"""
        # 定时刷新进程信息（每30秒）
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_process_list)
        self.refresh_timer.start(30000)  # 30秒
    
    def _schedule_filter(self):
        """安排过滤操作（防抖动）"""
        self.filter_timer.stop()
        self.filter_timer.start(300)  # 300毫秒后执行过滤
    
    def _apply_filters(self):
        """应用过滤器（实际的过滤逻辑）"""
        if not self.all_processes:
            return
        
        name_filter = self.name_filter.text().lower().strip()
        memory_filter = self.memory_filter.value()
        
        # 进程类型过滤
        show_all = self.show_all_radio.isChecked()
        show_user = self.show_user_radio.isChecked()
        show_system = self.show_system_radio.isChecked()
        
        # 过滤进程
        filtered_processes = []
        for proc in self.all_processes:
            # 进程名过滤
            if name_filter and name_filter not in proc['name'].lower():
                continue
            
            # 内存过滤
            if proc.get('memory_mb', 0) < memory_filter:
                continue
            
            # 进程类型过滤
            if not show_all:
                if show_user and proc.get('is_system', False):
                    continue
                if show_system and not proc.get('is_system', False):
                    continue
            
            filtered_processes.append(proc)
        
        self.filtered_processes = filtered_processes
        
        # 更新表格
        self.populate_process_table(filtered_processes)
        
        # 更新统计信息
        self.process_count_label.setText(
            f"显示进程数: {len(filtered_processes)} / 总进程数: {len(self.all_processes)}"
        )
    
    def clear_filters(self):
        """清除所有过滤器"""
        self.name_filter.clear()
        self.memory_filter.setValue(0)
        self.show_all_radio.setChecked(True)
        self._apply_filters()
    
    def refresh_process_list(self):
        """刷新进程列表"""
        if self.process_worker and self.process_worker.isRunning():
            return  # 如果已经在刷新，则跳过
        
        # 显示加载状态
        self.loading_progress.setVisible(True)
        self.loading_progress.setRange(0, 0)  # 不确定进度
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("🔄 刷新中...")
        
        # 创建工作线程
        self.process_worker = ProcessInfoWorker()
        self.process_worker.processes_updated.connect(self.update_process_table)
        self.process_worker.progress_updated.connect(self.update_loading_progress)
        self.process_worker.finished.connect(self.on_refresh_finished)
        self.process_worker.start()
    
    def update_loading_progress(self, current, total):
        """更新加载进度"""
        if total > 0:
            self.loading_progress.setRange(0, total)
            self.loading_progress.setValue(current)
    
    def on_refresh_finished(self):
        """刷新完成"""
        self.loading_progress.setVisible(False)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 刷新进程列表")
        
        if self.process_worker:
            self.process_worker.deleteLater()
            self.process_worker = None
    
    def update_process_table(self, processes):
        """更新进程表格"""
        self.all_processes = processes
        self._apply_filters()  # 应用当前过滤器
    
    def populate_process_table(self, processes):
        """填充进程表格"""
        # 禁用排序以提高性能
        self.process_table.setSortingEnabled(False)
        
        # 设置行数
        current_row_count = self.process_table.rowCount()
        target_row_count = len(processes)
        
        if current_row_count != target_row_count:
            self.process_table.setRowCount(target_row_count)
        
        # 批量更新表格项
        for row, proc in enumerate(processes):
            self._populate_row(row, proc)
        
        # 重新启用排序
        self.process_table.setSortingEnabled(True)
    
    def _populate_row(self, row, proc):
        """填充单行数据"""
        # PID
        pid_item = self._get_or_create_item(row, 0)
        pid_item.setText(str(proc['pid']))
        pid_item.setData(Qt.UserRole, proc)  # 存储完整进程信息
        
        # 进程名 - 为系统进程添加特殊标识
        name_item = self._get_or_create_item(row, 1)
        process_name = proc['name']
        if proc.get('is_system', False):
            process_name = f"🔒 {process_name}"  # 系统进程添加锁定图标
            name_item.setForeground(QColor(ColorScheme.PROCESS_SYSTEM()))  # 系统进程使用灰色
        else:
            name_item.setForeground(QColor(ColorScheme.PROCESS_USER()))  # 用户进程使用深色
        name_item.setText(process_name)
        
        # 用户 - 添加用户类型颜色区分
        user_item = self._get_or_create_item(row, 2)
        username = proc['username']
        user_color = ColorScheme.PROCESS_SYSTEM_USER() if proc.get('is_system', False) else ColorScheme.PROCESS_USER()
        user_item.setText(username)
        user_item.setForeground(QColor(user_color))
        
        # 状态 - 添加状态图标和颜色
        status_item = self._get_or_create_item(row, 3)
        status = proc['status']
        status_icon, status_color = self.get_status_display(status)
        status_item.setText(f"{status_icon} {status}")
        status_item.setForeground(QColor(status_color))
        
        # 内存 - 添加内存使用量颜色指示
        memory_item = self._get_or_create_item(row, 4)
        memory_mb = proc.get('memory_mb', 0)
        memory_text, memory_color = self.get_memory_display(memory_mb)
        memory_item.setText(memory_text)
        memory_item.setForeground(QColor(memory_color))
        
        # 创建时间
        time_item = self._get_or_create_item(row, 5)
        try:
            create_time = time.strftime('%m-%d %H:%M', 
                                      time.localtime(proc.get('create_time', 0)))
        except:
            create_time = 'N/A'
        time_item.setText(create_time)
        
        # 性能模式选择
        performance_mode_combo = self.process_table.cellWidget(row, 6)
        if not performance_mode_combo:
            performance_mode_combo = QComboBox()
            performance_mode_combo.addItem("🔥 最大性能模式", PERFORMANCE_MODE.MAXIMUM_PERFORMANCE)
            performance_mode_combo.addItem("🚀 高性能模式", PERFORMANCE_MODE.HIGH_PERFORMANCE)
            performance_mode_combo.addItem("🍉 正常模式", PERFORMANCE_MODE.NORMAL_MODE)
            performance_mode_combo.addItem("🌱 效能模式", PERFORMANCE_MODE.ECO_MODE)
            performance_mode_combo.setCurrentIndex(2)  # 默认选择"正常模式"
            performance_mode_combo.setFixedHeight(30)   # 设置固定高度
            performance_mode_combo.setMinimumWidth(120) # 设置最小宽度，确保文本完整显示
            
            # 设置改进的工具提示
            performance_mode_combo.setToolTip(
                "选择进程性能模式：\n\n"
                "🔥 最大性能模式 - 实时优先级，绑定所有核心，最高性能\n"
                "🚀 高性能模式 - 高优先级，绑定所有核心，适合游戏等重要应用\n"
                "🍉 正常模式 - 正常优先级，绑定所有核心，系统默认设置\n"
                "🌱 效能模式 - 效能模式，绑定到最后一个核心，降低功耗\n\n"
                "💡 建议：\n"
                "• 游戏/重要应用：高性能或最大性能\n"
                "• 后台进程/反作弊：效能模式\n"
                "• 一般应用：正常模式"
            )
            self.process_table.setCellWidget(row, 6, performance_mode_combo)
        
        # 操作按钮
        action_widget = self.process_table.cellWidget(row, 7)
        if not action_widget:
            action_layout = QHBoxLayout()
            action_widget = QWidget()
            
            # 应用并添加到列表按钮
            apply_btn = QPushButton("🚀 应用")
            apply_btn.setStyleSheet("min-height: 20px;")
            apply_btn.setToolTip("应用当前选择的性能模式设置到进程，并添加到自动优化列表")
            
            # 设置按钮类型
            StyleHelper.set_button_type(apply_btn, "success")
            
            apply_btn.setProperty("process_info", proc)
            apply_btn.clicked.connect(lambda checked, btn=apply_btn: self.apply_performance_mode_by_button(btn))
            action_layout.addWidget(apply_btn)
            
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(2)
            action_widget.setLayout(action_layout)
            self.process_table.setCellWidget(row, 7, action_widget)
        else:
            # 如果按钮已存在，更新存储的进程信息
            apply_btn = action_widget.layout().itemAt(0).widget()
            if apply_btn:
                apply_btn.setProperty("process_info", proc)
    
    def _get_or_create_item(self, row, column):
        """获取或创建表格项"""
        item = self.process_table.item(row, column)
        if not item:
            item = QTableWidgetItem()
            self.process_table.setItem(row, column, item)
        return item
    
    def apply_performance_mode_by_button(self, button):
        """通过按钮应用性能模式并添加到自动优化列表"""
        # 从按钮获取进程信息
        proc_info = button.property("process_info")
        if not proc_info:
            return
        
        # 找到按钮所在的行
        row = -1
        for r in range(self.process_table.rowCount()):
            widget = self.process_table.cellWidget(r, 7)
            if widget and widget.layout().itemAt(0).widget() == button:
                row = r
                break
        
        if row == -1:
            return
        
        # 获取选择的性能模式
        performance_mode_combo = self.process_table.cellWidget(row, 6)
        if not performance_mode_combo:
            return
        
        performance_mode = performance_mode_combo.currentData()
        process_name = proc_info['name']
        pid = proc_info['pid']
        
        # 根据性能模式设置对应的I/O优先级
        if performance_mode == PERFORMANCE_MODE.MAXIMUM_PERFORMANCE:
            # 最大性能：实时优先级，绑定所有核心
            priority = IO_PRIORITY_HINT.IoPriorityCritical
        elif performance_mode == PERFORMANCE_MODE.HIGH_PERFORMANCE:
            # 高性能：高优先级，绑定所有核心
            priority = IO_PRIORITY_HINT.IoPriorityNormal
        elif performance_mode == PERFORMANCE_MODE.NORMAL_MODE:
            # 正常模式：正常优先级，绑定所有核心
            priority = IO_PRIORITY_HINT.IoPriorityNormal
        else:  # ECO_MODE
            # 效能模式：低优先级，绑定到最后一个核心
            priority = IO_PRIORITY_HINT.IoPriorityLow
        
        # 应用性能模式设置
        success = self.io_manager.set_process_io_priority(pid, priority, performance_mode)
        
        if not success:
            QMessageBox.warning(self, "优化失败", 
                f"无法优化进程 {process_name} (PID: {pid})\n可能是权限不足或进程已退出")
            return
        
        # 检查是否已存在于自动优化列表
        existing_found = False
        for existing_proc in self.config_manager.io_priority_processes:
            if existing_proc.get('name') == process_name:
                # 如果进程已存在，检查性能模式
                existing_performance_mode = existing_proc.get('performance_mode', PERFORMANCE_MODE.ECO_MODE)
                if existing_performance_mode != performance_mode:
                    # 性能模式不同，询问是否更新
                    reply = QMessageBox.question(
                        self,
                        "进程已存在",
                        f"进程 {process_name} 已在自动优化列表中，但性能模式不同。\n"
                        f"当前列表中性能模式: {self.get_performance_mode_text(existing_performance_mode)}\n"
                        f"新选择的性能模式: {self.get_performance_mode_text(performance_mode)}\n\n"
                        f"是否要更新设置？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if reply == QMessageBox.Yes:
                        existing_proc['performance_mode'] = performance_mode
                        existing_proc['updated_time'] = time.time()
                        existing_found = True
                    else:
                        # 用户选择不更新，但进程优化已经完成了
                        QMessageBox.information(self, "优化完成", 
                            f"✅ 已成功优化进程 {process_name} (PID: {pid})\n"
                            f"⚡ 性能模式: {self.get_performance_mode_text(performance_mode)}\n\n"
                            f"自动优化列表保持原有设置不变")
                        return
                else:
                    # 性能模式相同，提示不需要重复添加
                    QMessageBox.information(self, "进程已存在", 
                        f"✅ 已成功优化进程 {process_name} (PID: {pid})\n"
                        f"⚡ 性能模式: {self.get_performance_mode_text(performance_mode)}\n\n"
                        f"💡 该进程已在自动优化列表中，性能模式设置相同，无需重复添加。\n"
                        f"系统将继续按照当前设置自动优化该进程。")
                    existing_found = True
                break
        
        if not existing_found:
            # 添加新进程到列表
            self.config_manager.io_priority_processes.append({
                'name': process_name,
                'performance_mode': performance_mode,
                'added_time': time.time()
            })
        
        # 保存配置
        if self.config_manager.save_config():
            if existing_found:
                QMessageBox.information(self, "优化成功", 
                    f"✅ 已成功优化进程 {process_name} (PID: {pid})\n"
                    f"⚡ 性能模式: {self.get_performance_mode_text(performance_mode)}\n\n"
                    f"✅ 自动优化列表中的设置已更新")
            else:
                QMessageBox.information(self, "优化成功", 
                    f"✅ 已成功优化进程 {process_name} (PID: {pid})\n"
                    f"⚡ 性能模式: {self.get_performance_mode_text(performance_mode)}\n\n"
                    f"✅ 已添加到自动优化列表，将定期自动优化")
            
            # 刷新自动优化列表显示
            self.load_auto_optimize_list()
            logger.debug(f"优化并添加进程到自动优化列表: {process_name} (PID: {pid}) -> {performance_mode}")
        else:
            QMessageBox.warning(self, "保存失败", 
                f"进程优化成功，但无法保存到自动优化列表\n请检查程序权限")
    
    def load_auto_optimize_list(self):
        """加载自动优化列表（优化版本）"""
        if not self.config_manager:
            return
        
        processes = self.config_manager.io_priority_processes
        
        # 禁用排序以提高性能
        self.auto_optimize_table.setSortingEnabled(False)
        
        current_row_count = self.auto_optimize_table.rowCount()
        target_row_count = len(processes)
        
        if current_row_count != target_row_count:
            self.auto_optimize_table.setRowCount(target_row_count)
        
        for row, proc in enumerate(processes):
            # 进程名
            name_item = self._get_or_create_auto_item(row, 0)
            name_item.setText(proc.get('name', ''))
            
            # 性能模式下拉框
            performance_combo = self.auto_optimize_table.cellWidget(row, 1)
            if not performance_combo:
                performance_combo = QComboBox()
                performance_combo.addItem("🔥 最大性能模式", PERFORMANCE_MODE.MAXIMUM_PERFORMANCE)
                performance_combo.addItem("🚀 高性能模式", PERFORMANCE_MODE.HIGH_PERFORMANCE)
                performance_combo.addItem("🍉 正常模式", PERFORMANCE_MODE.NORMAL_MODE)
                performance_combo.addItem("🌱 效能模式", PERFORMANCE_MODE.ECO_MODE)
                performance_combo.setFixedHeight(30)
                performance_combo.setMinimumWidth(120)
                performance_combo.setProperty("process_name", proc.get('name', ''))
                performance_combo.currentIndexChanged.connect(lambda index, combo=performance_combo: self.on_auto_performance_mode_changed(combo))
                self.auto_optimize_table.setCellWidget(row, 1, performance_combo)
            
            # 设置当前性能模式
            performance_mode = proc.get('performance_mode', PERFORMANCE_MODE.ECO_MODE)
            for i in range(performance_combo.count()):
                if performance_combo.itemData(i) == performance_mode:
                    performance_combo.setCurrentIndex(i)
                    break
            
            # 添加时间
            add_time = proc.get('added_time', proc.get('updated_time', 0))
            time_item = self._get_or_create_auto_item(row, 2)
            if add_time:
                time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(add_time))
            else:
                time_str = 'N/A'
            time_item.setText(time_str)
            
            # 操作按钮
            action_widget = self.auto_optimize_table.cellWidget(row, 3)
            if not action_widget:
                action_layout = QHBoxLayout()
                action_widget = QWidget()
                
                # 删除按钮
                delete_btn = QPushButton("🗑️ 删除")
                delete_btn.setStyleSheet("min-height: 20px;")
                
                # 设置按钮类型
                StyleHelper.set_button_type(delete_btn, "danger")
                
                # 将进程名存储在按钮中
                delete_btn.setProperty("process_name", proc.get('name', ''))
                delete_btn.clicked.connect(lambda checked, btn=delete_btn: self.delete_from_auto_optimize_list_by_button(btn))
                action_layout.addWidget(delete_btn)
                
                action_layout.setContentsMargins(2, 2, 2, 2)
                action_layout.setSpacing(2)
                action_widget.setLayout(action_layout)
                self.auto_optimize_table.setCellWidget(row, 3, action_widget)
            else:
                # 如果按钮已存在，更新存储的进程名
                delete_btn = action_widget.layout().itemAt(0).widget()
                if delete_btn:
                    delete_btn.setProperty("process_name", proc.get('name', ''))
        
        # 重新启用排序
        self.auto_optimize_table.setSortingEnabled(True)
        
        # 清除选择，避免焦点高亮
        self.auto_optimize_table.clearSelection()
        
        # 更新统计信息
        self.auto_optimize_count_label.setText(f"自动优化进程数: {len(processes)}")
    
    def _get_or_create_auto_item(self, row, column):
        """获取或创建自动优化表格项"""
        item = self.auto_optimize_table.item(row, column)
        if not item:
            item = QTableWidgetItem()
            self.auto_optimize_table.setItem(row, column, item)
        return item
    
    def get_priority_text(self, priority):
        """获取优先级的文本表示"""
        priority_map = {
            IO_PRIORITY_HINT.IoPriorityCritical: "🔴 最高优先级",
            IO_PRIORITY_HINT.IoPriorityNormal: "🟢 正常优先级", 
            IO_PRIORITY_HINT.IoPriorityLow: "🟡 低优先级",
            IO_PRIORITY_HINT.IoPriorityVeryLow: "🔵 最低优先级"
        }
        return priority_map.get(priority, f"未知({priority})")
    
    def get_performance_mode_text(self, performance_mode):
        """获取性能模式的文本表示"""
        mode_map = {
            PERFORMANCE_MODE.MAXIMUM_PERFORMANCE: "🔥 最大性能模式",
            PERFORMANCE_MODE.HIGH_PERFORMANCE: "🚀 高性能模式",
            PERFORMANCE_MODE.NORMAL_MODE: "🍉 正常模式",
            PERFORMANCE_MODE.ECO_MODE: "🌱 效能模式"
        }
        return mode_map.get(performance_mode, f"未知({performance_mode})")
    
    def get_status_display(self, status):
        """获取进程状态的显示样式"""
        status_map = {
            'running': ('🟢', ColorScheme.PROCESS_RUNNING()),
            'sleeping': ('💤', ColorScheme.PROCESS_SYSTEM()),
            'disk-sleep': ('💾', ColorScheme.INFO()),
            'stopped': ('⏸️', ColorScheme.WARNING_BTN()),
            'tracing-stop': ('🔍', '#fd7e14'),
            'zombie': ('💀', ColorScheme.DANGER()),
            'dead': ('☠️', '#6f42c1'),
            'wake-kill': ('⚡', '#e83e8c'),
            'waking': ('🌅', '#20c997'),
            'idle': ('😴', ColorScheme.PROCESS_SYSTEM()),
            'locked': ('🔒', '#fd7e14'),
            'waiting': ('⏳', ColorScheme.INFO())
        }
        return status_map.get(status.lower(), ('❓', ColorScheme.PROCESS_SYSTEM()))
    
    def get_memory_display(self, memory_mb):
        """获取内存使用量的显示样式"""
        if memory_mb >= 1000:  # 大于1GB
            return f"{memory_mb:.1f} MB", ColorScheme.MEMORY_HIGH()  # 红色 - 高内存使用
        elif memory_mb >= 500:  # 500MB-1GB
            return f"{memory_mb:.1f} MB", '#fd7e14'  # 橙色 - 中等内存使用
        elif memory_mb >= 100:  # 100MB-500MB
            return f"{memory_mb:.1f} MB", ColorScheme.WARNING_BTN()  # 黄色 - 一般内存使用
        else:  # 小于100MB
            return f"{memory_mb:.1f} MB", ColorScheme.MEMORY_LOW()  # 绿色 - 低内存使用
    
    def delete_from_auto_optimize_list_by_button(self, button):
        """通过按钮从自动优化列表中删除进程"""
        # 从按钮获取进程名
        process_name = button.property("process_name")
        if not process_name:
            return
        
        # 在配置中找到对应的进程
        process_index = -1
        for i, proc in enumerate(self.config_manager.io_priority_processes):
            if proc.get('name') == process_name:
                process_index = i
                break
        
        if process_index == -1:
            QMessageBox.warning(self, "错误", f"未找到进程 '{process_name}'")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要从自动优化列表中删除进程 '{process_name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.config_manager.io_priority_processes[process_index]
            
            # 保存配置
            if self.config_manager.save_config():
                self.load_auto_optimize_list()  # 重新加载列表
                logger.debug(f"从自动优化列表删除进程: {process_name}")
            else:
                QMessageBox.warning(self, "保存失败", "删除进程后保存配置失败")
    
    def clear_auto_optimize_list(self):
        """清空自动优化列表"""
        if not self.config_manager.io_priority_processes:
            QMessageBox.information(self, "提示", "自动优化列表已为空")
            return
        
        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确定要清空整个自动优化列表吗？\n这将删除 {len(self.config_manager.io_priority_processes)} 个进程的自动优化设置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.config_manager.io_priority_processes.clear()
            
            # 保存配置
            if self.config_manager.save_config():
                self.load_auto_optimize_list()  # 重新加载列表
                QMessageBox.information(self, "成功", "已清空自动优化列表")
                logger.debug("清空自动优化列表")
            else:
                QMessageBox.warning(self, "保存失败", "清空列表后保存配置失败")
    
    def on_process_table_section_resized(self, logical_index, old_size, new_size):
        """处理进程表格列宽调整，限制最小宽度"""
        # 定义每列的最小宽度
        min_widths = {
            0: 50,   # PID
            1: 120,  # 进程名
            2: 80,   # 用户
            3: 70,   # 状态
            4: 60,   # 内存
            5: 100,  # 创建时间
            6: 120,  # 性能模式
            7: 100   # 操作
        }
        
        min_width = min_widths.get(logical_index, 50)
        if new_size < min_width:
            # 阻止信号递归
            header = self.process_table.horizontalHeader()
            header.sectionResized.disconnect(self.on_process_table_section_resized)
            header.resizeSection(logical_index, min_width)
            header.sectionResized.connect(self.on_process_table_section_resized)
    
    def on_auto_optimize_table_section_resized(self, logical_index, old_size, new_size):
        """处理自动优化表格列宽调整，限制最小宽度"""
        # 定义每列的最小宽度
        min_widths = {
            0: 120,  # 进程名
            1: 120,  # 性能模式
            2: 120,  # 添加时间
            3: 100   # 操作
        }
        
        min_width = min_widths.get(logical_index, 80)
        if new_size < min_width:
            # 阻止信号递归
            header = self.auto_optimize_table.horizontalHeader()
            header.sectionResized.disconnect(self.on_auto_optimize_table_section_resized)
            header.resizeSection(logical_index, min_width)
            header.sectionResized.connect(self.on_auto_optimize_table_section_resized)

    def on_auto_performance_mode_changed(self, combo):
        """自动优化列表中性能模式改变时的处理"""
        process_name = combo.property("process_name")
        new_performance_mode = combo.currentData()
        
        if not process_name or new_performance_mode is None:
            return
        
        # 在配置中找到对应的进程并更新
        for proc in self.config_manager.io_priority_processes:
            if proc.get('name') == process_name:
                old_performance_mode = proc.get('performance_mode', PERFORMANCE_MODE.ECO_MODE)
                if old_performance_mode != new_performance_mode:
                    proc['performance_mode'] = new_performance_mode
                    proc['updated_time'] = time.time()
                    
                    # 保存配置
                    if self.config_manager.save_config():
                        # 如果进程当前正在运行，立即应用新设置
                        self._apply_to_running_process(process_name, new_performance_mode)
                        logger.debug(f"更新自动优化进程 {process_name} 的性能模式: {old_performance_mode} -> {new_performance_mode}")
                    else:
                        # 保存失败，恢复原来的值
                        combo.blockSignals(True)
                        for i in range(combo.count()):
                            if combo.itemData(i) == old_performance_mode:
                                combo.setCurrentIndex(i)
                                break
                        combo.blockSignals(False)
                        QMessageBox.warning(self, "保存失败", f"无法保存进程 {process_name} 的性能模式设置")
                break
    
    def _apply_to_running_process(self, process_name, performance_mode):
        """将性能模式设置应用到当前运行的所有同名进程"""
        try:
            # 使用set_process_io_priority_by_name方法处理所有同名进程
            # 传入priority=None让它根据性能模式自动确定I/O优先级
            success_count, total_count = self.io_manager.set_process_io_priority_by_name(
                process_name, 
                priority=None,  # 自动确定优先级
                performance_mode=performance_mode
            )
            
            if total_count > 0:
                if success_count == total_count:
                    logger.debug(f"已将性能模式 {performance_mode} 应用到所有运行中的 {process_name} 进程 ({success_count}/{total_count})")
                else:
                    logger.warning(f"部分 {process_name} 进程优化失败 ({success_count}/{total_count})")
            else:
                logger.debug(f"未找到运行中的 {process_name} 进程")
                
        except Exception as e:
            logger.error(f"应用性能模式到运行中的进程 {process_name} 时出错: {e}")

    def closeEvent(self, event):
        """关闭事件处理"""
        # 停止定时器
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        
        if hasattr(self, 'filter_timer'):
            self.filter_timer.stop()
        
        # 停止工作线程
        if self.process_worker and self.process_worker.isRunning():
            self.process_worker.stop()
            self.process_worker.wait(1000)
        
        # 断开主题信号连接
        try:
            theme_manager.theme_changed.disconnect(self.apply_theme_properties)
        except:
            pass  # 忽略断开连接失败的情况
        
        event.accept()


def show_process_io_priority_manager(parent=None, config_manager=None):
    """显示进程I/O优先级管理对话框"""
    dialog = ProcessIoPriorityManagerDialog(parent, config_manager)
    return dialog.exec() 