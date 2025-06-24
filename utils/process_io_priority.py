#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
进程I/O优先级设置模块
"""

import ctypes
import time
import threading
from typing import Optional, Tuple, Dict, Any
from ctypes import wintypes
import psutil
from utils.logger import logger
from win32api import OpenProcess, CloseHandle
from win32con import PROCESS_ALL_ACCESS
from win32process import (
    SetPriorityClass, 
    IDLE_PRIORITY_CLASS, 
    BELOW_NORMAL_PRIORITY_CLASS, 
    ABOVE_NORMAL_PRIORITY_CLASS,
    NORMAL_PRIORITY_CLASS,
    HIGH_PRIORITY_CLASS,
    REALTIME_PRIORITY_CLASS
)

# 导入权限管理器
from utils.privilege_manager import get_privilege_manager

# =============================================================================
# Windows API 常量和结构体定义
# =============================================================================

# 进程访问权限
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_ALL_ACCESS = 0x1F0FFF

# ProcessInformationClass 枚举
ProcessIoPriority = 33

# 效能模式相关常量
PROCESS_POWER_THROTTLING_INFORMATION = 4
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1


class IO_PRIORITY_HINT:
    """I/O优先级枚举"""
    IoPriorityVeryLow = 0    # 最低优先级
    IoPriorityLow = 1        # 低优先级
    IoPriorityNormal = 2     # 正常优先级(默认)
    IoPriorityCritical = 3   # 关键优先级


class PERFORMANCE_MODE:
    """性能模式枚举"""
    ECO_MODE = 0              # 效能模式（低优先级，单核心）
    NORMAL_MODE = 1           # 正常模式（正常优先级，所有核心）
    HIGH_PERFORMANCE = 2      # 高性能模式（高优先级，所有核心）
    MAXIMUM_PERFORMANCE = 3   # 最大性能模式（实时优先级，所有核心）


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    """进程功耗节流状态结构体"""
    _fields_ = [
        ("Version", wintypes.DWORD),
        ("ControlMask", wintypes.DWORD),
        ("StateMask", wintypes.DWORD)
    ]


# =============================================================================
# 性能模式配置映射
# =============================================================================

class PerformanceModeConfig:
    """性能模式配置类，根据UI要求定义各模式的设置"""
    
    # 性能模式到CPU优先级的映射
    CPU_PRIORITY_MAP = {
        PERFORMANCE_MODE.ECO_MODE: IDLE_PRIORITY_CLASS,           # 效能模式：低优先级
        PERFORMANCE_MODE.NORMAL_MODE: NORMAL_PRIORITY_CLASS,      # 正常模式：正常优先级  
        PERFORMANCE_MODE.HIGH_PERFORMANCE: HIGH_PRIORITY_CLASS,   # 高性能：高优先级
        PERFORMANCE_MODE.MAXIMUM_PERFORMANCE: REALTIME_PRIORITY_CLASS  # 最大性能：实时优先级
    }
    
    # 性能模式到I/O优先级的映射
    IO_PRIORITY_MAP = {
        PERFORMANCE_MODE.ECO_MODE: IO_PRIORITY_HINT.IoPriorityLow,         # 效能模式：低I/O优先级
        PERFORMANCE_MODE.NORMAL_MODE: IO_PRIORITY_HINT.IoPriorityNormal,   # 正常模式：正常I/O优先级
        PERFORMANCE_MODE.HIGH_PERFORMANCE: IO_PRIORITY_HINT.IoPriorityNormal,  # 高性能：正常I/O优先级
        PERFORMANCE_MODE.MAXIMUM_PERFORMANCE: IO_PRIORITY_HINT.IoPriorityCritical  # 最大性能：最高I/O优先级
    }
    
    # 性能模式到CPU亲和性策略的映射
    CPU_AFFINITY_MAP = {
        PERFORMANCE_MODE.ECO_MODE: "last_core",        # 效能模式：绑定到最后一个核心
        PERFORMANCE_MODE.NORMAL_MODE: "all_cores",     # 正常模式：绑定所有核心
        PERFORMANCE_MODE.HIGH_PERFORMANCE: "all_cores", # 高性能：绑定所有核心
        PERFORMANCE_MODE.MAXIMUM_PERFORMANCE: "all_cores"  # 最大性能：绑定所有核心
    }
    
    # 性能模式文本描述
    MODE_DESCRIPTIONS = {
        PERFORMANCE_MODE.ECO_MODE: "效能模式",
        PERFORMANCE_MODE.NORMAL_MODE: "正常模式", 
        PERFORMANCE_MODE.HIGH_PERFORMANCE: "高性能模式",
        PERFORMANCE_MODE.MAXIMUM_PERFORMANCE: "最大性能模式"
    }
    
    # CPU优先级名称映射
    PRIORITY_NAMES = {
        IDLE_PRIORITY_CLASS: "低优先级(IDLE)",
        BELOW_NORMAL_PRIORITY_CLASS: "低于正常",
        NORMAL_PRIORITY_CLASS: "正常优先级",
        ABOVE_NORMAL_PRIORITY_CLASS: "高于正常",
        HIGH_PRIORITY_CLASS: "高优先级",
        REALTIME_PRIORITY_CLASS: "实时优先级"
    }


# =============================================================================
# 进程I/O优先级管理器
# =============================================================================

class ProcessIoPriorityManager:
    """处理进程I/O优先级管理的类"""
    
    def __init__(self):
        """初始化进程优先级管理器"""
        # 加载Windows API
        self.ntdll = ctypes.WinDLL('ntdll.dll')
        self.kernel32 = ctypes.WinDLL('kernel32.dll')
        
        # 获取权限管理器
        self.privilege_manager = get_privilege_manager()
        
        # 性能配置
        self.config = PerformanceModeConfig()
        
        # 初始化Windows API函数
        self._init_api_functions()
        
        # 检查权限
        self._check_privileges()
        
        # 缓存系统CPU核心数
        self._cpu_count = psutil.cpu_count(logical=True)
    
    def _init_api_functions(self):
        """初始化Windows API函数"""
        # 定义NtSetInformationProcess函数
        self.NtSetInformationProcess = self.ntdll.NtSetInformationProcess
        self.NtSetInformationProcess.argtypes = [
            wintypes.HANDLE,    # ProcessHandle
            ctypes.c_int,       # ProcessInformationClass
            ctypes.c_void_p,    # ProcessInformation
            ctypes.c_ulong      # ProcessInformationLength
        ]
        self.NtSetInformationProcess.restype = ctypes.c_ulong
    
    def _check_privileges(self):
        """检查并记录权限状态"""
        self.privilege_manager.log_privilege_status()
        
        if not self.privilege_manager.has_privilege("set_process_io_priority"):
            logger.warning("缺少设置进程I/O优先级的权限，某些操作可能失败")
            if not self.privilege_manager.check_admin_rights():
                logger.warning("建议以管理员身份运行程序以获得完整的进程管理权限")
    
    def set_process_io_priority(self, process_id: int, priority: int = None, performance_mode: int = PERFORMANCE_MODE.ECO_MODE) -> bool:
        """
        根据性能模式设置指定进程的完整优化
        
        Args:
            process_id: 进程ID
            priority: I/O优先级（如果为None，则根据性能模式自动确定）
            performance_mode: 性能模式
            
        Returns:
            bool: 操作是否成功
        """
        try:
            # 根据性能模式自动确定I/O优先级（如果未指定）
            if priority is None:
                priority = self.config.IO_PRIORITY_MAP.get(performance_mode, IO_PRIORITY_HINT.IoPriorityLow)
            
            mode_text = self.config.MODE_DESCRIPTIONS.get(performance_mode, f"未知模式({performance_mode})")
            logger.debug(f"开始优化进程(PID={process_id}) - {mode_text}")
            
            # 执行优化步骤
            results = {}
            
            # 1. 设置I/O优先级
            results['io'] = self._set_io_priority(process_id, priority)
            if not results['io']:
                logger.error(f"设置进程(PID={process_id})I/O优先级失败")
                return False
            
            # 2. 设置CPU优先级
            results['cpu'] = self._set_cpu_priority(process_id, performance_mode)
            
            # 3. 设置CPU亲和性
            results['affinity'] = self._set_cpu_affinity_by_mode(process_id, performance_mode)
            
            # 4. 设置功耗节流模式
            results['power'] = self._set_power_throttling(process_id, performance_mode)
            
            # 记录结果
            success_count = sum(1 for success in results.values() if success)
            logger.debug(f"进程优化完成(PID={process_id}): {success_count}/4 项成功 - I/O={results['io']}, CPU={results['cpu']}, 亲和性={results['affinity']}, 功耗={results['power']} ({mode_text})")
            
            # 只要I/O优先级设置成功就认为操作成功
            return results['io']
            
        except Exception as e:
            logger.error(f"设置进程优化时发生错误: {str(e)}")
            return False
    
    def _set_io_priority(self, process_id: int, priority: int) -> bool:
        """设置I/O优先级"""
        process_handle = None
        try:
            # 打开进程句柄
            process_handle = self.kernel32.OpenProcess(
                PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION,
                False,
                process_id
            )
            
            if not process_handle:
                error_code = ctypes.GetLastError()
                self._log_process_error(process_id, error_code, "打开进程")
                return False
            
            # 设置优先级值
            priority_value = ctypes.c_int(priority)
            
            # 调用API设置I/O优先级
            status = self.NtSetInformationProcess(
                process_handle,
                ProcessIoPriority,
                ctypes.byref(priority_value),
                ctypes.sizeof(priority_value)
            )
            
            if status != 0:
                error_message = self._get_ntstatus_message(status)
                logger.error(f"设置进程(PID={process_id})I/O优先级失败，{error_message}")
                return False
            
            logger.debug(f"成功设置进程(PID={process_id})的I/O优先级为: {priority}")
            return True
            
        except Exception as e:
            logger.error(f"设置I/O优先级时发生错误: {str(e)}")
            return False
        finally:
            if process_handle:
                self.kernel32.CloseHandle(process_handle)
    
    def _set_cpu_priority(self, process_id: int, performance_mode: int) -> bool:
        """根据性能模式设置CPU优先级"""
        try:
            # 获取对应的优先级类
            priority_class = self.config.CPU_PRIORITY_MAP.get(performance_mode, NORMAL_PRIORITY_CLASS)
            
            # 实时优先级警告
            if performance_mode == PERFORMANCE_MODE.MAXIMUM_PERFORMANCE:
                logger.warning(f"正在为进程(PID={process_id})设置实时优先级，这可能影响系统稳定性")
            
            # 打开进程并设置优先级
            handle = OpenProcess(PROCESS_ALL_ACCESS, False, process_id)
            if not handle:
                logger.error(f"无法打开进程(PID={process_id})用于设置CPU优先级")
                return False
            
            try:
                SetPriorityClass(handle, priority_class)
                priority_name = self.config.PRIORITY_NAMES.get(priority_class, f"未知({priority_class})")
                logger.debug(f"成功设置进程(PID={process_id})的CPU优先级为: {priority_name}")
                return True
            finally:
                CloseHandle(handle)
                
        except Exception as e:
            logger.error(f"设置CPU优先级时发生错误: {str(e)}")
            return False
    
    def _set_cpu_affinity_by_mode(self, process_id: int, performance_mode: int) -> bool:
        """根据性能模式设置CPU亲和性"""
        try:
            affinity_strategy = self.config.CPU_AFFINITY_MAP.get(performance_mode, "all_cores")
            
            if self._cpu_count <= 1:
                logger.debug(f"系统只有一个核心，跳过CPU亲和性设置(PID={process_id})")
                return True
            
            proc = psutil.Process(process_id)
            
            if affinity_strategy == "last_core":
                # 效能模式：绑定到最后一个核心
                last_core = self._cpu_count - 1
                proc.cpu_affinity([last_core])
                logger.debug(f"成功设置进程(PID={process_id})的CPU亲和性到核心{last_core}")
            else:  # "all_cores"
                # 其他模式：绑定到所有核心
                all_cores = list(range(self._cpu_count))
                proc.cpu_affinity(all_cores)
                logger.debug(f"成功设置进程(PID={process_id})的CPU亲和性到所有核心")
            
            return True
            
        except Exception as e:
            logger.error(f"设置CPU亲和性时发生错误: {str(e)}")
            return False
    
    def _set_power_throttling(self, process_id: int, performance_mode: int) -> bool:
        """设置进程的功耗节流模式"""
        process_handle = None
        try:
            # 打开进程句柄
            process_handle = self.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, process_id)
            if not process_handle:
                logger.error(f"无法打开进程(PID={process_id})句柄用于设置功耗模式")
                return False
            
            # 创建功耗节流状态结构体
            throttling_state = PROCESS_POWER_THROTTLING_STATE()
            throttling_state.Version = 1
            throttling_state.ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
            
            # 根据性能模式设置节流状态
            if performance_mode == PERFORMANCE_MODE.ECO_MODE:
                # 效能模式：启用节流
                throttling_state.StateMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
                mode_text = "效能模式(启用节流)"
            else:
                # 正常模式、高性能模式、最大性能模式：禁用节流
                throttling_state.StateMask = 0
                if performance_mode == PERFORMANCE_MODE.NORMAL_MODE:
                    mode_text = "正常模式(禁用节流)"
                elif performance_mode == PERFORMANCE_MODE.HIGH_PERFORMANCE:
                    mode_text = "高性能模式(禁用节流)"
                else:  # MAXIMUM_PERFORMANCE
                    mode_text = "最大性能模式(禁用节流)"
            
            # 调用API设置功耗模式
            SetProcessInformation = self.kernel32.SetProcessInformation
            result = SetProcessInformation(
                process_handle,
                PROCESS_POWER_THROTTLING_INFORMATION,
                ctypes.byref(throttling_state),
                ctypes.sizeof(throttling_state)
            )
            
            if result:
                logger.debug(f"成功将进程(PID={process_id})设置为{mode_text}")
                return True
            else:
                error = self.kernel32.GetLastError()
                logger.error(f"设置进程功耗模式失败，错误码: {error}")
                return False
                
        except Exception as e:
            logger.error(f"设置进程功耗模式时发生异常: {str(e)}")
            return False
        finally:
            if process_handle:
                self.kernel32.CloseHandle(process_handle)
    
    def _log_process_error(self, process_id: int, error_code: int, operation: str):
        """记录进程操作错误的详细信息"""
        logger.error(f"无法{operation}(PID={process_id})，错误码: {error_code}")
        
        if error_code == 5:  # ERROR_ACCESS_DENIED
            logger.error(f"进程(PID={process_id})访问被拒绝，可能是系统进程或权限不足")
            if not self.privilege_manager.check_admin_rights():
                logger.error("建议以管理员身份运行程序")
        elif error_code == 87:  # ERROR_INVALID_PARAMETER
            logger.error(f"进程(PID={process_id})可能已经退出")
    
    def _get_ntstatus_message(self, status_code: int) -> str:
        """获取NTSTATUS错误码的说明"""
        ntstatus_messages = {
            0x00000000: "STATUS_SUCCESS - 操作成功",
            0xC0000061: "STATUS_PRIVILEGE_NOT_HELD - 权限不足，需要管理员权限",
            0xC0000005: "STATUS_ACCESS_DENIED - 访问被拒绝",
            0xC0000008: "STATUS_INVALID_HANDLE - 无效的句柄",
            0xC000000D: "STATUS_INVALID_PARAMETER - 无效的参数",
            0xC0000022: "STATUS_ACCESS_DENIED - 访问被拒绝",
        }
        return ntstatus_messages.get(status_code, f"未知错误码: 0x{status_code:08x}")
    
    def set_process_io_priority_by_name(self, process_name: str, priority: int = None, performance_mode: int = PERFORMANCE_MODE.ECO_MODE) -> Tuple[int, int]:
        """
        通过进程名称设置所有匹配进程的优化
        
        Args:
            process_name: 进程名称
            priority: I/O优先级（如果为None，则根据性能模式自动确定）
            performance_mode: 性能模式
            
        Returns:
            tuple: (成功设置的进程数, 总尝试的进程数)
        """
        success_count = 0
        total_count = 0
        
        try:
            # 查找所有匹配的进程
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'].lower() == process_name.lower():
                    total_count += 1
                    if self.set_process_io_priority(proc.info['pid'], priority, performance_mode):
                        success_count += 1
            
            if total_count == 0:
                logger.warning(f"未找到名为 {process_name} 的进程")
            else:
                mode_text = self.config.MODE_DESCRIPTIONS.get(performance_mode, f"未知模式({performance_mode})")
                logger.debug(f"已为 {success_count}/{total_count} 个名为 {process_name} 的进程设置优化 ({mode_text})")
            
            return (success_count, total_count)
            
        except Exception as e:
            logger.error(f"通过名称设置进程优化时发生错误: {str(e)}")
            return (success_count, total_count)
    
    def get_process_info(self, process_id: int) -> Optional[Dict[str, Any]]:
        """获取进程信息"""
        try:
            proc = psutil.Process(process_id)
            return {
                'pid': proc.pid,
                'name': proc.name(),
                'create_time': proc.create_time(),
                'cpu_percent': proc.cpu_percent(interval=0.1),
                'memory_percent': proc.memory_percent(),
                'status': proc.status()
            }
        except Exception as e:
            logger.error(f"获取进程信息失败, PID={process_id}: {str(e)}")
            return None


# =============================================================================
# 自动优化服务
# =============================================================================

class ProcessIoPriorityService:
    """自动设置进程I/O优先级的服务类"""
    
    def __init__(self, config_manager):
        """初始化I/O优先级服务"""
        self.config_manager = config_manager
        self.io_manager = get_io_priority_manager()
        self.running = False
        self.thread = None
        self.check_interval = 30  # 检查间隔，单位秒
        self.auto_optimize_enabled = True  # 自动优化开关
    
    def start_service(self) -> bool:
        """启动I/O优先级服务"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._service_loop, daemon=True)
            self.thread.start()
            return True
        return False
    
    def stop_service(self) -> bool:
        """停止I/O优先级服务"""
        if self.running:
            self.running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(1.0)
            return True
        return False
    
    def _service_loop(self):
        """服务主循环"""
        while self.running:
            try:
                if self.auto_optimize_enabled:
                    self._check_and_optimize_processes()
            except Exception as e:
                logger.error(f"I/O优先级服务出错: {str(e)}")
            
            # 分段睡眠，便于及时响应停止信号
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def _check_and_optimize_processes(self):
        """检查并优化指定进程"""
        processes_to_optimize = self.config_manager.io_priority_processes
        if not processes_to_optimize:
            return
        
        total_processes = 0
        successful_processes = 0
        
        for proc_config in processes_to_optimize:
            if not isinstance(proc_config, dict) or 'name' not in proc_config:
                continue
            
            process_name = proc_config['name']
            performance_mode = proc_config.get('performance_mode', PERFORMANCE_MODE.ECO_MODE)
            
            # 根据性能模式自动确定I/O优先级
            success, count = self.io_manager.set_process_io_priority_by_name(
                process_name, 
                priority=None,  # 自动确定优先级
                performance_mode=performance_mode
            )
            total_processes += count
            successful_processes += success
        
        if total_processes > 0:
            logger.debug(f"自动优化完成: 已处理 {successful_processes}/{total_processes} 个进程")


# =============================================================================
# 单例模式管理器
# =============================================================================

_io_priority_manager = None
_io_priority_service = None

def get_io_priority_manager() -> ProcessIoPriorityManager:
    """获取ProcessIoPriorityManager单例"""
    global _io_priority_manager
    if _io_priority_manager is None:
        _io_priority_manager = ProcessIoPriorityManager()
    return _io_priority_manager

def get_io_priority_service(config_manager=None) -> Optional['ProcessIoPriorityService']:
    """获取ProcessIoPriorityService单例"""
    global _io_priority_service
    if _io_priority_service is None and config_manager is not None:
        _io_priority_service = ProcessIoPriorityService(config_manager)
    return _io_priority_service 