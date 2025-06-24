#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
进程监控核心模块
"""

import os
import queue
import threading
import time
import psutil
from utils.logger import logger
from win32api import OpenProcess
from win32con import PROCESS_ALL_ACCESS
from win32process import SetPriorityClass, IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS
import ctypes
from ctypes import wintypes
import win32service


# 定义Windows API常量和结构体
PROCESS_POWER_THROTTLING_INFORMATION = 4
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
POWER_THROTTLING_PROCESS_ENABLE = 0x1
POWER_THROTTLING_PROCESS_DISABLE = 0x2

class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.DWORD),
        ("ControlMask", wintypes.DWORD),
        ("StateMask", wintypes.DWORD)
    ]


class GameProcessMonitor:
    """反作弊进程监控类"""
    
    def __init__(self, config_manager):
        """
        初始化反作弊进程监控器
        
        Args:
            config_manager: 配置管理器对象
        """
        self.config_manager = config_manager
        self.anticheat_name = "ACE-Tray.exe"  # 反作弊进程名称
        self.scanprocess_name = "SGuard64.exe"  # 扫描进程名称
        
        # 反作弊服务列表
        self.anticheat_services = {
            "AntiCheatExpert Service": {"exists": None, "status": None, "start_type": None},
            "AntiCheatExpert Protection": {"exists": None, "status": None, "start_type": None},
            "ACE-BASE": {"exists": None, "status": None, "start_type": None},
            "ACE-GAME": {"exists": None, "status": None, "start_type": None}
        }
        
        self.running = False  # 监控线程运行标记，初始为False
        self.process_cache = {}  # 进程缓存
        self.cache_timeout = 5  # 缓存超时时间（秒）
        self.last_cache_refresh = 0  # 上次缓存刷新时间
        self.anticheat_killed = False  # 终止ACE进程标记
        self.scanprocess_optimized = False  # 优化SGuard64进程标记
        self.message_queue = queue.Queue()  # 消息队列，用于在线程间传递状态信息
        
        # 设置自身进程优先级
        self._set_self_priority()
        
        # 创建专门用于监控进程的线程
        self.sguard_monitor_thread = None
        self.acetray_monitor_thread = None
    
    def _set_self_priority(self):
        """设置自身进程优先级为低于正常"""
        try:
            handle = OpenProcess(PROCESS_ALL_ACCESS, False, os.getpid())
            SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)
            logger.debug("已设置程序优先级为低于正常")
        except Exception as e:
            logger.error(f"设置自身进程优先级失败: {str(e)}")
    
    @property
    def show_notifications(self):
        """获取通知状态"""
        return self.config_manager.show_notifications
    
    @property
    def auto_start(self):
        """获取自启动状态"""
        return self.config_manager.auto_start
    
    def refresh_process_cache(self, force=False):
        """
        刷新进程缓存，确保缓存中的进程信息是最新的
        
        Args:
            force (bool): 是否强制刷新缓存
        """
        current_time = time.time()
        if force or (current_time - self.last_cache_refresh) >= self.cache_timeout:
            self.process_cache.clear()
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name']:
                        self.process_cache[proc.info['name'].lower()] = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            self.last_cache_refresh = current_time
    
    def is_process_running(self, process_name):
        """
        检查进程是否在运行
        
        Args:
            process_name (str): 进程名称
            
        Returns:
            psutil.Process or None: 进程对象，未找到则返回None
        """
        if not process_name:
            return None
            
        process_name_lower = process_name.lower()
        
        # 先从缓存中查找
        if process_name_lower in self.process_cache:
            proc = self.process_cache[process_name_lower]
            try:
                if proc.is_running():
                    return proc
                else:
                    del self.process_cache[process_name_lower]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                del self.process_cache[process_name_lower]
        
        # 缓存中没有找到，则遍历所有进程
        try:
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == process_name_lower:
                        self.process_cache[process_name_lower] = proc
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        
        return None
    
    def check_service_status(self, service_name):
        """
        检查Windows服务的运行状态
        
        Args:
            service_name (str): 服务名称
            
        Returns:
            tuple: (是否存在, 运行状态, 启动类型)
                运行状态: 'running', 'stopped', 'paused', 'start_pending', 
                         'stop_pending', 'continue_pending', 'pause_pending', 'unknown'
                启动类型: 'auto', 'manual', 'disabled', 'unknown'
        """
        # 检查服务缓存，如果服务之前检查过不存在，减少重复检查频率
        if hasattr(self, '_service_cache') and service_name in self._service_cache:
            cache_item = self._service_cache[service_name]
            # 如果服务不存在，且上次检查时间在10分钟内，直接返回缓存结果
            if not cache_item['exists'] and time.time() - cache_item['last_check'] < 600:
                return cache_item['exists'], cache_item['status'], cache_item['start_type']
        
        try:
            status_map = {
                win32service.SERVICE_RUNNING: 'running',
                win32service.SERVICE_STOPPED: 'stopped',
                win32service.SERVICE_PAUSED: 'paused',
                win32service.SERVICE_START_PENDING: 'start_pending',
                win32service.SERVICE_STOP_PENDING: 'stop_pending',
                win32service.SERVICE_CONTINUE_PENDING: 'continue_pending',
                win32service.SERVICE_PAUSE_PENDING: 'pause_pending'
            }
            
            start_type_map = {
                win32service.SERVICE_AUTO_START: 'auto',
                win32service.SERVICE_DEMAND_START: 'manual',
                win32service.SERVICE_DISABLED: 'disabled',
                win32service.SERVICE_BOOT_START: 'boot',
                win32service.SERVICE_SYSTEM_START: 'system'
            }
            
            # 获取服务管理器句柄
            sch_handle = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            
            try:
                # 获取服务句柄
                service_handle = win32service.OpenService(
                    sch_handle, service_name, win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS
                )
                
                try:
                    # 获取服务状态
                    service_status = win32service.QueryServiceStatus(service_handle)
                    status = status_map.get(service_status[1], 'unknown')
                    
                    # 获取服务配置信息
                    service_config = win32service.QueryServiceConfig(service_handle)
                    start_type = start_type_map.get(service_config[1], 'unknown')
                    
                    # 更新缓存
                    if not hasattr(self, '_service_cache'):
                        self._service_cache = {}
                    self._service_cache[service_name] = {
                        'exists': True,
                        'status': status,
                        'start_type': start_type,
                        'last_check': time.time()
                    }
                    
                    return True, status, start_type
                    
                finally:
                    win32service.CloseServiceHandle(service_handle)
            except win32service.error as e:
                # 安全地获取错误码
                error_code = None
                try:
                    # 尝试获取错误码
                    if hasattr(e, 'args') and len(e.args) > 0:
                        error_code = e.args[0]
                    elif hasattr(e, 'winerror'):
                        error_code = e.winerror
                    elif isinstance(e, tuple) and len(e) > 0:
                        error_code = e[0]
                except:
                    error_code = None
                
                # 服务不存在时不记录警告日志，只在初次检查或错误码不是1060时记录
                should_log = True
                if error_code == 1060:  # ERROR_SERVICE_DOES_NOT_EXIST
                    # 如果是服务不存在的错误，检查是否需要记录日志
                    if hasattr(self, '_service_cache') and service_name in self._service_cache:
                        should_log = False
                
                if should_log:
                    logger.debug(f"服务 {service_name} 不存在或无法访问: {str(e)} (错误码: {error_code})")
                
                # 更新缓存
                if not hasattr(self, '_service_cache'):
                    self._service_cache = {}
                self._service_cache[service_name] = {
                    'exists': False,
                    'status': 'unknown',
                    'start_type': 'unknown',
                    'last_check': time.time()
                }
                
                return False, 'unknown', 'unknown'
            finally:
                win32service.CloseServiceHandle(sch_handle)
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"检查服务状态时发生错误: [{error_type}] {error_msg}")
            logger.debug(f"服务名称: {service_name}, 异常详情: {repr(e)}")
            return False, 'unknown', 'unknown'
    
    def monitor_anticheat_service(self):
        """
        监控所有反作弊服务状态
        
        Returns:
            dict: 包含所有服务状态的字典
        """
        service_results = {}
        
        # 遍历所有反作弊服务并检查状态
        for service_name in self.anticheat_services.keys():
            service_exists, status, start_type = self.check_service_status(service_name)
            
            # 记录服务状态
            service_results[service_name] = {
                "exists": service_exists,
                "status": status,
                "start_type": start_type
            }
            
            if service_exists:
                logger.debug(f"反作弊{service_name}服务状态: {status}, 启动类型: {start_type}")
            
            # 更新服务状态缓存
            self.anticheat_services[service_name]["exists"] = service_exists
            self.anticheat_services[service_name]["status"] = status
            self.anticheat_services[service_name]["start_type"] = start_type
        
        return service_results
    
    def kill_process(self, process_name):
        """
        终止进程
        
        Args:
            process_name (str): 进程名称
            
        Returns:
            bool: 是否成功终止进程
        """
        proc = self.is_process_running(process_name)
        if proc:
            try:
                proc.kill()
                logger.debug(f"已终止进程: {process_name}")
                if process_name.lower() in self.process_cache:
                    del self.process_cache[process_name.lower()]
                return True
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.warning(f"终止进程失败: {process_name} - {str(e)}")
        return False
    
    def set_process_priority_and_affinity(self, process_name):
        """
        设置进程优先级和CPU相关性
        
        Args:
            process_name (str): 进程名称
            
        Returns:
            bool: 是否成功设置
        """
        proc = self.is_process_running(process_name)
        if proc:
            try:
                handle = OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
                SetPriorityClass(handle, IDLE_PRIORITY_CLASS)
                
                # 设置CPU亲和性
                cores = psutil.cpu_count(logical=True)
                if cores > 0:
                    small_core = cores - 1
                    proc.cpu_affinity([small_core])
                
                # 设置为效能模式
                self._set_process_eco_qos(proc.pid)
                
                logger.debug(f"优化进程: {process_name}，已设置为效能模式")
                return True
            except Exception as e:
                logger.error(f"优化进程失败: {str(e)}")
        return False
    
    def _set_process_eco_qos(self, pid):
        """
        设置进程为效能模式 (EcoQoS)
        
        Args:
            pid (int): 进程ID
            
        Returns:
            bool: 是否成功设置
        """
        try:
            # 获取SetProcessInformation函数
            SetProcessInformation = ctypes.windll.kernel32.SetProcessInformation
            
            # 打开进程
            process_handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_ALL_ACCESS, False, pid
            )
            
            if not process_handle:
                logger.error(f"无法打开进程(PID: {pid})句柄")
                return False
            
            # 创建并初始化PROCESS_POWER_THROTTLING_STATE结构体
            throttling_state = PROCESS_POWER_THROTTLING_STATE()
            throttling_state.Version = 1
            throttling_state.ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
            throttling_state.StateMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
            
            # 调用SetProcessInformation设置效能模式
            result = SetProcessInformation(
                process_handle,
                PROCESS_POWER_THROTTLING_INFORMATION,
                ctypes.byref(throttling_state),
                ctypes.sizeof(throttling_state)
            )
            
            # 关闭进程句柄
            ctypes.windll.kernel32.CloseHandle(process_handle)
            
            if result:
                logger.debug(f"成功将进程(PID: {pid})设置为效能模式")
                return True
            else:
                error = ctypes.windll.kernel32.GetLastError()
                logger.error(f"设置进程效能模式失败，错误码: {error}")
                return False
        except Exception as e:
            logger.error(f"设置进程效能模式时发生异常: {str(e)}")
            return False
    
    def add_message(self, message):
        """
        添加消息到队列
        
        Args:
            message (str): 消息内容
        """
        if self.show_notifications:
            self.message_queue.put(message)
    
    def check_process_status(self, process_name):
        """
        检查进程状态，判断是否已被处理
        
        Args:
            process_name (str): 进程名称
            
        Returns:
            tuple: (是否运行, 是否已优化)
        """
        proc = self.is_process_running(process_name)
        if not proc:
            return False, False
            
        # 进程存在，检查是否已优化
        is_optimized = False
        
        if process_name.lower() == self.scanprocess_name.lower():
            try:
                # 检查CPU亲和性（这个不涉及Windows API调用，较为安全）
                cpu_affinity_optimized = False
                try:
                    cpu_affinity = proc.cpu_affinity()
                    cores = psutil.cpu_count(logical=True)
                    expected_core = [cores - 1] if cores > 0 else None
                    
                    # 判断CPU亲和性是否符合优化要求
                    if expected_core is not None:
                        # 只要设置了亲和性，或者亲和性包含了最后一个核心，就认为是优化了
                        if len(cpu_affinity) == 1 or (cores - 1) in cpu_affinity:
                            cpu_affinity_optimized = True
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.debug(f"检查CPU亲和性失败: {str(e)}")
                    # 如果检查失败，给予好处理，假设已优化
                    cpu_affinity_optimized = True
                
                # 检查进程优先级
                priority_optimized = False
                try:
                    # 在Windows上，nice()返回的是进程优先级类
                    priority = proc.nice()
                    # 只要是低优先级就认为是已优化
                    if priority in [IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS]:
                        priority_optimized = True
                    
                    # logger.debug(f"{process_name} 状态检查: 优先级={priority}, 优先级优化={priority_optimized}, CPU亲和性优化={cpu_affinity_optimized}")
                    
                    # 放宽判断标准：只要优先级或CPU亲和性满足一个条件就认为已优化
                    is_optimized = priority_optimized or cpu_affinity_optimized
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.debug(f"检查进程优先级失败: {str(e)}")
                    # 如果检查失败，给予好处理，假设已优化
                    is_optimized = True
                
            except Exception as e:
                logger.error(f"检查进程状态失败: {str(e)}")
                # 如果检查过程出现异常，不要立即判断为未优化，给予好处理
                is_optimized = True
                
        return True, is_optimized
    
    def monitor_acetray_process(self):
        """
        专门监控并终止ACE-Tray.exe进程
        """
        check_counter = 0
        
        while self.running:
            # 每5次循环刷新一次进程缓存
            if check_counter % 5 == 0:
                self.refresh_process_cache()
            check_counter += 1
            
            # 检查ACE-Tray.exe进程是否存在
            ace_proc = self.is_process_running(self.anticheat_name)
            
            if ace_proc:
                if not self.anticheat_killed:
                    logger.debug(f"检测到 {self.anticheat_name} 进程，尝试终止")
                    if self.kill_process(self.anticheat_name):
                        self.anticheat_killed = True
                        self.add_message(f"已终止 {self.anticheat_name} 进程")
                    else:
                        # 如果终止失败，暂时标记为已处理，避免频繁尝试
                        self.anticheat_killed = True
                        logger.warning(f"终止 {self.anticheat_name} 失败")
            else:
                # 进程不存在时重置状态，以便下次检测到时再次处理
                self.anticheat_killed = False
            
            # 降低检测频率，减少CPU使用率
            time.sleep(2)
    
    def monitor_sguard_process(self):
        """
        专门监控并优化SGuard64.exe进程
        """
        check_counter = 0
        
        while self.running:
            # 每5次循环刷新一次进程缓存
            if check_counter % 5 == 0:
                self.refresh_process_cache()
            check_counter += 1
            
            # 检查SGuard64进程是否存在
            scan_running, is_optimized = self.check_process_status(self.scanprocess_name)
            
            if scan_running:
                # 如果进程正在运行，根据优化状态设置全局标志
                if is_optimized:
                    # 如果检测到已优化，直接设置全局标志为True
                    if not self.scanprocess_optimized:
                        logger.debug(f"{self.scanprocess_name} 进程已检测为优化状态")
                        self.scanprocess_optimized = True
                else:
                    # 未优化时尝试优化
                    logger.debug(f"检测到未优化的 {self.scanprocess_name}，尝试优化")
                    if self.set_process_priority_and_affinity(self.scanprocess_name):
                        self.scanprocess_optimized = True
                        self.add_message(f"已优化 {self.scanprocess_name} 进程")
            else:
                # 如果当前没有运行，重置状态以便下次检测到时再次优化
                if self.scanprocess_optimized:
                    self.scanprocess_optimized = False
            
            # 降低检测频率，减少CPU使用率
            time.sleep(2)
    
    def start_monitors(self):
        """启动所有监控线程"""
        self.running = True
        logger.debug("监控程序已启动")
        
        # 启动ACE-Tray专用监控线程
        self.start_acetray_monitor()
        
        # 启动SGuard64专用监控线程
        self.start_sguard_monitor()
        
        # 初始检查反作弊服务状态
        self.monitor_anticheat_service()
    
    def start_acetray_monitor(self):
        """启动专门用于监控ACE-Tray.exe进程的线程"""
        if not self.acetray_monitor_thread or not self.acetray_monitor_thread.is_alive():
            logger.debug(f"启动ACE-Tray专用监控线程")
            self.acetray_monitor_thread = threading.Thread(
                target=self.monitor_acetray_process
            )
            self.acetray_monitor_thread.daemon = True
            self.acetray_monitor_thread.start()
    
    def start_sguard_monitor(self):
        """启动专门用于监控SGuard64.exe进程的线程"""
        if not self.sguard_monitor_thread or not self.sguard_monitor_thread.is_alive():
            logger.debug(f"启动SGuard64专用监控线程")
            self.sguard_monitor_thread = threading.Thread(
                target=self.monitor_sguard_process
            )
            self.sguard_monitor_thread.daemon = True
            self.sguard_monitor_thread.start()
    
    def stop_monitors(self):
        """停止所有监控线程"""
        # 设置运行标志为False，使所有监控线程退出循环
        self.running = False
        # 重置状态
        self.anticheat_killed = False
        self.scanprocess_optimized = False
        logger.debug("监控程序已停止")