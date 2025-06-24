<div align="center">

# ACE-KILLER

<img src="https://socialify.git.ci/Cassianvale/ACE-KILLER/image?font=Jost&forks=1&issues=1&name=1&pattern=Plus&stargazers=1&theme=Dark" alt="ACE-KILLER" width="640" height="320" />

✨ _游戏反作弊进程管理工具，专为无畏契约、三角洲行动等使用 ACE 反作弊的游戏设计_ ✨

<!-- 项目状态徽章 -->
<div>
    <img alt="platform" src="https://img.shields.io/badge/Platform-Windows-blue?style=flat-square&logo=windows">
    <img alt="python" src="https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python&logoColor=white">
    <img alt="license" src="https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square&logo=gnu">
    <img alt="version" src="https://img.shields.io/github/v/release/Cassianvale/ACE-KILLER?style=flat-square&color=orange&logo=github">
</div>

<div>
    <img alt="total downloads" src="https://img.shields.io/github/downloads/Cassianvale/ACE-KILLER/total?style=for-the-badge&label=%E6%80%BB%E4%B8%8B%E8%BD%BD%E6%AC%A1%E6%95%B0&color=success">
    <img alt="latest release downloads" src="https://img.shields.io/github/downloads/Cassianvale/ACE-KILLER/latest/total?style=for-the-badge&label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC%E4%B8%8B%E8%BD%BD&color=blue">
</div>
<br/>


<div align="left">

> ## ⚠️ 重要声明
> 🚨 本项目所有代码均通过**标准Windows API和脚本实现**  
> 🔒 不涉及**任何反作弊内核修改、注入或破解**，仅对进程资源进行合理管理  
> ⚖️ 所有功能基于Windows系统标准权限管理，**未使用任何第三方破解工具**  
> 🎯 本项目仅优化系统资源分配，**不干扰反作弊程序的正常检测逻辑，所有操作均合理合法**  
> **❗ 最后，如果您因使用本工具而遇到任何被检测的问题，请优先检查自己是否使用了其他可能导致封号的软件！**

</div>
</div>

## ✅ 功能特性

- 🛡️ 自动关闭`ACE-Tray.exe`反作弊安装询问弹窗
- 🚀 自动优化`SGuard64.exe`扫盘进程，降低 CPU 占用
- 🗑️ 支持一键启动/停止反作弊进程，卸载/删除 ACE 反作弊服务
- 🐻 支持自定义进程性能模式
- 🧹 内存清理根据作者`H3d9`编写的 [Memory Cleaner](https://github.com/H3d9/memory_cleaner) 进行重构
- 📱 支持 Windows 系统通知
- 🔄 支持开机静默自启
- 💻 系统托盘常驻运行
- 🌓 支持明暗主题切换

## 🚀 如何使用

1. [点击下载最新版本.zip压缩包](https://github.com/Cassianvale/ACE-KILLER/releases) 👈
2. 解压后运行`ACE-KILLER.exe`
3. 程序将在系统托盘显示图标
4. 右键点击托盘图标可以：
   - 👁️ 查看程序状态
   - 🔔 启用/禁用 Windows 通知
   - 🔄 设置开机自启动
   - ⚙️ 配置游戏监控
   - 📁 打开配置目录
   - 🚪 退出程序

## 🏠 项目展示

<div align="center">
  <img src="https://raw.githubusercontent.com/Cassianvale/ACE-KILLER/main/assets/image/1.png" width="45%" alt="应用界面预览">
  <img src="https://raw.githubusercontent.com/Cassianvale/ACE-KILLER/main/assets/image/2.png" width="45%" alt="进程监控界面预览1">
</div>

<div align="center">
  <img src="https://raw.githubusercontent.com/Cassianvale/ACE-KILLER/main/assets/image/3.png" width="45%" alt="内存清理界面预览">
  <img src="https://raw.githubusercontent.com/Cassianvale/ACE-KILLER/main/assets/image/4.png" width="45%" alt="设置界面预览">
</div>

<div align="center">
  <img src="https://raw.githubusercontent.com/Cassianvale/ACE-KILLER/main/assets/image/5.png" width="80%" alt="进程监控界面预览2">
</div>

## 😶‍🌫️ 进程模式策略

| 性能模式    | CPU 优先级             | 效能节流     | CPU 核心绑定   |
| ----------- | ---------------------- | ------------ | ------------ |
| 🌱 效能模式 | 低优先级(IDLE)         | 启用节流     | 最后一个核心 |
| 🍉 正常模式 | **正常优先级(NORMAL)** | **禁用节流** | 所有核心     |
| 🚀 高性能   | 高优先级(HIGH)         | 禁用节流     | 所有核心     |
| 🔥 最大性能 | 实时优先级(REALTIME)   | 禁用节流     | 所有核心     |

## ⚙️ ACE Services 说明

- **AntiCheatExpert Service**：用户模式，由 `SvGuard64.exe` 控制的游戏交互的服务，也是在服务概览 (services.msc) 中看到的唯一服务
- **AntiCheatExpert Protection**：反作弊组件
- **ACE-BASE**：内核模式，加载系统驱动程序
- **ACE-GAME**：内核模式，加载系统驱动程序

## ⚠️ 注意事项

- 本程序需要管理员权限运行
- 使用过程中如遇到问题，日志文件位于 `%USERPROFILE%\.ace-killer\logs\` 目录

## 📢 免责声明

- **本项目仅供个人学习和研究使用，禁止用于任何商业或非法目的。**
- **开发者保留对本项目的最终解释权。**
- **使用者在使用本项目时，必须严格遵守 `中华人民共和国（含台湾省）` 以及使用者所在地区的法律法规。禁止将本项目用于任何违反相关法律法规的活动。**
- **使用者应自行承担因使用本项目所产生的任何风险和责任。开发者不对因使用本项目而导致的任何直接或间接损失承担责任。**
- **开发者不对本项目所提供的服务或内容的准确性、完整性或适用性作出任何明示或暗示的保证。使用者应自行评估使用本项目的风险。**
- **若使用者发现任何商家或第三方以本项目进行收费或从事其他商业行为，所产生的任何问题或后果与本项目及开发者无关。使用者应自行承担相关风险。**

## 📜 许可证

- **本项目采用 `GNU General Public License v3.0`** - 详见 [LICENSE](LICENSE) 文件
