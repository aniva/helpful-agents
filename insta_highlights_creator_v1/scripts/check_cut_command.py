import json
import os

def main():
    log_path = "/mnt/c/Users/me/.gemini/antigravity/brain/64681769-3704-4a64-a001-c7bedf088c94/.system_generated/logs/transcript_full.jsonl"
    if not os.path.exists(log_path):
        log_path = "/mnt/c/Users/me/.gemini/antigravity/brain/64681769-3704-4a64-a001-c7bedf088c94/.system_generated/logs/transcript.jsonl"
        
    print(f"Reading {log_path}...")
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            content = str(d.get("content", ""))
            tool_calls = str(d.get("tool_calls", ""))
            if "temp_front_30s" in content or "temp_front_30s" in tool_calls:
                print(f"Step {d.get('step_index')}:")
                if "CommandLine" in tool_calls:
                    print("  Tool call:", tool_calls)
                else:
                    # Truncate content to keep output small
                    print("  Content:", content[:200])

if __name__ == "__main__":
    main()
