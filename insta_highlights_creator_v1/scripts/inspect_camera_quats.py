import json

def main():
    path = "/mnt/c/Users/me/.gemini/antigravity/scratch/camera.json"
    with open(path, "r") as f:
        d = json.load(f)
        
    for i in range(min(5, len(d))):
        print(f"\n--- Element {i} ---")
        for k in ['frame', 'timestamp_ms', 'org_quat', 'stab_quat', 'stab_euler']:
            print(f"  {k}: {d[i].get(k)}")

if __name__ == "__main__":
    main()
