#!/bin/bash
set -e

# Defaults
MODE="sdk"
THRESHOLD="2.5"
GYROFLOW_PROJECT=""
INPUT_FILES=()
CPU="false"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --mode) MODE="$2"; shift ;;
        --threshold) THRESHOLD="$2"; shift ;;
        --gyroflow) GYROFLOW_PROJECT="$2"; shift ;;
        --cpu) CPU="true" ;;
        --input)
            shift
            while [[ "$#" -gt 0 && ! "$1" =~ ^-- ]]; do
                INPUT_FILES+=("$1")
                shift
            done
            continue
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Define CPU flags if requested
CPU_FLAGS=""
if [ "$CPU" = "true" ]; then
    CPU_FLAGS="-disable_cuda -enable_soft_encode -enable_soft_decode -image_processing_accel cpu"
    echo "[Pipeline] CPU Mode requested. Disabling CUDA and enabling software codecs."
fi

# Validation
if [ ${#INPUT_FILES[@]} -eq 0 ]; then
    echo "Error: No input files specified with --input"
    exit 1
fi
# If GYROFLOW_PROJECT is not specified, or if it doesn't exist, we try to auto-generate it from the first input INSV file!
if [ -z "$GYROFLOW_PROJECT" ]; then
    FIRST_INPUT="${INPUT_FILES[0]}"
    # Replace suffix with .gyroflow
    GYROFLOW_PROJECT="${FIRST_INPUT%.insv}.gyroflow"
    GYROFLOW_PROJECT="${GYROFLOW_PROJECT%.lrv}.gyroflow"
fi

if [ ! -f "$GYROFLOW_PROJECT" ]; then
    echo "[Pipeline] Gyroflow project file not found. Auto-generating from input: ${INPUT_FILES[0]}..."
    
    WIN_INPUT=$(wslpath -w "${INPUT_FILES[0]}")
    # Run Gyroflow to export the project
    /mnt/c/Users/me/.gemini/antigravity/scratch/Gyroflow/Gyroflow.exe "$WIN_INPUT" --export-project 2 -f
    
    # Check if export was successful (Gyroflow might save as .gyroflow in the same folder)
    if [ ! -f "$GYROFLOW_PROJECT" ]; then
        # Check if it was exported with lowercase extension or slightly different name
        BASE_GYRO="${INPUT_FILES[0]%.*}.gyroflow"
        if [ -f "$BASE_GYRO" ]; then
            GYROFLOW_PROJECT="$BASE_GYRO"
        else
            echo "Error: Failed to auto-generate Gyroflow project file at $GYROFLOW_PROJECT"
            exit 1
        fi
    fi
    echo "[Pipeline] Successfully auto-generated project file: $GYROFLOW_PROJECT"
fi

# Ensure workspace folders exist
mkdir -p rawIngest processScratch outputHighlights build

# 1. Compile C++ Stitcher
echo "========================================="
echo "[Pipeline] Compiling C++ Headless Stitcher..."
echo "========================================="
if command -v cmake &> /dev/null; then
    cd build
    cmake ..
    make -j$(nproc 2>/dev/null || echo 1)
    cd ..
else
    echo "[Pipeline] CMake not found. Compiling directly with g++..."
    if [ -f "thirdParty/insta360Sdk/lib/libMediaSDK.so" ]; then
        g++ -std=c++17 -I./thirdParty/insta360Sdk/include -L./thirdParty/insta360Sdk/lib \
            -Wl,-rpath,'$ORIGIN/../thirdParty/insta360Sdk/lib' -Wl,--disable-new-dtags -Wl,-rpath-link,./thirdParty/insta360Sdk/lib \
            -o build/stitcher main.cpp \
            -lMediaSDK -lMNN_Cuda_Main -lMNN -lssl -lcrypto -ltbb -lwz265 -ltscsdk_center -liconv -lcudart -lnppc -lnppial -lnppicc -lnppidei -lnppig -lnppist
    else
        g++ -std=c++17 -I./thirdParty/insta360Sdk/include -o build/stitcher main.cpp
    fi
fi

STITCHER="./build/stitcher"

# Clean scratch space
rm -f processScratch/*

if [ "$MODE" = "sdk" ]; then
    echo "========================================="
    echo "[Pipeline] Running Option A: SDK-Native Stabilization..."
    echo "========================================="
    
    # Run stitcher with stabilization flags
    LD_LIBRARY_PATH=./thirdParty/insta360Sdk/lib $STITCHER -inputs "${INPUT_FILES[@]}" -output processScratch/stitched_stabilized.mp4 -enable_flowstate -enable_directionlock -model_root_dir thirdParty/insta360Sdk/models/ $CPU_FLAGS
    
    MASTER_VIDEO="processScratch/stitched_stabilized.mp4"
    
elif [ "$MODE" = "gyroflow" ]; then
    echo "========================================="
    echo "[Pipeline] Running Option B: Gyroflow CLI Stabilization..."
    echo "========================================="
    
    # Run stitcher unstabilized
    LD_LIBRARY_PATH=./thirdParty/insta360Sdk/lib $STITCHER -inputs "${INPUT_FILES[@]}" -output processScratch/stitched_unstabilized.mp4 -model_root_dir thirdParty/insta360Sdk/models/ $CPU_FLAGS
    
    echo "[Pipeline] Running Gyroflow CLI render..."
    # Translate Gyroflow project path to Windows path for the executable
    WIN_GYROFLOW_PROJECT=$(wslpath -w "$GYROFLOW_PROJECT")
    
    # Run Gyroflow on the Windows host using its executable
    # Overwrite if exists, print progress to stdout
    /mnt/c/Users/me/.gemini/antigravity/scratch/Gyroflow/Gyroflow.exe "$WIN_GYROFLOW_PROJECT" -f --stdout-progress
    
    # The output is expected to be placed next to the project file or video file.
    # Typically, Gyroflow outputs with _stabilized suffix next to the video file:
    # processScratch/stitched_unstabilized_stabilized.mp4
    # We will locate it and rename it to processScratch/stitched_stabilized.mp4
    if [ -f "processScratch/stitched_unstabilized_stabilized.mp4" ]; then
        mv processScratch/stitched_unstabilized_stabilized.mp4 processScratch/stitched_stabilized.mp4
    elif [ -f "${GYROFLOW_PROJECT%.gyroflow}_stabilized.mp4" ]; then
        mv "${GYROFLOW_PROJECT%.gyroflow}_stabilized.mp4" processScratch/stitched_stabilized.mp4
    else
        # Search the directory for any newly rendered mp4 files containing 'stabilized'
        FOUND_STAB=$(find processScratch -name "*_stabilized.mp4" | head -n 1)
        if [ -n "$FOUND_STAB" ]; then
            mv "$FOUND_STAB" processScratch/stitched_stabilized.mp4
        else
            echo "Error: Gyroflow did not produce a stabilized video in processScratch."
            exit 1
        fi
    fi
    
    MASTER_VIDEO="processScratch/stitched_stabilized.mp4"
else
    echo "Error: Unknown mode $MODE. Use 'sdk' or 'gyroflow'."
    exit 1
fi

# 3. Slice Highlights
echo "========================================="
echo "[Pipeline] Running Telemetry Highlights Slicing..."
echo "========================================="
python3 extractHighlights.py \
    --video "$MASTER_VIDEO" \
    --gyroflow "$GYROFLOW_PROJECT" \
    --output-dir outputHighlights \
    --threshold "$THRESHOLD"

echo "========================================="
echo "[Pipeline] Master Pipeline Completed Successfully!"
echo "Highlights available in: outputHighlights/"
echo "========================================="
