import json
import os

def main():
    path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    print(f"Type of root: {type(d)}")
    if isinstance(d, list):
        print(f"Length of list: {len(d)}")
        if len(d) > 0:
            first = d[0]
            print(f"Type of first element: {type(first)}")
            if isinstance(first, dict):
                print(f"First element keys: {list(first.keys())}")
                for k, v in first.items():
                    if isinstance(v, dict):
                        print(f"  Key '{k}': dict with keys {list(v.keys())}")
                    else:
                        print(f"  Key '{k}': type={type(v)}")
    elif isinstance(d, dict):
        print("Root is a dict.")
        
if __name__ == "__main__":
    main()
