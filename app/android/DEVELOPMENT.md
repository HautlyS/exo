# Android Development Guide

## Prerequisites

### Install Required Tools

```bash
# 1. Android SDK
# Download from https://developer.android.com/studio
# Or on Linux with sdkmanager:
sdkmanager "platforms;android-35" "build-tools;35.0.0"

# 2. Android NDK 26.0+
sdkmanager "ndk;26.0.10469015"

# 3. CMake
sdkmanager "cmake;3.22.1"

# 4. Rust Android targets
rustup target add aarch64-linux-android armv7-linux-androideabi

# 5. Set environment variables
export ANDROID_SDK_ROOT=$HOME/Android/Sdk
export ANDROID_NDK_ROOT=$ANDROID_SDK_ROOT/ndk/26.0.10469015
export PATH=$ANDROID_SDK_ROOT/tools:$ANDROID_SDK_ROOT/platform-tools:$PATH
```

### Verify Setup

```bash
# Check Android SDK
sdkmanager --list | head -10

# Check NDK
ls $ANDROID_NDK_ROOT

# Check Rust targets
rustup target list | grep android
```

## Development Workflow

### 1. Make Code Changes

Edit Kotlin files in `src/main/kotlin/com/exo/gpu/`

```bash
# Auto-format Kotlin code
./gradlew ktlintFormat
```

### 2. Build Rust Library

```bash
# From project root
cd /home/hautly/exo

# Build for Android
cargo build --target aarch64-linux-android --release -p exo_jni_binding

# Verify output
ls -lh target/aarch64-linux-android/release/libexo_jni_binding.a
# Should be 5-10 MB
```

### 3. Build Android App

```bash
cd app/android

# Debug build (faster)
./gradlew assembleDebug

# Release build (optimized)
./gradlew assembleRelease

# Build with verbose output for debugging
./gradlew assembleDebug --info
```

### 4. Run Tests

```bash
# Local unit tests (no device required)
./gradlew test --info

# Instrumented tests (requires device/emulator)
./gradlew connectedAndroidTest --info

# Run specific test
./gradlew testDebug --info -Dorg.gradle.testkit.debug=false
```

### 5. Install and Run

```bash
# Install debug app on device
./gradlew installDebug

# Install and run
./gradlew installDebugRun

# View logs
adb logcat -c  # Clear log
adb logcat *:S ExoVulkan:V VulkanGpu:V  # Filter for GPU logs

# View real-time device info
adb shell vulkaninfo
```

## Debugging

### Android Studio Integration

```bash
# Open project in Android Studio
cd app/android
open -a "Android Studio" .

# Or from command line
studio app/android
```

### Native Code Debugging

1. Add breakpoints in C code (`jni_bridge.c`)
2. Build with debug symbols: `./gradlew assembleDebug`
3. In Android Studio: Run → Debug 'app'
4. Use LLDB debugger window

### JNI Debugging

```bash
# Check JNI method signatures
./gradlew javah

# Verify method names match Rust bindings
adb logcat | grep "JNI_OnLoad\|Java_com_exo_gpu"

# Check symbols in library
nm -D libexo_jni_binding.so | grep Java_com_exo_gpu
```

### Logcat Filtering

```bash
# All GPU-related logs
adb logcat | grep -E "ExoVulkan|VulkanGpu|jni_bridge"

# Errors only
adb logcat | grep "^E/"

# Real-time system events
adb logcat -s System

# Save to file
adb logcat > logs.txt &
```

## Emulator Setup

### Create AVD for GPU Testing

```bash
# List available system images
sdkmanager --list | grep "system-images"

# Create Android 14 (API 34) AVD with GPU
avdmanager create avd \
  -n exo_gpu_test \
  -k "system-images;android-34;google_apis;arm64-v8a" \
  -d "pixel_5" \
  --force

# Launch with GPU support
emulator -avd exo_gpu_test -gpu host -verbose
```

### Verify Emulator Vulkan

```bash
# Check if Vulkan available
adb shell vulkaninfo | head -20

# Install app
./gradlew installDebug

# Run tests
./gradlew connectedAndroidTest
```

## Build System Troubleshooting

### CMake Configuration Issues

```bash
# Manually run CMake to see detailed errors
cd app/android
cmake -P CMakeLists.txt -DCMAKE_SYSTEM_NAME=Android

# Check CMake variables
cmake --debug-output CMakeLists.txt
```

### Gradle Build Failures

```bash
# Rebuild from scratch
./gradlew clean build

# Check dependencies
./gradlew dependencies

# Force download of dependencies
./gradlew --refresh-dependencies build

# Use verbose output
./gradlew build --debug 2>&1 | head -100
```

### Rust Compilation Issues

```bash
# Check for Rust errors
cargo build --target aarch64-linux-android --release -p exo_jni_binding 2>&1 | grep error

# Show all warnings
cargo build --target aarch64-linux-android --release -p exo_jni_binding 2>&1 | grep warning

# Clean Rust build
cargo clean
```

## Performance Profiling

### CPU Profiling

```bash
# Use Android Profiler in Android Studio
# Or from command line:
adb shell am profiler start --sampling 1000

# Let app run for a few seconds, then:
adb shell am profiler stop
```

### Memory Profiling

```bash
# Dump memory usage
adb shell dumpsys meminfo com.exo.gpu

# Monitor real-time memory
adb shell am dumpheap com.exo.gpu /data/local/tmp/heap.hprof
adb pull /data/local/tmp/heap.hprof
```

