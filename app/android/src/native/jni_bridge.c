#include <jni.h>
#include <android/log.h>
#include <stdio.h>

#define LOG_TAG "exo_jni_bridge"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Forward declarations from Rust library
// These are defined in exo_jni_binding and linked at compile time
extern jboolean Java_com_exo_gpu_VulkanGpu_initializeVulkan(
    JNIEnv *env, jclass clazz);

extern jstring Java_com_exo_gpu_VulkanGpu_enumerateDevices(
    JNIEnv *env, jclass clazz);

extern jstring Java_com_exo_gpu_VulkanGpu_getDeviceName(
    JNIEnv *env, jclass clazz, jint deviceIndex);

extern jlong Java_com_exo_gpu_VulkanGpu_getDeviceMemory(
    JNIEnv *env, jclass clazz, jint deviceIndex);

extern jint Java_com_exo_gpu_VulkanGpu_getComputeUnits(
    JNIEnv *env, jclass clazz, jint deviceIndex);

extern jstring Java_com_exo_gpu_VulkanGpu_allocateMemory(
    JNIEnv *env, jclass clazz, jint deviceIndex, jlong sizeBytes);

extern jboolean Java_com_exo_gpu_VulkanGpu_freeMemory(
    JNIEnv *env, jclass clazz, jstring handleId);

extern jboolean Java_com_exo_gpu_VulkanGpu_copyToDevice(
    JNIEnv *env, jclass clazz, jstring handleId, jbyteArray data);

extern jbyteArray Java_com_exo_gpu_VulkanGpu_copyFromDevice(
    JNIEnv *env, jclass clazz, jstring handleId, jlong sizeBytes);

/**
 * JNI_OnLoad - called when library is loaded by system.
 * Performs initialization and version negotiation.
 */
jint JNI_OnLoad(JavaVM *vm, void *reserved) {
    LOGI("JNI_OnLoad: Initializing exo_jni_bridge");
    
    JNIEnv *env;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        LOGE("JNI_OnLoad: Failed to get JNI environment");
        return -1;
    }
    
    LOGI("JNI_OnLoad: Successfully initialized (version JNI_VERSION_1_6)");
    return JNI_VERSION_1_6;
}

/**
 * JNI_OnUnload - called when library is unloaded.
 * Performs cleanup.
 */
void JNI_OnUnload(JavaVM *vm, void *reserved) {
    LOGI("JNI_OnUnload: Cleaning up exo_jni_bridge");
}
