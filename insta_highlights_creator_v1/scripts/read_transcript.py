import json
import sys

def main():
    path = "/mnt/c/Users/me/.gemini/antigravity/brain/64681769-3704-4a64-a001-c7bedf088c94/.system_generated/logs/transcript.jsonl"
    with open(path, "r") as f:
        for line in f:
            try:
                x = json.loads(line)
                idx = x.get("step_index", 0)
                if 1040 <= idx <= 1066:
                    print(f"================ Step {idx} ({x.get('source')} -> {x.get('type')}) ================")
                    print(f"Thinking: {x.get('thinking')}")
                    content = x.get('content')
                    if content:
                        print(f"Content (truncated): {content[:800]}")
                    tc = x.get('tool_calls')
                    if tc:
                        print(f"Tool calls: {json.dumps(tc, indent=2)}")
            except Exception as e:
                pass

if __name__ == "__main__":
    main()
