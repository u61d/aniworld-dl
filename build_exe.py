import PyInstaller.__main__
import os
import sys
import shutil


def build_executable():
    """Build the executable with proper bundling to prevent source exposure"""

    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Paths to your files
    main_script = os.path.join(current_dir, "anidlkey.py")
    dl_script = os.path.join(current_dir, "dl.py")
    keyauth_script = os.path.join(current_dir, "keyauth.py")
    settings_script = os.path.join(current_dir, "settings.py")
    mal_script = os.path.join(current_dir, "mal.py")

    if not os.path.exists(main_script):
        print("Error: anidlkey.py not found!")
        return False

    if not os.path.exists(dl_script):
        print("Error: dl.py not found!")
        return False

    if not os.path.exists(keyauth_script):
        print("Error: keyauth.py not found!")
        return False

    if not os.path.exists(settings_script):
        print("Error: settings.py not found!")
        return False

    if not os.path.exists(mal_script):
        print("Error: mal.py not found!")
        return False

    # PyInstaller arguments - Updated for proper bundling
    args = [
        main_script,
        "--name=ShadowStream",
        "--onefile",
        "--console",
        # Include all necessary Python files
        "--add-data",
        f"{dl_script};.",
        "--add-data",
        f"{keyauth_script};.",
        "--add-data",
        f"{settings_script};.",
        "--add-data",
        f"{mal_script};.",
        # Hidden imports for all dependencies
        "--hidden-import=cloudscraper",
        "--hidden-import=requests",
        "--hidden-import=bs4",
        "--hidden-import=beautifulsoup4",
        "--hidden-import=rich",
        "--hidden-import=yt_dlp",
        "--hidden-import=keyauth",
        "--hidden-import=dl",
        "--hidden-import=settings",
        "--hidden-import=mal",
        "--hidden-import=qrcode",
        "--hidden-import=PIL",
        "--hidden-import=discord_interactions",
        # Collect all packages
        "--collect-all=rich",
        "--collect-all=cloudscraper",
        "--collect-all=requests",
        "--collect-all=bs4",
        "--collect-all=yt_dlp",
        "--collect-all=keyauth",
        "--collect-all=dl",
        # Build directories
        "--distpath=dist",
        "--workpath=build",
        "--specpath=.",
        "--clean",
        "--noconfirm",
        # Security options
        "--noupx",
        "--strip",
        # Exclude unnecessary modules
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=numpy",
        "--exclude-module=pandas",
        "--exclude-module=scipy",
    ]

    print("Building ShadowStream executable...")
    print("This may take a few minutes...")
    print("\nConfiguration:")
    print(f"  Main script: {main_script}")
    print(f"  DL script: {dl_script}")
    print(f"  KeyAuth script: {keyauth_script}")
    print(f"  Build type: Single file executable")
    print(f"  Platform: {sys.platform}")

    try:
        PyInstaller.__main__.run(args)

        print("\n" + "=" * 60)
        print("✅ BUILD COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(
            f"📁 Executable location: {os.path.join(current_dir, 'dist', 'ShadowStream.exe')}"
        )
        print("\n📋 SECURITY FEATURES:")
        print("   • All scripts properly bundled")
        print("   • Source code protection enabled")
        print("=" * 60)
        return True

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ BUILD FAILED!")
        print("=" * 60)
        print(f"Error: {e}")
        print("=" * 60)
        return False


def clean_build_artifacts():
    """Clean previous build artifacts"""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Directories to clean
    build_dir = os.path.join(current_dir, "build")
    dist_dir = os.path.join(current_dir, "dist")
    spec_files = [f for f in os.listdir(current_dir) if f.endswith(".spec")]

    # Remove build directory
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
            print(f"✓ Removed build directory: {build_dir}")
        except Exception as e:
            print(f"⚠ Could not remove build directory: {e}")

    # Remove dist directory
    if os.path.exists(dist_dir):
        try:
            shutil.rmtree(dist_dir)
            print(f"✓ Removed dist directory: {dist_dir}")
        except Exception as e:
            print(f"⚠ Could not remove dist directory: {e}")

    # Remove spec files
    for spec_file in spec_files:
        try:
            os.remove(os.path.join(current_dir, spec_file))
            print(f"✓ Removed spec file: {spec_file}")
        except Exception as e:
            print(f"⚠ Could not remove spec file {spec_file}: {e}")


if __name__ == "__main__":
    print("ShadowStream Executable Builder")
    print("=" * 40)

    # Check if user wants to clean first
    if len(sys.argv) > 1 and sys.argv[1] == "--clean":
        print("Cleaning previous build artifacts...")
        clean_build_artifacts()
        print()

    # Build the executable
    success = build_executable()

    if not success:
        sys.exit(1)
    else:
        print(f"\n🎉 Ready to test your executable!")
        print(f"Run: .{os.sep}dist{os.sep}ShadowStream.exe")
