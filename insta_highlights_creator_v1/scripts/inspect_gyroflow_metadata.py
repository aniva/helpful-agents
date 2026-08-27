import json
import os

def main():
    path = "/mnt/c/Users/me/.gemini/antigravity/scratch/metadata.json"
    print(f"Loading {path}...")
    with open(path, "r") as f:
        d = json.load(f)
        
    print(f"Root object type: {type(d)}")
    if isinstance(d, list):
        print(f"List length: {len(d)}")
        if len(d) > 0:
            print("Keys / Types of elements in the list:")
            element_types = set(type(x) for x in d)
            print(f"Element types: {element_types}")
            
            # Print first element
            first = d[0]
            print(f"First element type: {type(first)}")
            if isinstance(first, dict):
                print(f"First element keys: {first.keys()}")
                for k, v in first.items():
                    print(f"  {k}: type={type(v)}")
                    if isinstance(v, list) and len(v) > 0:
                        print(f"    list length={len(v)}, first element={v[0]}")
                    elif isinstance(v, dict):
                        print(f"    dict keys={v.keys()}")
    elif isinstance(d, dict):
        print(f"Dict keys: {d.keys()}")
        
if __name__ == "__main__":
    main()
