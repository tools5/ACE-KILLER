#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPainterPath, QIcon


class CircleButton(QWidget):
    clicked = Signal()  # 点击信号
    close_requested = Signal()  # 添加关闭请求信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._default_color = "#FF5F57"
        self._hover_color = "#FF5F57"
        self._icon = None
        self._icon_size = 10
        self._is_hover = False

        # 设置鼠标追踪
        self.setMouseTracking(True)

    def setColors(self, default_color, hover_color):
        """设置按钮颜色"""
        self._default_color = default_color
        self._hover_color = hover_color
        self.update()

    def setIcon(self, icon_path):
        """设置按钮图标"""
        self._icon = QIcon(icon_path)
        self.update()

    def setIconSize(self, size):
        """设置图标大小"""
        self._icon_size = size
        self.update()

    def paintEvent(self, event):
        """绘制按钮"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制圆形背景
        self._draw_background(painter)

        # 绘制图标
        if self._is_hover and self._icon:
            self._draw_icon(painter)

    def _draw_background(self, painter):
        """绘制按钮背景"""
        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())

        color = QColor(self._hover_color if self._is_hover else self._default_color)
        painter.fillPath(path, color)

    def _draw_icon(self, painter):
        """绘制图标"""
        icon_size = QSize(self._icon_size, self._icon_size)
        icon_pos_x = (self.width() - self._icon_size) // 2
        icon_pos_y = (self.height() - self._icon_size) // 2
        self._icon.paint(
            painter, icon_pos_x, icon_pos_y, self._icon_size, self._icon_size
        )

    def enterEvent(self, event):
        """鼠标进入事件"""
        self._is_hover = True
        self.update()

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self._is_hover = False
        self.update()

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            # 只发出关闭请求信号，让父窗口处理异步关闭
            self.clicked.emit()
            self.close_requested.emit()