import os
import sys
import numpy as np
import cv2
import subprocess
from video_processor import FisheyeProjector, HighlightAnalyzer, HighlightGenerator, find_video_pairs

def create_dummy_videos():
    print("Creating mock front and rear camera video files...")
    
    # 300x300 resolution for testing
    width, height = 300, 300
    fps = 10
    duration_sec = 3
    num_frames = fps * duration_sec
    
    front_path = "VID_TEST_00_001.mp4"
    rear_path = "VID_TEST_10_001.mp4"
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer_f = cv2.VideoWriter(front_path, fourcc, fps, (width, height))
    writer_r = cv2.VideoWriter(rear_path, fourcc, fps, (width, height))
    
    for f in range(num_frames):
        # Front frame: simulating water with a rider (moving red circle)
        frame_f = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw circular fisheye boundary
        cv2.circle(frame_f, (width//2, height//2), width//2, (20, 20, 20), -1)
        # Draw horizon line
        cv2.rectangle(frame_f, (0, height//2), (width, height), (80, 40, 20), -1) # Water (BGR)
        cv2.rectangle(frame_f, (0, 0), (width, height//2), (180, 100, 50), -1) # Sky (BGR)
        # Draw moving rider (red dot)
        rx = int(width/2 + 50 * np.cos(2 * np.pi * f / num_frames))
        ry = int(height/2 + 30 + 10 * np.sin(2 * np.pi * f / num_frames))
        cv2.circle(frame_f, (rx, ry), 8, (0, 0, 255), -1)
        
        # Rear frame: simulating sky with a kite (moving green dot)
        frame_r = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw circular fisheye boundary
        cv2.circle(frame_r, (width//2, height//2), width//2, (20, 20, 20), -1)
        # Sky background
        cv2.rectangle(frame_r, (0, 0), (width, height), (200, 140, 60), -1)
        # Draw moving kite (green dot)
        kx = int(width/2 + 60 * np.sin(2 * np.pi * f / num_frames))
        ky = int(height/2 - 40 + 10 * np.cos(2 * np.pi * f / num_frames))
        cv2.circle(frame_r, (kx, ky), 12, (0, 255, 0), -1)
        
        writer_f.write(frame_f)
        writer_r.write(frame_r)
        
    writer_f.release()
    writer_r.release()
    print(f"Created dummy front video: {front_path}")
    print(f"Created dummy rear video:  {rear_path}")
    return front_path, rear_path

def create_dummy_music():
    print("Generating a dummy music track via FFmpeg...")
    music_path = "dummy_music.mp3"
    # Generate 3 seconds of sine wave beep
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', 
        '-acodec', 'libmp3lame', music_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"Created dummy music: {music_path}")
    return music_path

def clean_up_dummies(files):
    for f in files:
        if os.path.exists(f):
            os.remove(f)
    print("Cleaned up temporary mock files.")

def main():
    print("=== Start Automated Pipeline Verification ===")
    
    # 1. Create dummies
    front, rear = create_dummy_videos()
    music = create_dummy_music()
    temp_render = "verify_temp.mp4"
    final_output = "verify_final.mp4"
    
    files_to_clean = [front, rear, music, temp_render, final_output]
    
    try:
        # 2. Test video pair scanner
        print("\n[Test 1] Testing file pairing scanner...")
        pairs = find_video_pairs(".")
        print(f"Scanner found pairs: {pairs}")
        assert len(pairs) > 0, "No paired videos found by scanner"
        
        # 3. Test Projection Math
        print("\n[Test 2] Testing Fisheye Projection math...")
        proj = FisheyeProjector(640, 360, fov_deg=90)
        
        cap_f = cv2.VideoCapture(front)
        cap_r = cv2.VideoCapture(rear)
        ret_f, frame_f = cap_f.read()
        ret_r, frame_r = cap_r.read()
        cap_f.release()
        cap_r.release()
        
        assert ret_f and ret_r, "Failed to read dummy frames"
        
        out_frame = proj.project(frame_f, frame_r, yaw=np.radians(20), pitch=np.radians(-10), roll=np.radians(5))
        assert out_frame.shape == (360, 640, 3), f"Output shape mismatch: {out_frame.shape}"
        print("Projection completed successfully. Frame shape is correct.")
        
        # 4. Test YOLOv8 CPU Inference
        print("\n[Test 3] Testing YOLOv8 CPU model loading and inference...")
        # Running YOLOv8n on the projected frame
        analyzer = HighlightAnalyzer(model_size="n")
        res = analyzer.model(out_frame, verbose=False)[0]
        print(f"YOLOv8 initialized and successfully ran inference. Found {len(res.boxes)} bounding boxes.")
        
        # 5. Test Highlight generator rendering
        print("\n[Test 4] Testing Highlight Generator segment planning & rendering...")
        # Mock timeline metadata
        timeline = [
            {'timestamp': 0.0, 'frame_idx': 0, 'rider': {'conf': 0.9}, 'kite': None, 'scenery': False, 'scenery_count': 0},
            {'timestamp': 1.0, 'frame_idx': 10, 'rider': None, 'kite': {'conf': 0.85}, 'scenery': False, 'scenery_count': 0},
            {'timestamp': 2.0, 'frame_idx': 20, 'rider': None, 'kite': None, 'scenery': True, 'scenery_count': 2},
        ]
        
        # Generator for Instagram portrait aspect ratio (540x960)
        generator = HighlightGenerator(timeline, W_out=540, H_out=960, format_type="Instagram")
        segments = generator.plan_highlights(target_duration=3.0, p_rider=0.33, p_kite=0.33, p_scenery=0.33)
        print(f"Segments planned: {segments}")
        assert len(segments) > 0, "Failed to plan segments"
        
        generator.render_video(front, rear, segments, temp_render)
        assert os.path.exists(temp_render), "Failed to render reframed video file"
        print("Highlights rendering completed. File created.")
        
        # 6. Test FFmpeg Audio mixing
        print("\n[Test 5] Testing FFmpeg audio mixing...")
        generator.mix_audio(
            video_path=temp_render,
            source_audio_video=front,
            music_path=music,
            output_path=final_output,
            mix_music_ratio=0.7,
            mix_bg_ratio=0.3
        )
        assert os.path.exists(final_output), "Failed to mix audio and generate final output video"
        print(f"Final output video generated successfully: {final_output}")
        
        print("\n=== Verification Successful! All pipeline tests passed. ===")
        
    except Exception as e:
        print(f"\nVerification Failed! Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        clean_up_dummies(files_to_clean)

if __name__ == "__main__":
    main()
