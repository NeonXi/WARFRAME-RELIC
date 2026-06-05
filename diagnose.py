import sys
import os
import traceback

def main():
    print("=" * 60)
    print("WARFRAME-RELIC Diagnostic Tool")
    print("=" * 60)
    
    # Check Python version
    print(f"\n[1] Python Version: {sys.version}")
    print(f"    Executable: {sys.executable}")
    
    # Check current directory
    print(f"\n[2] Working Directory: {os.getcwd()}")
    
    # Check numpy version
    print("\n[3] Checking NumPy...")
    try:
        import numpy as np
        print(f"    NumPy Version: {np.__version__}")
    except Exception as e:
        print(f"    ERROR: {e}")
    
    # Check cv2
    print("\n[4] Checking OpenCV...")
    try:
        import cv2
        print(f"    OpenCV Version: {cv2.__version__}")
    except Exception as e:
        print(f"    ERROR: {e}")
        traceback.print_exc()
    
    # Check PyQt6
    print("\n[5] Checking PyQt6...")
    try:
        from PyQt6.QtWidgets import QApplication
        print("    PyQt6: OK")
    except Exception as e:
        print(f"    ERROR: {e}")
        traceback.print_exc()
    
    # Check other dependencies
    print("\n[6] Checking other dependencies...")
    deps = ['dxcam', 'keyboard', 'rapidocr_onnxruntime', 'PIL', 'pypinyin']
    for dep in deps:
        try:
            __import__(dep)
            print(f"    [OK] {dep}")
        except Exception as e:
            print(f"    [FAIL] {dep}: {e}")
    
    # Check main.py exists
    print("\n[7] Checking main.py...")
    if os.path.exists("main.py"):
        print("    main.py: Found")
    else:
        print("    main.py: NOT FOUND!")
    
    print("\n" + "=" * 60)
    print("Diagnostic complete!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        traceback.print_exc()