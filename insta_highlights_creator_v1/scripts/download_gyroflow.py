import os
import urllib.request
import json
import zipfile

def main():
    if os.name == 'posix':
        scratch_dir = "/mnt/c/Users/me/.gemini/antigravity/scratch"
    else:
        scratch_dir = r"C:\Users\me\.gemini\antigravity\scratch"
    zip_path = os.path.join(scratch_dir, "Gyroflow-windows64.zip")
    extract_path = os.path.join(scratch_dir, "Gyroflow")
    
    print("Fetching latest Gyroflow release metadata from GitHub...")
    req = urllib.request.Request(
        "https://api.github.com/repos/gyroflow/gyroflow/releases/latest",
        headers={"User-Agent": "Antigravity-AI-Coding-Assistant"}
    )
    with urllib.request.urlopen(req) as response:
        metadata = json.loads(response.read().decode())
        
    download_url = None
    for asset in metadata.get("assets", []):
        if asset.get("name", "").endswith("windows64.zip"):
            download_url = asset.get("browser_download_url")
            break
            
    if not download_url:
        print("Error: Could not find Gyroflow-windows64.zip in the latest release assets.")
        return
        
    print(f"Downloading Gyroflow from: {download_url}")
    urllib.request.urlretrieve(download_url, zip_path)
    print("Download completed. Extracting zip archive...")
    
    os.makedirs(extract_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)
        
    print(f"Successfully extracted Gyroflow to: {extract_path}")
    
    # Remove the zip file
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
if __name__ == "__main__":
    main()
