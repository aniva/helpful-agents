import os
import sys
import subprocess
import json
import xml.etree.ElementTree as ET

# Reconfigure stdout and stderr to handle UTF-8 characters (Cyrillic file names)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    return res.stdout

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", file_path
    ]
    res_json = json.loads(run_cmd(cmd))
    duration = float(res_json.get("format", {}).get("duration", 0))
    return duration

def main():
    gopro_dir = "E:/20260627_GoPro"
    music_dir = "D:/Users/me/Music/Rybnikov_all"
    
    # 1. Concat Jan 25th clips
    jan25_files = [
        "GX015251.MP4",
        "GX015252.MP4",
        "GX015253.MP4",
        "GX015254.MP4",
        "GX015255.MP4"
    ]
    
    merged_jan25_path = os.path.join(gopro_dir, "merged_Jan25.MP4").replace("\\", "/")
    
    if not os.path.exists(merged_jan25_path):
        print("Concatenating Jan 25th clips losslessly...")
        concat_list_path = os.path.join(gopro_dir, "concat_list.txt").replace("\\", "/")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for file_name in jan25_files:
                f.write(f"file '{gopro_dir}/{file_name}'\n")
        
        # Concat command
        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path, "-c", "copy", merged_jan25_path
        ]
        run_cmd(concat_cmd)
        print("Concatenation complete!")
    else:
        print("merged_Jan25.MP4 already exists, skipping concatenation.")

    # 2. Today's clip path
    today_clip_path = f"{gopro_dir}/GX015261.MP4"
    
    # Music tracks
    music_jan25_path = f"{music_dir}/Алексей Рыбников - Вечер из к_ф Усатый нянь.mp3"
    music_today_path = f"{music_dir}/Алексей Рыбников - Аморе, аморе Из к_ф _Серафим Полубес и другие жители Земли_.mp3"
    
    # Validate paths
    for p in [merged_jan25_path, today_clip_path, music_jan25_path, music_today_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Required file not found: {p}")

    # 3. Get exact durations
    dur_jan25 = get_duration(merged_jan25_path)
    dur_today = get_duration(today_clip_path)
    dur_music_jan25 = get_duration(music_jan25_path)
    dur_music_today = get_duration(music_today_path)
    
    print(f"Durations:")
    print(f"  Jan 25th merged: {dur_jan25:.3f}s")
    print(f"  Today:           {dur_today:.3f}s")
    print(f"  Music Jan 25th:  {dur_music_jan25:.3f}s")
    print(f"  Music Today:     {dur_music_today:.3f}s")
    
    # 4. Frame rate calculation (GoPro 59.94 fps)
    fps_num = 60000
    fps_den = 1001
    fps = fps_num / fps_den
    
    frames_jan25 = int(round(dur_jan25 * fps))
    frames_today = int(round(dur_today * fps))
    frames_music_jan25 = int(round(dur_music_jan25 * fps))
    frames_music_today = int(round(dur_music_today * fps))
    
    print(f"Frame counts:")
    print(f"  Jan 25th merged: {frames_jan25} frames")
    print(f"  Today:           {frames_today} frames")
    print(f"  Music Jan 25th:  {frames_music_jan25} frames")
    print(f"  Music Today:     {frames_music_today} frames")

    # 5. Build MLT XML
    mlt = ET.Element("mlt", version="7.19.0", title="GoPro Instagram Edit", producer="main_bin")
    
    # 4:5 aspect ratio profile (1080x1350)
    profile = ET.SubElement(mlt, "profile", 
                            id="custom", 
                            width="1080", 
                            height="1350", 
                            sample_aspect_num="1", 
                            sample_aspect_den="1", 
                            display_aspect_num="4", 
                            display_aspect_den="5", 
                            frame_rate_num=str(fps_num), 
                            frame_rate_den=str(fps_den), 
                            colorspace="709", 
                            progressive="1")
    
    # Producers (Media Sources)
    prod_jan25 = ET.SubElement(mlt, "producer", id="producer_jan25", attrib={"in": "0", "out": str(frames_jan25 - 1)})
    ET.SubElement(prod_jan25, "property", name="resource").text = merged_jan25_path
    ET.SubElement(prod_jan25, "property", name="audio_index").text = "-1" # Mutes original audio!
    
    prod_today = ET.SubElement(mlt, "producer", id="producer_today", attrib={"in": "0", "out": str(frames_today - 1)})
    ET.SubElement(prod_today, "property", name="resource").text = today_clip_path
    ET.SubElement(prod_today, "property", name="audio_index").text = "-1" # Mute today's original audio too for clean music edit (user can unmute V1 if desired)

    prod_music_jan25 = ET.SubElement(mlt, "producer", id="producer_music_jan25", attrib={"in": "0", "out": str(frames_music_jan25 - 1)})
    ET.SubElement(prod_music_jan25, "property", name="resource").text = music_jan25_path
    # Volume filter to 40% (gain = -7.96 dB approx, level = 0.4)
    vol_filter = ET.SubElement(prod_music_jan25, "filter", id="filter_volume_jan25")
    ET.SubElement(vol_filter, "property", name="mlt_service").text = "volume"
    ET.SubElement(vol_filter, "property", name="level").text = "0.4"
    
    prod_music_today = ET.SubElement(mlt, "producer", id="producer_music_today", attrib={"in": "0", "out": str(frames_music_today - 1)})
    ET.SubElement(prod_music_today, "property", name="resource").text = music_today_path

    # Playlists
    # Main project media bin
    main_bin = ET.SubElement(mlt, "playlist", id="main_bin")
    ET.SubElement(main_bin, "property", name="xml_retain").text = "1"
    ET.SubElement(main_bin, "entry", producer="producer_jan25")
    ET.SubElement(main_bin, "entry", producer="producer_today")
    ET.SubElement(main_bin, "entry", producer="producer_music_jan25")
    ET.SubElement(main_bin, "entry", producer="producer_music_today")

    # Track V1: Video Playlist
    playlist_video = ET.SubElement(mlt, "playlist", id="playlist_video")
    ET.SubElement(playlist_video, "property", name="shotcut:video").text = "1"
    ET.SubElement(playlist_video, "property", name="shotcut:name").text = "V1"
    ET.SubElement(playlist_video, "entry", producer="producer_jan25", attrib={"in": "0", "out": str(frames_jan25 - 1)})
    ET.SubElement(playlist_video, "entry", producer="producer_today", attrib={"in": "0", "out": str(frames_today - 1)})

    # Track A1: Audio Playlist (Music for Jan 25th)
    playlist_audio_jan25 = ET.SubElement(mlt, "playlist", id="playlist_audio_jan25")
    ET.SubElement(playlist_audio_jan25, "property", name="shotcut:audio").text = "1"
    ET.SubElement(playlist_audio_jan25, "property", name="shotcut:name").text = "A1"
    
    # Loop music for Jan 25th
    rem = frames_jan25
    while rem > 0:
        if rem >= frames_music_jan25:
            ET.SubElement(playlist_audio_jan25, "entry", producer="producer_music_jan25", attrib={"in": "0", "out": str(frames_music_jan25 - 1)})
            rem -= frames_music_jan25
        else:
            ET.SubElement(playlist_audio_jan25, "entry", producer="producer_music_jan25", attrib={"in": "0", "out": str(rem - 1)})
            rem = 0
    # Blank silence for the today's video portion
    ET.SubElement(playlist_audio_jan25, "blank", length=str(frames_today))

    # Track A2: Audio Playlist (Music for Today)
    playlist_audio_today = ET.SubElement(mlt, "playlist", id="playlist_audio_today")
    ET.SubElement(playlist_audio_today, "property", name="shotcut:audio").text = "1"
    ET.SubElement(playlist_audio_today, "property", name="shotcut:name").text = "A2"
    # Blank silence during Jan 25th video portion
    ET.SubElement(playlist_audio_today, "blank", length=str(frames_jan25))
    
    # Loop music for Today
    rem = frames_today
    while rem > 0:
        if rem >= frames_music_today:
            ET.SubElement(playlist_audio_today, "entry", producer="producer_music_today", attrib={"in": "0", "out": str(frames_music_today - 1)})
            rem -= frames_music_today
        else:
            ET.SubElement(playlist_audio_today, "entry", producer="producer_music_today", attrib={"in": "0", "out": str(rem - 1)})
            rem = 0

    # Tractor (Timeline Container)
    tractor = ET.SubElement(mlt, "tractor", id="timeline", global_feed="1")
    ET.SubElement(tractor, "track", producer="playlist_video")
    ET.SubElement(tractor, "track", producer="playlist_audio_jan25")
    ET.SubElement(tractor, "track", producer="playlist_audio_today")

    # Audio Mix Transitions
    trans1 = ET.SubElement(tractor, "transition", id="transition_mix_0_1")
    ET.SubElement(trans1, "property", name="a_track").text = "0"
    ET.SubElement(trans1, "property", name="b_track").text = "1"
    ET.SubElement(trans1, "property", name="mlt_service").text = "mix"
    ET.SubElement(trans1, "property", name="combine").text = "1"

    trans2 = ET.SubElement(tractor, "transition", id="transition_mix_0_2")
    ET.SubElement(trans2, "property", name="a_track").text = "0"
    ET.SubElement(trans2, "property", name="b_track").text = "2"
    ET.SubElement(trans2, "property", name="mlt_service").text = "mix"
    ET.SubElement(trans2, "property", name="combine").text = "1"

    # Pretty print XML
    ET.indent(mlt, space="  ")
    
    # Write to MLT file
    mlt_file_path = os.path.join(gopro_dir, "gopro_instagram_4_5.mlt").replace("\\", "/")
    tree = ET.ElementTree(mlt)
    tree.write(mlt_file_path, encoding="utf-8", xml_declaration=True)
    print(f"Shotcut project file generated successfully: {mlt_file_path}")

    # Also generate a square version (1:1 aspect ratio)
    # Set the profile to square
    profile.set("width", "1080")
    profile.set("height", "1080")
    profile.set("display_aspect_num", "1")
    profile.set("display_aspect_den", "1")
    
    mlt_square_path = os.path.join(gopro_dir, "gopro_instagram_1_1.mlt").replace("\\", "/")
    tree.write(mlt_square_path, encoding="utf-8", xml_declaration=True)
    print(f"Shotcut square project file generated successfully: {mlt_square_path}")

if __name__ == "__main__":
    main()
