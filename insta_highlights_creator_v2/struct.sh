#!/bin/bash

# Define workspace directory names using camelCase formatting
projectRoot="kitefoilPipeline"
rawIngest="rawIngest"
processScratch="processScratch"
outputHighlights="outputHighlights"
sdkInclude="thirdParty/insta360Sdk/include"
sdkLib="thirdParty/insta360Sdk/lib"
buildDir="build"

echo "Initializing automated kitefoil pipeline workspace structure..."

# Create core project tree paths
mkdir -p "$projectRoot/$rawIngest"
mkdir -p "$projectRoot/$processScratch"
mkdir -p "$projectRoot/$outputHighlights"
mkdir -p "$projectRoot/$sdkInclude"
mkdir -p "$projectRoot/$sdkLib"
mkdir -p "$projectRoot/$buildDir"

# Generate empty placeholder files for development targeting
touch "$projectRoot/CMakeLists.txt"
touch "$projectRoot/main.cpp"
touch "$projectRoot/extractHighlights.py"
touch "$projectRoot/runPipeline.sh"

# Apply executable permissions to script configurations
chmod +x "$projectRoot/runPipeline.sh"

echo "Workspace generation completed successfully."
echo "Navigate to the project root directory using: cd $projectRoot"
