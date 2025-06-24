import os
import sys
import subprocess
import shutil
import argparse
import re
from utils.logger import logger

# 设置标准输出编码为UTF-8，解决Windows环境下中文输出问题
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.6及更早版本兼容
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录
root_dir = os.path.dirname(current_dir)

# 设置图标文件路径
icon_path = os.path.join(root_dir, 'assets', 'icon', 'favicon.ico')
assets_icon_dir = os.path.join(root_dir, 'assets', 'icon')

# 检查资源文件是否存在
if not os.path.exists(icon_path):
    logger.error(f"图标文件不存在: {icon_path}")
    sys.exit(1)

if not os.path.exists(assets_icon_dir):
    logger.error(f"图标资源目录不存在: {assets_icon_dir}")
    sys.exit(1)

logger.info(f"图标文件路径: {icon_path}")
logger.info(f"图标资源目录: {assets_icon_dir}")

# 列出要包含的图标资源文件
icon_files = [f for f in os.listdir(assets_icon_dir) if os.path.isfile(os.path.join(assets_icon_dir, f))]
logger.info(f"将包含的图标资源文件: {', '.join(icon_files)}")

def get_current_version():
    """获取当前版本号"""
    version_file = os.path.join(root_dir, 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "1.0.0"

def update_version(new_version):
    """更新VERSION文件和version_checker.py中的版本号"""
    version_file = os.path.join(root_dir, 'VERSION')
    version_checker_file = os.path.join(root_dir, 'utils', 'version_checker.py')
    
    # 验证版本号格式
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        logger.error(f"版本号格式错误: {new_version}，应为 x.y.z 格式")
        return False
    
    try:
        # 更新VERSION文件
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(new_version + '\n')
        logger.success(f"VERSION文件已更新为: {new_version}")
        
        # 更新version_checker.py中的__version__
        if os.path.exists(version_checker_file):
            with open(version_checker_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正则表达式替换__version__的值
            updated_content = re.sub(
                r'__version__ = "[^"]*"',
                f'__version__ = "{new_version}"',
                content
            )
            
            with open(version_checker_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            logger.success(f"version_checker.py中的__version__已更新为: {new_version}")
        else:
            logger.warning("未找到version_checker.py文件，跳过__version__更新")
        
        return True
    except Exception as e:
        logger.error(f"更新版本号失败: {str(e)}")
        return False

def verify_version_sync():
    """验证VERSION文件和version_checker.py中的版本号是否同步"""
    try:
        # 读取VERSION文件
        version_file = os.path.join(root_dir, 'VERSION')
        version_from_file = "未找到"
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                version_from_file = f.read().strip()
        
        # 读取version_checker.py中的__version__
        version_checker_file = os.path.join(root_dir, 'utils', 'version_checker.py')
        version_from_code = "未找到"
        if os.path.exists(version_checker_file):
            with open(version_checker_file, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'__version__ = "([^"]*)"', content)
                if match:
                    version_from_code = match.group(1)
        
        logger.info(f"版本号验证:")
        logger.info(f"  VERSION文件: {version_from_file}")
        logger.info(f"  version_checker.py: {version_from_code}")
        
        if version_from_file == version_from_code:
            logger.success("✅ 版本号同步正常")
            return True
        else:
            logger.warning("⚠️ 版本号不同步，建议更新")
            return False
            
    except Exception as e:
        logger.error(f"验证版本号同步失败: {str(e)}")
        return False

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='ACE-KILLER Nuitka 打包工具')
    parser.add_argument('-v', '--version', 
                       help='指定新版本号 (格式: x.y.z)',
                       type=str)
    parser.add_argument('--no-version-update', 
                       action='store_true',
                       help='跳过版本号更新')
    return parser.parse_args()

# 解析命令行参数
args = parse_arguments()

# 获取当前版本号
current_version = get_current_version()
logger.info(f"当前版本号: {current_version}")

# 验证版本号同步状态
verify_version_sync()

# 处理版本号更新
if not args.no_version_update:
    if args.version:
        # 使用命令行指定的版本号
        new_version = args.version
        if update_version(new_version):
            current_version = new_version
        else:
            sys.exit(1)
    else:
        # 交互式输入新版本号
        print(f"\n当前版本号: {current_version}")
        user_input = input("请输入新版本号 (格式: x.y.z，直接回车跳过): ").strip()
        if user_input:
            if update_version(user_input):
                current_version = user_input
            else:
                sys.exit(1)
        else:
            logger.info("跳过版本号更新")

logger.info(f"使用版本号进行打包: {current_version}")

# 确保nuitka已安装
try:
    import nuitka
except ImportError:
    logger.info("正在安装 Nuitka...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "nuitka"])

# PySide6相关设置
try:
    from PySide6.QtCore import QLibraryInfo
    qt_plugins_path = QLibraryInfo.path(QLibraryInfo.PluginsPath)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    qt_binaries_path = QLibraryInfo.path(QLibraryInfo.BinariesPath)
    logger.debug(f"Qt插件路径已找到: {qt_plugins_path}")
except ImportError:
    logger.error("无法导入 PySide6，请确保已正确安装")
    sys.exit(1)

# 构建Nuitka打包命令
cmd = [
    sys.executable,
    "-m", "nuitka",
    "--standalone",  # 生成独立可执行文件
    "--windows-console-mode=disable",  # 禁用控制台
    "--windows-icon-from-ico=" + icon_path,  # 设置图标
    "--include-data-dir=%s=assets/icon" % assets_icon_dir,  # 包含整个图标资源目录
    "--windows-uac-admin",  # 请求管理员权限
    "--remove-output",  # 在重新构建前移除输出目录
    
    # PySide6 相关配置
    "--enable-plugin=pyside6",  # 启用PySide6插件
    "--nofollow-import-to=PySide6.QtWebEngineWidgets",
    "--nofollow-import-to=PySide6.Qt3DCore",
    "--nofollow-import-to=PySide6.Qt3DRender",
    "--nofollow-import-to=PySide6.QtCharts",
    "--nofollow-import-to=PySide6.QtDataVisualization",
    "--nofollow-import-to=PySide6.QtMultimedia",
    "--nofollow-import-to=PySide6.QtPositioning",
    "--nofollow-import-to=PySide6.QtBluetooth",
    "--nofollow-import-to=PySide6.QtSerialPort",
    "--nofollow-import-to=PySide6.QtLocation",
    # 优化选项
    "--lto=yes",  # 链接时优化
    "--mingw64",  # 使用MinGW64
    "--jobs=4",  # 使用多核编译加速
    "--disable-cache=all",  # 禁用缓存
    "--clean-cache=all",  # 清除现有缓存
    "--output-filename=ACE-KILLER.exe",  # 指定输出文件名
    "--nofollow-import-to=tkinter,PIL.ImageTk",  # 不跟随部分不必要模块
    "--prefer-source-code",  # 优先使用源代码而不是字节码
    "--python-flag=no_site",  # 不导入site
    "--python-flag=no_warnings",  # 不显示警告
    "main.py"
]

logger.info("开始 Nuitka 打包...")
logger.info("打包过程可能需要几分钟，请耐心等待...")

# 执行打包命令
try:
    # 切换到项目根目录执行打包命令
    os.chdir(root_dir)
    subprocess.check_call(cmd)
    
    # 查找生成的可执行文件
    main_exe = os.path.join(root_dir, "main.dist", "ACE-KILLER.exe")
    
    # 首先判断main_exe是否存在
    if os.path.exists(main_exe):
        logger.success(f"打包成功！生成的可执行文件: {main_exe}")
        
        # 输出文件大小信息
        size_mb = os.path.getsize(main_exe) / (1024 * 1024)
        logger.info(f"可执行文件大小: {size_mb:.2f} MB")
    else:
        logger.error("打包完成，但未找到可执行文件")
        
except subprocess.CalledProcessError as e:
    logger.error(f"打包失败: {e}")
    sys.exit(1)

# 压缩可执行文件目录
dist_dir = os.path.join(root_dir, "main.dist")
zip_name = f"ACE-KILLER-v{current_version}-x64"
zip_path = os.path.join(root_dir, zip_name + ".zip")
if os.path.exists(dist_dir):
    logger.info("正在压缩可执行文件目录...")
    # 确保在正确的位置创建zip文件
    shutil.make_archive(os.path.join(root_dir, zip_name), 'zip', dist_dir)
    logger.success(f"压缩完成！生成的压缩包: {zip_path}")
else:
    logger.error("未找到可执行文件目录，无法压缩")
    sys.exit(1)

logger.success(f"ACE-KILLER v{current_version} Nuitka 打包和压缩完成！")

# 显示使用说明
def show_usage():
    """显示使用说明"""
    print("\n" + "="*60)
    print("ACE-KILLER 打包工具使用说明:")
    print("="*60)
    print("1. 直接运行 (交互式更新版本号):")
    print("   python utils/build_exe.py")
    print()
    print("2. 指定版本号:")
    print("   python utils/build_exe.py -v 1.2.3")
    print()
    print("3. 跳过版本号更新:")
    print("   python utils/build_exe.py --no-version-update")
    print()
    print("4. 显示帮助:")
    print("   python utils/build_exe.py -h")
    print("="*60)

# 仅在直接运行脚本时显示使用说明
if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(f"\n当前项目版本: {get_current_version()}")
        show_usage()
