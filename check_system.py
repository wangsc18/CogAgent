#!/usr/bin/env python3
"""
平台检测和依赖检查脚本
用于检查系统是否满足运行 PACE 的要求
"""

import sys
import platform
import subprocess

def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version < (3, 9):
        print("  ⚠️  警告: 建议使用 Python 3.9 或更高版本")
        return False
    return True

def check_platform():
    """检查操作系统平台"""
    system = platform.system()
    print(f"✓ 操作系统: {system} ({platform.release()})")

    if system == "Darwin":
        print("  → 检测到 macOS，将使用 macOS 特定配置")
        return "macos"
    elif system == "Windows":
        print("  → 检测到 Windows，将使用 Windows 特定配置")
        return "windows"
    elif system == "Linux":
        print("  → 检测到 Linux，部分功能可能需要额外配置")
        return "linux"
    else:
        print(f"  ⚠️  未知平台: {system}")
        return "unknown"

def check_module(module_name):
    """检查 Python 模块是否已安装"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def check_dependencies(platform_type):
    """检查关键依赖"""
    print("\n检查关键依赖:")

    core_deps = [
        ("torch", "PyTorch"),
        ("cv2", "OpenCV"),
        ("quart", "Quart"),
        ("langchain", "LangChain"),
        ("pynput", "pynput"),
    ]

    platform_deps = {
        "macos": [
            ("Quartz", "PyObjC-Quartz"),
            ("AppKit", "PyObjC-Cocoa"),
        ],
        "windows": [
            ("win32gui", "pywin32"),
            ("pygetwindow", "pygetwindow"),
        ]
    }

    missing = []

    # 检查核心依赖
    for module, name in core_deps:
        if check_module(module):
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name} (未安装)")
            missing.append(name)

    # 检查平台特定依赖
    if platform_type in platform_deps:
        for module, name in platform_deps[platform_type]:
            if check_module(module):
                print(f"  ✓ {name}")
            else:
                print(f"  ✗ {name} (未安装)")
                missing.append(name)

    return missing

def check_gpu_support():
    """检查 GPU 支持"""
    print("\n检查 GPU 支持:")
    try:
        import torch

        if torch.cuda.is_available():
            print(f"  ✓ CUDA 可用")
            print(f"    GPU: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print(f"  ✓ Apple MPS 可用 (Apple Silicon)")
        else:
            print(f"  ℹ️  将使用 CPU (未检测到 GPU 加速)")

        return True
    except ImportError:
        print("  ✗ PyTorch 未安装，无法检测 GPU")
        return False

def check_camera():
    """检查摄像头"""
    print("\n检查摄像头:")
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("  ✓ 摄像头可用")
            cap.release()
            return True
        else:
            print("  ✗ 无法打开摄像头")
            print("    提示: 请检查摄像头权限设置")
            return False
    except ImportError:
        print("  ✗ OpenCV 未安装，无法检测摄像头")
        return False
    except Exception as e:
        print(f"  ✗ 检测摄像头时出错: {e}")
        return False

def check_model_file():
    """检查模型文件"""
    print("\n检查模型文件:")
    import os
    model_path = "utils/realtime_detection/best_resnet3d.pth"

    if os.path.exists(model_path):
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        print(f"  ✓ 模型文件存在 ({size_mb:.1f} MB)")
        return True
    else:
        print(f"  ℹ️  模型文件不存在: {model_path}")
        print("    系统可以运行，但认知负荷检测功能将不可用")
        return False

def provide_installation_guide(platform_type, missing_deps):
    """提供安装指南"""
    if not missing_deps:
        print("\n✅ 所有依赖都已安装！")
        return

    print("\n缺少以下依赖，请安装:")
    print("---")

    if platform_type == "macos":
        print("运行以下命令安装:")
        print("pip install -r requirements-macos.txt")
    elif platform_type == "windows":
        print("运行以下命令安装:")
        print("pip install -r requirements.txt")
    else:
        print("运行以下命令安装基础依赖:")
        print("pip install torch torchvision opencv-python quart langchain pynput")

    print("\n详细安装指南:")
    if platform_type == "macos":
        print("- macOS: 请查看 INSTALL_MACOS.md")
    elif platform_type == "windows":
        print("- Windows: 请查看 README.md")
    else:
        print("- 其他平台: 请查看 README.md")

def main():
    """主函数"""
    print("=" * 60)
    print("PACE 系统环境检查")
    print("=" * 60)

    # 检查 Python 版本
    python_ok = check_python_version()

    # 检查平台
    platform_type = check_platform()

    # 检查依赖
    missing = check_dependencies(platform_type)

    # 检查 GPU
    check_gpu_support()

    # 检查摄像头
    check_camera()

    # 检查模型文件
    check_model_file()

    # 提供安装指南
    print("\n" + "=" * 60)
    provide_installation_guide(platform_type, missing)
    print("=" * 60)

    if not missing and python_ok:
        print("\n✨ 系统已准备就绪！运行以下命令启动服务:")
        print("   hypercorn web_app:app --bind 0.0.0.0:5001")
    else:
        print("\n⚠️  请先安装缺失的依赖，然后重新运行此脚本进行检查。")

    return 0 if (not missing and python_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
