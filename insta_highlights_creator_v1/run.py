import os
import argparse
import sys
from video_processor import find_video_pairs, HighlightAnalyzer, HighlightGenerator, prepare_input_videos

def main():
    parser = argparse.ArgumentParser(
        description="Insta360 X5 Kitefoil Highlights Creator - Command Line Interface"
    )
    
    parser.add_argument("--front", required=True, help="Path to front lens video (_00_.insv/mp4 or multi-stream single file)")
    parser.add_argument("--rear", help="Path to rear lens video (_10_.insv/mp4). Omit if using single multi-stream file.")
    parser.add_argument("--music", help="Path to soundtrack audio/MP3")
    parser.add_argument("--duration", type=float, default=300.0, help="Target highlight duration in seconds (default: 300)")
    parser.add_argument("--rider", type=float, default=0.2, help="Focus percentage on Rider (0.0 to 1.0, default: 0.2)")
    parser.add_argument("--kite", type=float, default=0.3, help="Focus percentage on Kite (0.0 to 1.0, default: 0.3)")
    parser.add_argument("--scenery", type=float, default=0.5, help="Focus percentage on Scenery/Objects (0.0 to 1.0, default: 0.5)")
    parser.add_argument("--format", choices=["YT", "Instagram"], default="YT", help="Output format: YT (16:9) or Instagram (9:16) (default: YT)")
    parser.add_argument("--resolution", choices=["1080p", "4k"], default="1080p", help="Output resolution: 1080p or 4k (default: 1080p)")
    parser.add_argument("--mix-music", type=float, default=0.7, help="Music soundtrack volume (0.0 to 1.0, default: 0.7)")
    parser.add_argument("--mix-bg", type=float, default=0.3, help="Background ambient volume (0.0 to 1.0, default: 0.3)")
    parser.add_argument("--output", default="final_output.mp4", help="Output video path (default: final_output.mp4)")
    parser.add_argument("--preview", action="store_true", help="Generate a short 30-second low-resolution draft preview")
    parser.add_argument("--template", help="Path to template screenshot image for locating target view t1")
    
    args = parser.parse_args()
    
    # Validation
    if not os.path.exists(args.front):
        print(f"Error: Front video file not found at '{args.front}'")
        sys.exit(1)
    if args.rear and not os.path.exists(args.rear):
        print(f"Error: Rear video file not found at '{args.rear}'")
        sys.exit(1)
    if args.music and not os.path.exists(args.music):
        print(f"Warning: Music file not found at '{args.music}'. Rendering with ambient audio only.")
    if args.template and not os.path.exists(args.template):
        print(f"Error: Template screenshot file not found at '{args.template}'")
        sys.exit(1)
        
    total_ratio = args.rider + args.kite + args.scenery
    if not (0.99 <= total_ratio <= 1.01):
        print("Warning: Highlight focus percentages do not sum to 1.0. Normalizing values.")
        r_sum = args.rider + args.kite + args.scenery
        args.rider /= r_sum
        args.kite /= r_sum
        args.scenery /= r_sum
        
    print("\n=== Insta360 Highlights Creator CLI ===")
    print(f"Front Lens:  {args.front}")
    print(f"Rear Lens:   {args.rear if args.rear else '(Will extract from front video)'}")
    print(f"Format:      {args.format} ({'9:16 Vertical' if args.format == 'Instagram' else '16:9 Horizontal'})")
    print(f"Resolution:  {args.resolution}")
    print(f"Target Dur:  {args.duration}s" if not args.preview else "Target Dur: 30s (Draft Preview Mode)")
    if args.template:
        print(f"Template Tpl: {args.template} (Locking onto matching view)")
    else:
        print(f"Focus Dist:  Rider {args.rider*100:.1f}%, Kite {args.kite*100:.1f}%, Scenery {args.scenery*100:.1f}%")
    print("=======================================\n")
    
    # Extract tracks if multi-stream
    output_dir = os.path.dirname(args.output) if os.path.dirname(args.output) else "."
    video_front, video_rear, is_temp = prepare_input_videos(args.front, args.rear, output_dir)
    
    temp_video = os.path.join(output_dir, "temp_render.mp4")
    
    try:
        # 1. Analysis
        print("[1/4] Running YOLOv8 Object Tracking...")
        analyzer = HighlightAnalyzer(model_size="n")
        
        def log_scan_prog(p):
            sys.stdout.write(f"\rScanning Video: {p*100:.1f}% completed")
            sys.stdout.flush()
            
        timeline = analyzer.analyze_video(video_front, video_rear, progress_callback=log_scan_prog)
        print("\nScan completed successfully.")
        
        # 2. Plan segments
        print("[2/4] Slicing highlights...")
        render_duration = 30.0 if args.preview else args.duration
        
        # Set resolution based on format, resolution choice, and preview status
        if args.preview:
            W_out, H_out = (540, 960) if args.format == "Instagram" else (960, 540)
        else:
            if args.resolution == "4k":
                W_out, H_out = (2160, 3840) if args.format == "Instagram" else (3840, 2160)
            else:
                W_out, H_out = (1080, 1920) if args.format == "Instagram" else (1920, 1080)
            
        generator = HighlightGenerator(timeline, video_path_front=video_front, W_out=W_out, H_out=H_out, format_type=args.format)
        
        if args.template:
            t1 = generator.find_matching_timestamp(video_front, args.template)
            # Define segment of target duration from the matched t1 start point
            segments = [{'start': t1, 'end': t1 + render_duration, 'type': 'rider'}]
            print(f"Matched view in template screenshot! Lock-on start time set to t1 = {t1:.2f}s.")
        else:
            segments = generator.plan_highlights(render_duration, args.rider, args.kite, args.scenery)
            print(f"Planned {len(segments)} highlight clips.")
        
        # 3. Render
        print("[3/4] Rendering reframed perspectives and stabilizing horizon...")
        
        def log_render_prog(p):
            sys.stdout.write(f"\rRendering Video: {p*100:.1f}% completed")
            sys.stdout.flush()
            
        generator.render_video(video_front, video_rear, segments, temp_video, progress_callback=log_render_prog)
        print("\nRendering completed.")
        
        # 4. Audio Mixing
        print("[4/4] Mixing soundtrack and ambient audio via FFmpeg...")
        try:
            if not args.music or not os.path.exists(args.music):
                # Create a silent track or copy without audio if no music provided
                cmd_mix = ['ffmpeg', '-y', '-i', temp_video, '-i', args.front, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-shortest', args.output]
                import subprocess
                subprocess.run(cmd_mix, capture_output=True, check=True)
            else:
                generator.mix_audio(temp_video, args.front, args.music, args.output, 
                                    mix_music_ratio=args.mix_music, mix_bg_ratio=args.mix_bg)
            print("Audio mixing completed.")
        except Exception as e:
            print(f"Error mixing audio: {e}. Outputting video without soundtrack.")
            if os.path.exists(temp_video):
                os.rename(temp_video, args.output)
                
    finally:
        # Clean up temp files
        if os.path.exists(temp_video):
            os.remove(temp_video)
        if is_temp:
            if os.path.exists(video_front):
                os.remove(video_front)
            if os.path.exists(video_rear):
                os.remove(video_rear)
            print("Cleaned up temporary demuxed tracks.")
            
    print(f"\nSuccess! Highlights video created at: '{os.path.abspath(args.output)}'")

if __name__ == "__main__":
    main()