### GPU Profiling

```bash
# Vulkan validation layers
adb shell setprop debug.vulkan.validation 1

# GPU counters
vulkantrace record --output trace.vtrace app_command

# Analyze with vendor tools
# NVIDIA: nvprof
# AMD: RGP (Radeon GPU Profiler)
```

## Common Issues and Solutions

### Issue: "Could not find Vulkan"

```
CMake Error at CMakeLists.txt:XX: find_package(Vulkan REQUIRED)
```

**Solution:**
```bash
# Install Vulkan SDK
# From: https://vulkan.lunarg.com/sdk/home

# Or set Vulkan_DIR explicitly
export Vulkan_DIR=/path/to/vulkan/sdk
./gradlew build
```

### Issue: "libexo_jni_binding.a not found"

**Solution:**
```bash
# Verify Rust library was built
ls -l target/aarch64-linux-android/release/libexo_jni_binding.a

# If missing, rebuild it
cargo build --target aarch64-linux-android --release -p exo_jni_binding --verbose

# Check build logs
cargo build --target aarch64-linux-android --release -p exo_jni_binding 2>&1 | tail -50
```

### Issue: "UnsatisfiedLinkError: dlopen failed: library not found"

**Solution:**
```bash
# Check if library was packaged in APK
unzip -l build/outputs/apk/debug/app-debug.apk | grep libexo_jni

# If not present, verify CMakeLists.txt paths
cat CMakeLists.txt | grep LIBEXO_JNI_BINDING

# Rebuild with verbose output
./gradlew assembleDebug --info 2>&1 | grep -A5 "libexo_jni"
```

### Issue: "Symbol not found: Java_com_exo_gpu_VulkanGpu_*"

**Solution:**
```bash
# Verify Rust library exports JNI functions
nm -g target/aarch64-linux-android/release/libexo_jni_binding.a | grep Java_com_exo_gpu

# Check method signature in Rust
grep "pub extern \"C\" fn Java_com_exo_gpu" rust/exo_jni_binding/src/lib.rs

# Verify Kotlin method name matches exactly
grep "external fun " app/android/src/main/kotlin/com/exo/gpu/VulkanGpu.kt
```

## Code Style

### Kotlin Code Style

```bash
# Format all Kotlin files
./gradlew ktlintFormat

# Check formatting
./gradlew ktlint

# Configure in build.gradle.kts
kotlin {
    jvmTarget = "17"
}
```

### C Code Style

```bash
# Format C code with clang-format
clang-format -i app/android/src/native/jni_bridge.c

# Check style
clang-format --dry-run app/android/src/native/jni_bridge.c
```

## Documentation

- **README.md** - User-facing documentation
- **DEVELOPMENT.md** - This file, for developers
- **Code comments** - Inline documentation in Kotlin/C code
- **Javadoc/KDoc** - API documentation in source files

Generate KDoc documentation:

```bash
./gradlew dokkaHtml

# Open documentation
open build/dokka/html/index.html
```

## Continuous Integration

This project uses GitHub Actions for CI/CD.

### Local CI Testing

```bash
# Run all checks locally before pushing
./gradlew test check

# Build release APK
./gradlew assembleRelease

# Check with lint
./gradlew lint
```

## Device Testing

### Physical Device Setup

```bash
# Enable developer mode
# Settings → About phone → Build number (tap 7 times)
# Settings → Developer options → USB debugging (enable)

# Verify connection
adb devices

# Install app
./gradlew installDebug

# Run on device
./gradlew assembleDebug && adb shell am start -n com.exo.gpu/com.exo.gpu.MainActivity
```

### Emulator vs Physical Device

| Feature | Physical | Emulator |
|---------|----------|----------|
| GPU support | Native | Host-dependent |
| Performance | Real-world | Slower |
| Debugging | Harder | Easier |
| Cost | Hardware | Free |
| Testing | Recommended | Good for CI |

## Release Builds

### Signing Configuration

```gradle
// In build.gradle.kts
signingConfigs {
    release {
        storeFile = file(System.getenv("RELEASE_KEYSTORE_PATH"))
        storePassword = System.getenv("RELEASE_KEYSTORE_PASSWORD")
        keyAlias = System.getenv("RELEASE_KEY_ALIAS")
        keyPassword = System.getenv("RELEASE_KEY_PASSWORD")
    }
}
```

### Build Release APK

```bash
# Set signing credentials
export RELEASE_KEYSTORE_PATH=/path/to/keystore.jks
export RELEASE_KEYSTORE_PASSWORD=password
export RELEASE_KEY_ALIAS=key_alias
export RELEASE_KEY_PASSWORD=key_password

# Build
./gradlew assembleRelease

# Output: app/build/outputs/apk/release/app-release.apk
```

### Size Optimization

```gradle
// In build.gradle.kts
android {
    bundle {
        language {
            enableSplit = true
        }
    }
    buildTypes {
        release {
            minifyEnabled = true
            shrinkResources = true
            proguardFiles getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro"
        }
    }
}
```

## Further Reading

- [Android Developer Docs](https://developer.android.com/docs)
- [NDK Developer Guide](https://developer.android.com/ndk/guides)
- [JNI Specification](https://docs.oracle.com/javase/8/docs/technotes/guides/jni/)
- [Vulkan Tutorial](https://vulkan-tutorial.com/)
- [Kotlin Documentation](https://kotlinlang.org/docs/home.html)
