cmake_minimum_required(VERSION 3.22.1)
project(exo_gpu_android C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Platform detection
if(CMAKE_SYSTEM_NAME STREQUAL "Android")
    set(ANDROID_PLATFORM TRUE)
endif()

# Paths to Rust built libraries
set(RUST_TARGET "aarch64-linux-android")
set(RUST_BUILD_DIR "${CMAKE_SOURCE_DIR}/../../../target/${RUST_TARGET}/release")

# Find Rust static libraries
find_library(
    LIBEXO_JNI_BINDING
    NAMES exo_jni_binding
    PATHS ${RUST_BUILD_DIR}
    NO_DEFAULT_PATH
    NO_CMAKE_FIND_ROOT_PATH
)

if(NOT LIBEXO_JNI_BINDING)
    message(FATAL_ERROR "Could not find libexo_jni_binding.a in ${RUST_BUILD_DIR}")
endif()

message(STATUS "Found exo_jni_binding: ${LIBEXO_JNI_BINDING}")

# Find Vulkan
find_package(Vulkan REQUIRED)

# Create JNI bridge library
add_library(exo_jni_bridge SHARED
    src/native/jni_bridge.c
)

target_include_directories(exo_jni_bridge PRIVATE
    ${JAVA_INCLUDE_PATH}
    ${JAVA_INCLUDE_PATH2}
    ${VULKAN_INCLUDE_DIR}
    ../../../rust/exo_vulkan_binding/src
    ../../../rust/exo_jni_binding/src
)

target_link_libraries(exo_jni_bridge
    ${LIBEXO_JNI_BINDING}
    ${VULKAN_LIBRARIES}
    -ldl
    -llog
)

# Optimization flags
target_compile_options(exo_jni_bridge PRIVATE
    -ffunction-sections
    -fdata-sections
    -fPIC
)

# Link-time optimization for release builds
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(exo_jni_bridge PRIVATE -flto)
    target_link_options(exo_jni_bridge PRIVATE -flto -Wl,--gc-sections)
endif()

# Install
install(
    TARGETS exo_jni_bridge
    LIBRARY DESTINATION lib
)
