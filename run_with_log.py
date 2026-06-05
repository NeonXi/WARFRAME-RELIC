import sys
import os
import traceback

def main():
    print("=" * 60)
    print("WARFRAME-RELIC Wrapper with Logging")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Working Dir: {os.getcwd()}")
    print("=" * 60)
    
    log_file = "startup_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"=== Startup Log ===\n")
        f.write(f"Time: {__import__('datetime').datetime.now()}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Working Dir: {os.getcwd()}\n")
    
    try:
        # Step 1: Import bootstrap module
        print("\n[1] Importing bootstrap module...")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n[1] Importing bootstrap module...\n")
        
        from core.bootstrap import main
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("bootstrap module imported successfully\n")
        
        # Step 2: Call main()
        print("\n[2] Calling main()...")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n[2] Calling main()...\n")
        
        main()
        
        print("\n[SUCCESS] Program exited normally")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("Program exited normally\n")
            
    except Exception as e:
        error_msg = f"\n[ERROR] {type(e).__name__}: {e}"
        print(error_msg)
        print("\n" + "=" * 60)
        print("Traceback:")
        print("=" * 60)
        traceback.print_exc()
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[ERROR] {type(e).__name__}: {e}\n")
            f.write("Traceback:\n")
            traceback.print_exc(file=f)
        
        print(f"\nFull error logged to: {log_file}")

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")