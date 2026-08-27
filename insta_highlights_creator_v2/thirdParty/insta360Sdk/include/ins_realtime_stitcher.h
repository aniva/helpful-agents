#pragma once

#include "ins_common.h"

#if WIN32
#ifdef USE_EXPORTDLL
#define MEDIASDK_API _declspec(dllexport)
#else
#define MEDIASDK_API _declspec(dllimport)
#endif // USE_EXPORTDLL
#else
#define MEDIASDK_API
#endif

namespace ins {
    class StitcherImp;
    /**
     * \class VideoStitcher
     * \brief A class that stitch video, only support the formats that maked by Insta360 camera, for example *.insv .
     *   If you want to make the most of multiple GPUs, you must create process instances to correspond to each GPU.
     *   In a process instance, multiple GPUs are not supported.
    */
    void MEDIASDK_API InitEnv();
    // set path of the log
    void MEDIASDK_API SetLogPath(const std::string& log_path);

    // set log level
    void MEDIASDK_API SetLogLevel(InsLogLevel level);

    class MEDIASDK_API RealTimeStitcher {
    public:
        RealTimeStitcher();
        ~RealTimeStitcher();

    public:
        /**
            * \brief set CameraAccessoryType
        */
        void SetCameraAccessoryType(CameraAccessoryType type);

        /**
         * \brief set the type of stitch,
         * \param type  it has four kind that has template,optflow,dynamicStitch,AI-Stitching and
         * \            template is fastest and AI-Stitching is slowest.
         * \            When the stitch type is AI-Stitching, the AI-Stitching model file must be set.
         * \            You can refer to this interface 'SetAiStitchModelFile ',
         * \            otherwise Ai-Stitching will not take effect
         */
        void SetStitchType(STITCH_TYPE type);

        /**
         *  \brief set the callback that can tell the client the error if stitcher goes error
         *  \param callback used for get err info of the process.
         *  \param lcontent the context
         */
        void SetStitchStateCallback(stitch_error_callback callback);

        /**
         *  \brief 设置预览需要的参数
         *  \param cameraInfo
         */
        void SetCameraInfo(const CameraInfo& cameraInfo);

        /**
         *  \brief start stitch
         */
        void StartStitch();

        /**
         *  \brief cancel stitch
         */
        bool CancelStitch();

        void SetStitchRealTimeDataCallback(stitch_realtime_data_callback callback);

        /**
        * \brief set the video resolution of the output file，default size of source
        */
        void SetOutputSize(int width, int height);
        /**
        * \brief Whether to turn on FlowState
        * \param enable true is on and false is off, default off
        */
        void EnableFlowState(bool enable);

        void EnableDirectionLock(bool enable);

        void SetVideoDelayMs(int video_delay_ms);

        /**
        * \brief enable deflicker
        */
        void EnableDeflicker(bool enable);

        /**
        * \brief 设置编解码器的软件实现开关
        * @param enable_encoder 是否启用软件编码（true=使用，false=禁用）
        * @param enable_decoder 是否启用软件解码（true=使用，false=禁用）
        */
        void SetSoftwareCodecUsage(bool enable_encoder, bool enable_decoder);

        /**
        * \brief enable Defringe
        */
        void EnableDefringe(bool enable);

        /**
        * \brief 处理视频数据
        */
        void HandleVideoData(const uint8_t* data, size_t size, int64_t timestamp, uint8_t stream_type, int stream_index = 0);

        /**
        * \brief 处理防抖数据
        */
        void HandleGyroData(const std::vector<GyroData>& data);

        /**
        * \brief 处理曝光数据
        */
        void HandleExposureData(const ExposureData& data);

    private:
        std::shared_ptr<StitcherImp> imp_;
    };
};