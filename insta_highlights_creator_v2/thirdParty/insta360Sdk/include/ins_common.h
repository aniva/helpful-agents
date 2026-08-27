#pragma once
#include <functional>
#include <map>
#include <vector>
#include <string>
#include <memory>

namespace ins {
    typedef std::function<void(int process, int error)> stitch_process_callback;
    typedef std::function<void(int error, const char* errinfo)> stitch_error_callback;
    typedef std::function<void(uint8_t* data[4], int linesize[4], int width, int height, int format, int64_t timestamp)> stitch_realtime_data_callback;

    enum class STITCH_TYPE {
        TEMPLATE,       // 模板拼接
        OPTFLOW,        // 光流拼接
        DYNAMICSTITCH,  // 动态光流拼接
        AIFLOW          // ai拼接
    };

    enum class IMAGE_TYPE {
        JPEG,
        PNG,
    };

    enum class ImageProcessingAccel { kAuto = 0, kCPU };

    enum class CameraAccessoryType {
        kNormal = 0,
        kWaterproof,            // (one/onex/onex2/oner/oners/onex2/onex3) 潜水壳
        kOnerLensGuard,         // (oner/oners) 黏贴式保护镜
        kOnerLensGuardPro,      // (oner/oners) 卡扣式保护镜
        kOnex2LensGuard,        // (oner/oners/onex2/onex3) 黏贴式保护镜
        kOnex2LensGuardPro,     // (onex2)卡扣式保护镜
        k283PanoLensGuardPro,   // (oner/oners) 283全景镜头的卡扣式保护镜
        kDiveCaseAir,           // (onex/onex2/oner/oners/onex2/onex3) 潜水壳(水上)
        kDiveCaseWater,         // (onex/onex2/oner/oners/onex2/onex3) 潜水壳(水下)
        kInvisibleDiveCaseAir,  // X3/X4/X5 全隐形潜水壳(水上)
        kInvisibleDiveCaseWater,// X3/X4/X5 全隐形潜水壳(水下)
        kLensGuardA,            // X3/X4/x5 A级塑胶保护镜
        kLensGuardS,            // X3/X4/x5 S级玻璃保护镜
        kLensGuardAS,           // X4 自动识别
    };

    enum class InsLogLevel {
        VERBOSE = 0,
        INFO,
        WARNING,
        ERR,
        FATAL,
    };

    enum class SDKErrorCode {
        E_SUCCESS = 0,                      // 正常
        E_OPEN_FILE = 1,                    // 打开文件失败
        E_PARSE_METADATA = 2,               // 解析文件尾失败
        E_CREATE_OFFSCREEN = 3,             // 创建离屏渲染失败
        E_CREATE_RENDER_MODEL = 4,          // 创建模型失败
        E_FRAME_PARSE = 5,                  // 获取视频帧失败
        E_CREATE_RENDER_SOURCE = 6,         // 创建渲染数据源失败
        E_UPDATE_RENDER_SOURCE = 7,         // 更新数据帧到渲染源失败
        E_RENDER_FRAME = 8,                 // 渲染数据失败
        E_SAVE_FRAME = 9,                   // 保存图片失败
        E_VIDEO_FRAME_EXPORTOR = 10,        // 创建视频提取器失败
        E_FILE_TYPE_UNSUPPORT = 11,         // 文件类型不支持
        E_INTERNAL_ERROR = 998,             // 程序内部错误，可能存在bug
        E_UNKNOWN = 999
    };

    enum class MediaFileType {
        UNDEFINED = 0xffff,
        VIDEO_NORMAL = 0,           // 普通视频
        VIDEO_BULLETTIME = 1,       // 子弹时间
        VIDEO_TIMELAPSE = 2,        // timelapse视频
        VIDEO_HDR = 6,              // HDR视频
        VIDEO_STATIC_TIMELAPSE = 8,
        VIDEO_TIMESHIFT = 9,        // 移动延时
        VIDEO_SUPER_NORMAL = 11,    // 超级录像
        VIDEO_LOOPRECORDING = 12,   // 循环录影
        VIDEO_FPV = 15,             // FPV视频
        VIDEO_MOVIE = 16,           // 电影模式视频
        VIDEO_SLOWMOTION = 17,      // 慢动作视频
        VIDEO_SELFIE = 18,          // 跟拍视频
        VIDEO_PURE = 20,            // 夜景视频
        VIDEO_STARLAPSE = 21,       // 星空视频
        VIDEO_DASH_CAM = 23,        // 行车记录
        VIDEO_VIR_PTZ = 24,         // 虚拟云台

        PHOTO_NORMAL = 3,           // 普通照片
        PHOTO_HDR = 4,              // HDR照片
        PHOTO_INTERVALSHOOTING = 5, // 间隔拍照照片
        PHOTO_BURST = 7,            // 连拍照片
        PHOTO_AEB_NIGHT_MODE = 10,
        PHOTO_STARLAPSE = 13,       // 星空拍照
        PHOTO_PANO_MODE = 14,       // 全景照片
        PHOTO_PURESHOTPLUS = 19,    // pureshot照片
        PHOTO_STARTRAIL = 22,
    };

    enum class VideoDecodeType {
        kH264,
        kH265
    };

    struct GyroData {
        int64_t timestamp;
        double ax;
        double ay;
        double az;
        double gx;
        double gy;
        double gz;
    };

    struct ExposureData {
        double timestamp;
        double exposure_time;
    };

    struct WindowCropInfo {
        uint32_t src_width;
        uint32_t src_height;
        uint32_t dst_width;
        uint32_t dst_height;
        int32_t crop_offset_x;   //自拍模式偏移量
        int32_t crop_offset_y;
    };

    struct CameraInfo {
        std::string cameraName;
        WindowCropInfo window_crop_info_;
        std::vector<std::string> offset;
        VideoDecodeType decode_type;
        int64_t gyro_timestamp{ 0 };
        int64_t sweep_timestamp{ 0 };
    };

    struct MediaFileInfo {
        MediaFileType media_type;
        int width;
        int height;
        double fps;
        int64_t bitrate;
        int64_t duration_ms;
    };
}