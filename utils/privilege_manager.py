#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Windows权限管理模块
提供Windows API权限提升和管理功能
"""

import ctypes
import sys
import win32security
import win32api
from utils.logger import logger


class WindowsPrivilegeManager:
    """Windows权限管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WindowsPrivilegeManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 权限状态
        self.available_functions = {
            "trim_all_processes": False,
            "flush_system_cache": False,
            "memory_combine": False,
            "purge_standby_list": False,
            "debug_other_processes": False,
            "set_process_io_priority": False,
            "set_process_priority": False,
        }

        # 初始化权限
        self.privilege_status = self._init_privileges()

        self._initialized = True

    def _init_privileges(self):
        """初始化并提升程序权限"""
        try:
            # 获取当前进程句柄
            hProcess = win32api.GetCurrentProcess()

            # 打开进程令牌
            hToken = win32security.OpenProcessToken(
                hProcess, win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY
            )

            # 智能权限分组
            # 1. 核心权限 - 内存清理必需，失败则功能受限
            core_privileges = [
                win32security.SE_INCREASE_QUOTA_NAME,  # 提高内存配额权限，系统缓存清理必需
                "SeProfileSingleProcessPrivilege",  # 单进程分析权限，清理工作集必需
            ]

            # 2. 增强权限 - 提升性能和功能，但不是必需
            enhanced_privileges = [
                win32security.SE_DEBUG_NAME,  # 最关键的调试权限，用于访问其他进程
                win32security.SE_INC_WORKING_SET_NAME,  # 增加工作集权限
                win32security.SE_MANAGE_VOLUME_NAME,  # 管理卷权限，文件系统缓存操作
            ]

            # 3. 进程管理权限 - 进程优先级设置必需
            process_privileges = [
                "SeIncreaseBasePriorityPrivilege",  # 提升进程基础优先级权限
                "SeSystemtimePrivilege",  # 系统时间权限
                # "SeAssignPrimaryTokenPrivilege",           # 分配主令牌权限
            ]

            # 记录权限状态
            privilege_status = {
                "core": {"total": len(core_privileges), "acquired": 0},
                "enhanced": {"total": len(enhanced_privileges), "acquired": 0},
                "process": {"total": len(process_privileges), "acquired": 0},
            }
            privilege_details = {}

            # 先请求核心权限 - 单独处理每一个，确保最大成功率
            for privilege_name in core_privileges:
                result = self._request_single_privilege(hToken, privilege_name)
                privilege_details[privilege_name] = result
                if result["success"]:
                    privilege_status["core"]["acquired"] += 1

            # 请求增强权限
            for privilege_name in enhanced_privileges:
                result = self._request_single_privilege(hToken, privilege_name)
                privilege_details[privilege_name] = result
                if result["success"]:
                    privilege_status["enhanced"]["acquired"] += 1

            # 请求进程管理权限
            for privilege_name in process_privileges:
                result = self._request_single_privilege(hToken, privilege_name)
                privilege_details[privilege_name] = result
                if result["success"]:
                    privilege_status["process"]["acquired"] += 1

            # 关闭句柄
            win32api.CloseHandle(hToken)

            # 根据权限获取情况确定可用功能
            self.available_functions = {
                "trim_all_processes": privilege_status["core"]["acquired"] > 0,
                "flush_system_cache": privilege_status["core"]["acquired"] > 0,
                "memory_combine": privilege_status["enhanced"]["acquired"] > 0,
                "purge_standby_list": privilege_status["core"]["acquired"] > 0,
                "debug_other_processes": win32security.SE_DEBUG_NAME in privilege_details
                and privilege_details[win32security.SE_DEBUG_NAME]["success"],
                "set_process_io_priority": (
                    privilege_status["enhanced"]["acquired"] > 0 or privilege_status["process"]["acquired"] > 0
                ),
                "set_process_priority": (
                    privilege_status["enhanced"]["acquired"] > 0 or privilege_status["process"]["acquired"] > 0
                ),
            }

            # 记录权限获取结果
            logger.debug(
                f"权限获取状态: 核心权限 {privilege_status['core']['acquired']}/{privilege_status['core']['total']}, "
                f"增强权限 {privilege_status['enhanced']['acquired']}/{privilege_status['enhanced']['total']}, "
                f"进程权限 {privilege_status['process']['acquired']}/{privilege_status['process']['total']}"
            )

            # 记录详细的权限获取情况（调试用）
            logger.debug("详细权限获取情况:")
            for priv_name, result in privilege_details.items():
                status = "✅" if result["success"] else "❌"
                logger.debug(f"  {priv_name}: {status}")
                if not result["success"] and result.get("error_message"):
                    logger.debug(f"    失败原因: {result['error_message']}")

            # 获取管理员状态
            is_admin = self.check_admin_rights()

            # 评估运行能力
            total_core = privilege_status["core"]["acquired"]
            total_enhanced = privilege_status["enhanced"]["acquired"]
            total_process = privilege_status["process"]["acquired"]

            if total_core == 0 and total_enhanced == 0 and total_process == 0:
                logger.warning("未能获取任何有效权限，所有高级功能将受限")
                if not is_admin:
                    logger.warning("建议以管理员身份运行程序以获得更好的功能体验")
            elif total_core == 0:
                logger.warning("未能获取核心权限，内存清理功能将受限")
            elif total_process == 0:
                logger.warning("未能获取进程管理权限，进程优先级设置功能可能受限")

            return privilege_status

        except Exception as e:
            logger.error(f"权限提升过程出现严重错误: {str(e)}")
            # 默认所有功能不可用
            self.available_functions = {key: False for key in self.available_functions}
            return {"core": {"acquired": 0}, "enhanced": {"acquired": 0}, "process": {"acquired": 0}}

    def _request_single_privilege(self, hToken, privilege_name):
        """请求单个权限并返回详细结果"""
        result = {"name": privilege_name, "success": False, "error_code": None, "error_message": None}

        try:
            # 查找权限ID
            privilege_id = win32security.LookupPrivilegeValue(None, privilege_name)

            # 创建权限结构
            new_privilege = [(privilege_id, win32security.SE_PRIVILEGE_ENABLED)]

            # 应用权限
            win32security.AdjustTokenPrivileges(hToken, False, new_privilege)

            # 检查是否真正成功
            error_code = win32api.GetLastError()
            result["error_code"] = error_code

            if error_code == 0:
                result["success"] = True
                logger.debug(f"成功获取权限: {privilege_name}")
            else:
                if error_code == 1300:  # ERROR_NOT_ALL_ASSIGNED
                    result["error_message"] = "权限不足，通常只有系统进程才能获取此权限"
                    logger.debug(f"无法获取权限 {privilege_name}: 权限不足 (ERROR_NOT_ALL_ASSIGNED)")
                else:
                    result["error_message"] = f"错误码: {error_code}"
                    logger.warning(f"无法获取权限 {privilege_name}: 错误码 {error_code}")

        except Exception as e:
            result["error_message"] = str(e)
            logger.debug(f"请求权限 {privilege_name} 出现异常: {str(e)}")

        return result

    def check_admin_rights(self):
        """检查当前进程是否拥有管理员权限"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def request_admin_rights(self):
        """请求提升为管理员权限（此函数需谨慎使用，可能导致程序重启）"""
        try:
            if not self.check_admin_rights():
                # 获取当前可执行文件路径
                executable = sys.executable
                # 重新以管理员身份启动
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", executable, " ".join(sys.argv), None, 1  # SW_SHOWNORMAL
                )
                # 退出当前进程
                sys.exit(0)
            return True
        except Exception as e:
            logger.error(f"请求管理员权限失败: {str(e)}")
            return False

    def has_privilege(self, privilege_type):
        """
        检查是否具有指定类型的权限

        Args:
            privilege_type: 权限类型字符串

        Returns:
            bool: 是否具有该权限
        """
        return self.available_functions.get(privilege_type, False)

    def get_privilege_summary(self):
        """获取权限状态摘要"""
        summary = {
            "is_admin": self.check_admin_rights(),
            "available_functions": self.available_functions.copy(),
            "privilege_status": getattr(self, "privilege_status", None),
        }

        # 添加诊断建议
        recommendations = []

        if not summary["is_admin"]:
            recommendations.append("建议以管理员身份运行程序以获得更多权限")

        if not self.available_functions.get("set_process_io_priority", False):
            recommendations.append("缺少进程I/O优先级设置权限，某些优化功能可能受限")

        if not self.available_functions.get("debug_other_processes", False):
            recommendations.append("缺少调试权限，无法优化受保护的系统进程")

        if not self.available_functions.get("trim_all_processes", False):
            recommendations.append("缺少内存清理权限，内存清理功能将受限")

        summary["recommendations"] = recommendations

        return summary

    def debug_privilege_constants(self):
        """调试方法：显示权限常量的实际值"""
        logger.debug("权限常量值:")
        logger.debug(f"  SE_DEBUG_NAME = '{win32security.SE_DEBUG_NAME}'")
        logger.debug(f"  SE_INCREASE_QUOTA_NAME = '{win32security.SE_INCREASE_QUOTA_NAME}'")
        logger.debug(f"  SE_INC_WORKING_SET_NAME = '{win32security.SE_INC_WORKING_SET_NAME}'")
        logger.debug(f"  SE_MANAGE_VOLUME_NAME = '{win32security.SE_MANAGE_VOLUME_NAME}'")

    def log_privilege_status(self):
        """记录当前权限状态到日志"""
        summary = self.get_privilege_summary()

        logger.info(f"权限管理器状态:")
        logger.info(f"  管理员权限: {'✅ 是' if summary['is_admin'] else '❌ 否'}")

        # 功能权限状态
        function_status = []
        for func_name, available in summary["available_functions"].items():
            status = "✅" if available else "❌"
            function_status.append(f"    {func_name}: {status}")

        logger.info(f"  功能权限:")
        for status in function_status:
            logger.info(status)

        # 权限统计
        if summary["privilege_status"]:
            ps = summary["privilege_status"]
            logger.info(
                f"  权限统计: 核心({ps['core']['acquired']}/{ps['core']['total']}) "
                f"增强({ps['enhanced']['acquired']}/{ps['enhanced']['total']}) "
                f"进程({ps['process']['acquired']}/{ps['process']['total']})"
            )

        # 建议
        if summary["recommendations"]:
            logger.info("  建议:")
            for rec in summary["recommendations"]:
                logger.info(f"    • {rec}")
        else:
            logger.info("  ✅ 权限状态良好")

        # 调试模式下显示权限常量值
        if logger.level == 10:  # DEBUG level
            self.debug_privilege_constants()


# 单例实例获取函数
_privilege_manager = None


def get_privilege_manager():
    """获取Windows权限管理器单例"""
    global _privilege_manager
    if _privilege_manager is None:
        _privilege_manager = WindowsPrivilegeManager()
    return _privilege_manager
