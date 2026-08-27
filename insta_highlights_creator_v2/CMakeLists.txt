cmake_minimum_required(VERSION 3.10)
project(insta360_stitcher CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/thirdParty/insta360Sdk/include)

# Library directories
link_directories(${CMAKE_CURRENT_SOURCE_DIR}/thirdParty/insta360Sdk/lib)

# Source files
add_executable(stitcher main.cpp)

# Link libraries
# In mock build mode (when libMediaSDK.so does not exist), we don't link the binary library.
# Since the mock headers implement all classes and methods inline, this will compile successfully.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/thirdParty/insta360Sdk/lib/libMediaSDK.so")
    target_link_libraries(stitcher MediaSDK)
    message(STATUS "Building linked with official Insta360 Media SDK library")
else()
    target_compile_definitions(stitcher PRIVATE MOCK_SDK_BUILD)
    message(STATUS "libMediaSDK.so not found, building in mock stub mode (for verification)")
endif()
