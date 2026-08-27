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

    // set model root dir
    void MEDIASDK_API SetModelFileRootDir(const std::string& root_dir);

    // get file info
    bool MEDIASDK_API GetMediaFileInfo(const std::vector<std::string>& file_paths, MediaFileInfo& info);

    class MEDIASDK_API VideoStitcher {
    public:
        VideoStitcher();
        ~VideoStitcher() = default;

    public:
        /**
        *\brief get timestamp list
        *\param the map contains frame index and frame timestamps
        */
        //static std::map<uint64_t, uint64_t> GetFrameTimeStampsList(const std::string& url);

        /**
         * \brief set the path of the source that you wanted.
         * \param input_paths if the source is the kind that ‘5.7k’, the size of the vector is 2，1 othersize
         */
        void SetInputPath(const std::vector<std::string>& input_paths);

        /**
        *\brief set output path of the stab path
        */
        void SetStabDataOutputPath(const std::string& file_path);

        /**
        *\brief set the info of imgage sequence
        *\param output_dir the output dir of imgage sequence. does not include filename
        *\param image_type support jpg and png
        */
        void SetImageSequenceInfo(const std::string& output_dir, IMAGE_TYPE image_type);

        /**
        *\brief set the numbers of export frame
        *\param vec the vector that saved frame index, starting from zero
        */
        void SetExportFrameSequence(const std::vector<uint64_t>& vec);

        /*
        * \brief If you have a CUDA-accelerated environment,
        *\       you can set this parameter to true. It can provide the speed of stitching
        */
        void EnableCuda(bool enable);

        /**
         *\brief set the file path of the output that you wanted, include filename
         */
        void SetOutputPath(const std::string& output_path);

        /**
         *\brief set the video bitrate of the output file bps
         */
        void SetOutputBitRate(int64_t bitRate);

        /**
         * \brief set the video resolution of the output file，default size of source
         */
        void SetOutputSize(int width, int height);

        /**
         * \brief Whether to turn on FlowState
         * \param enable true is on and false is off, default off
         */
        void EnableFlowState(bool enable);

        /**
         * \brief Whether to turn on directionLock, the feautre depend on flowstate, flowstate must open if you want use the feature
         * \param enable true is on and false is off, default off
         * \
         */
        void EnableDirectionLock(bool enable);

        /**
         * \brief Whether to turn on ImageFusion,  not support TEMPLATE stitch
         * \param enable  true is on and false is off, default off
         */
        void EnableStitchFusion(bool enable);

        /**
         * \brief Whether to turn on cooling shell detection
         * \param enable  true is on and false is off, default off
         */
        void EnableCoolingShellDetection(bool enable);

        /**
         * \brief Whether to turn on denoise
         * \param enable  true is on and false is off, default off
         */
        void EnableDenoise(bool enable);

        /**
         * \brief Whether to turn on ImageFusion
         * \param enable  true is on and false is off, default off
         * \param model_path this param is required for the feature, if the param is empty, the feature is disabled
         * \param strength
         */
        void EnableColorPlus(bool enable, float strength = 1.0f);

        /**
         * \brief Whether to use h265 encoder, default encoder is h264
         */
        void EnableH265Encoder();

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
         *  \brief set the callback that can tell the client the progress of stitching
         *  \param callback used for get process the process
         *  \param lcontent the context
         */
        void SetStitchProgressCallback(stitch_process_callback callback);

        /**
         *  \brief set the callback that can tell the client the error if stitcher goes error
         *  \param callback used for get err info of the process.
         *  \param lcontent the context
         */
        void SetStitchStateCallback(stitch_error_callback callback);

        /**
         *  \brief start stitch
         */
        void StartStitch();

        /**
         *  \brief cancel stitch
         */
        bool CancelStitch();

        /**
        *  \brief get stitch  progress  0 ~ 100
        */
        int GetStitchProgress() const;

        /**
        * \brief set CameraAccessoryType
        */
        void SetCameraAccessoryType(CameraAccessoryType type);

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
         * \brief set image process accel type
         * @param type
         */
        void SetImageProcessingAccelType(ImageProcessingAccel type);

        /**
        * \brief enable Defringe
        */
        void EnableDefringe(bool enable);

        /**
         * \brief set exposure
         * \param exposure range[-100,100]
         */
        void SetExposure(int exposure);

        /**
         * \brief set highlights
         * \param highlights range[-100,100]
         */
        void SetHighlights(int highlights);

        /**
         * \brief set shadows
         * \param shadows range[-100,100]
        */
        void SetShadows(int shadows);

        /**
         * \brief set contrast
         * \param contrast range[-100,100]
        */
        void SetContrast(int contrast);

        /**
         * \brief set brightness
         * \param brightness range[-100,100]
         */
        void SetBrightness(int brightness);

        /**
         * \brief set blackpoint
         * \param blackpoint range[-100,100]
         */
        void SetBlackpoint(int blackpoint);

        /**
         * \brief set saturation
         * \param saturation range[-100,100]
         */
        void SetSaturation(int saturation);

        /**
         * \brief set vibrance
         * \param vibrance range[-100,100]
        */
        void SetVibrance(int vibrance);

        /**
         * \brief set warmth
         * \param warmth range[-100,100]
         */
        void SetWarmth(int warmth);

        /**
         * \brief set tint
         * \param tint range[-100,100]
         */
        void SetTint(int tint);

        /**
         * \brief set definition
         * \param contrast range[0, 100]
         */
        void SetDefinition(int definition);

    private:
        std::shared_ptr<StitcherImp> imp_;
    };

    /**
     * \class ImageStitcher
     * \brief A class that stitch image, only support the formats that maked by Insta360 camera, for example *.insp
     */
    class MEDIASDK_API ImageStitcher {
    public:
        ImageStitcher();
        ~ImageStitcher() = default;

    public:
        /**
        * \brief set the path of the source that you wanted.
        * \param input_path
        */
        void SetInputPath(const std::vector<std::string>& input_paths);

        /**
         * \brief set the path of the output that you wanted
         */
        void SetOutputPath(const std::string& output_path);

        /**
         * \brief set the video resolution of the output file
         */
        void SetOutputSize(int width, int height);

        /**
         * \brief Whether to turn on FlowState
         * \param enable true is on and false is off default off
         */
        void EnableFlowState(bool enable);

        /**
         * \brief Whether to turn on ImageFusion,  not support TEMPLATE stitch
         * \param enable true is on and false is off, default off
         * \param model_path if model file is not found, colorplus is disabled
         */
        void EnableColorPlus(bool enable, float strength = 0.3f);

        /**
        * \brief Whether to turn on denoise
        * \param enable  true is on and false is off, default off
        */
        void EnableDenoise(bool enable);

        /**
        * \brief set the type of stitch,
        * \param type  it has four kind that has template,optflow,dynamicStitch,AI-Stitching and
        * \            template is fastest and AI-Stitching is slowest.
        * \            When the stitch type is AI-Stitching, the AI-Stitching model file must be set.
        * \            You can refer to this interface 'SetAiStitchModelFile ',
        * \            otherwise Ai-Stitching will not take effect
        */
        void SetStitchType(STITCH_TYPE type);

        /*
        * \brief If you have a CUDA-accelerated environment,
        *\       you can set this parameter to true. It can provide the speed of stitching
        */
        void EnableCuda(bool enable);

        /**
         * \brief set image process accel type
         * @param type
         */
        void SetImageProcessingAccelType(ImageProcessingAccel type);

        /**
         * \brief Whether to turn on ImageFusion,  not support TEMPLATE stitch
         * \param enable  true is on and false is off, default off
         */
        void EnableStitchFusion(bool enable);

        /**
         * \brief Whether to turn on cooling shell detection
         * \param enable  true is on and false is off, default off
         */
        void EnableCoolingShellDetection(bool enable);

        /**
        * \brief set CameraAccessoryType
        */
        void SetCameraAccessoryType(CameraAccessoryType type);

        /**
         * \brief start stitch, this function is called synchronously.
         */
        bool Stitch();

        /**
         * \brief set exposure
         * \param exposure range[-100,100]
         */
        void SetExposure(int exposure);

        /**
         * \brief set highlights
         * \param highlights range[-100,100]
         */
        void SetHighlights(int highlights);

        /**
         * \brief set shadows
         * \param shadows range[-100,100]
        */
        void SetShadows(int shadows);

        /**
         * \brief set contrast
         * \param contrast range[-100,100]
        */
        void SetContrast(int contrast);

        /**
         * \brief set brightness
         * \param brightness range[-100,100]
         */
        void SetBrightness(int brightness);

        /**
         * \brief set blackpoint
         * \param blackpoint range[-100,100]
         */
        void SetBlackpoint(int blackpoint);

        /**
         * \brief set saturation
         * \param saturation range[-100,100]
         */
        void SetSaturation(int saturation);

        /**
         * \brief set vibrance
         * \param vibrance range[-100,100]
        */
        void SetVibrance(int vibrance);

        /**
         * \brief set warmth
         * \param warmth range[-100,100]
         */
        void SetWarmth(int warmth);

        /**
         * \brief set tint
         * \param tint range[-100,100]
         */
        void SetTint(int tint);

        /**
         * \brief set definition
         * \param contrast range[0, 100]
         */
        void SetDefinition(int definition);
    private:
        std::shared_ptr<StitcherImp> imp_;
    };
};