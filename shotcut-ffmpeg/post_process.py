import os
import sys
import subprocess
import json
import xml.etree.ElementTree as ET
import argparse
import socket
import http.server
import socketserver
import threading
import qrcode

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

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def parse_timecode_or_frames(value, fps):
    if not value:
        return 0
    value_str = str(value).strip()
    if ":" in value_str:
        # Timecode format: HH:MM:SS.MS or HH:MM:SS:FF
        parts = value_str.split(":")
        if len(parts) == 3:
            h, m, s = parts
            if "." in s:
                sec, ms = s.split(".")
                total_sec = int(h) * 3600 + int(m) * 60 + int(sec) + float("0." + ms)
                return int(round(total_sec * fps))
            else:
                total_sec = int(h) * 3600 + int(m) * 60 + int(s)
                return int(round(total_sec * fps))
        elif len(parts) == 4:
            # HH:MM:SS:FF
            h, m, s, f = parts
            total_sec = int(h) * 3600 + int(m) * 60 + int(s)
            frames = int(round(total_sec * fps)) + int(f)
            return frames
    else:
        try:
            return int(value_str)
        except ValueError:
            try:
                return int(round(float(value_str) * fps))
            except ValueError:
                return 0

def start_server(file_to_serve, port=8080):
    class SingleFileHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/video.mp4':
                self.send_response(200)
                self.send_header('Content-type', 'video/mp4')
                self.send_header('Content-Length', str(os.path.getsize(file_to_serve)))
                self.end_headers()
                with open(file_to_serve, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

    handler = SingleFileHandler
    server = socketserver.TCPServer(("", port), handler)
    print(f"\n[Server] Serving {file_to_serve} at port {port}...")
    
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server

def main():
    parser = argparse.ArgumentParser(description="GoPro Instagram Video Post-Processing Pipeline")
    parser.add_argument("--draft", default="E:/20260627_GoPro/draft.mlt", help="Path to draft MLT file from Shotcut")
    parser.add_argument("--aspect", choices=["1:1", "4:5"], default="1:1", help="Aspect ratio for output (1:1 or 4:5)")
    parser.add_argument("--title", default="My Video Highlight\n2026", help="Title text overlay at start")
    parser.add_argument("--end", default="Thanks for watching!", help="Credits text overlay at end")
    parser.add_argument("--no-render", action="store_false", dest="render", help="Skip rendering the final video (generate MLT only)")
    parser.add_argument("--gpu", action="store_true", help="Use Nvidia GPU hardware acceleration (NVENC)")
    
    args = parser.parse_args()
    args.title = args.title.replace('\\n', '\n')
    args.end = args.end.replace('\\n', '\n')
    draft_path = args.draft.replace("\\", "/")
    if not os.path.exists(draft_path):
        print(f"Error: Draft file not found at {draft_path}")
        print("Please save your visual cuts in Shotcut as 'draft.mlt' in the GoPro folder first.")
        sys.exit(1)

    gopro_dir = os.path.dirname(draft_path)
    music_dir = "D:/Users/me/Music/Rybnikov_all"
    
    music_jan25_path = f"{gopro_dir}/synth_lullaby.mp3"
    music_today_path = f"{gopro_dir}/synth_sport_beat.mp3"
    
    # 1. Parse draft.mlt
    print(f"Parsing draft project: {draft_path}...")
    tree = ET.parse(draft_path)
    root = tree.getroot()
    
    # Find all producers/chains and map them to their resources
    producers_map = {}
    for tag in ["producer", "chain"]:
        for prod in root.findall(tag):
            prod_id = prod.get("id")
            res_elem = prod.find("property[@name='resource']")
            if res_elem is not None:
                producers_map[prod_id] = res_elem.text.replace("\\", "/")
            
    print(f"Found {len(producers_map)} media assets in project.")

    # Find the main video track (V1)
    # Shotcut uses playlist elements for tracks on timeline
    video_playlist = None
    for playlist in root.findall("playlist"):
        is_video = playlist.find("property[@name='shotcut:video']")
        if is_video is not None and is_video.text == "1":
            video_playlist = playlist
            break
            
    if video_playlist is None:
        print("Error: Could not find video track V1 in draft project.")
        sys.exit(1)
        
    # Get all entries (cuts) on the video track
    entries = video_playlist.findall("entry")
    if not entries:
        print("Error: Video track V1 is empty. Please make some cuts in Shotcut first.")
        sys.exit(1)
        
    print(f"Detected {len(entries)} cuts on the video timeline.")

    # 2. Re-calculate durations and frames
    fps_num = 60000
    fps_den = 1001
    fps = fps_num / fps_den
    
    # Group timeline entries into Jan 25th vs Today segments
    # Jan 25th files: contain "merged_Jan25" or "GX01525"
    # Today's files: contain "GX01526"
    frames_jan25 = 0
    frames_today = 0
    
    new_entries = []
    for entry in entries:
        prod_id = entry.get("producer")
        res_path = producers_map.get(prod_id, "")
        
        # Calculate clip duration in frames
        in_frame = parse_timecode_or_frames(entry.get("in", 0), fps)
        out_frame = parse_timecode_or_frames(entry.get("out", 0), fps)
        clip_frames = (out_frame - in_frame) + 1
        
        is_jan25 = "merged_Jan25" in res_path or any(f"GX01525{i}" in res_path for i in range(1, 6))
        
        if is_jan25:
            frames_jan25 += clip_frames
        else:
            frames_today += clip_frames
            
        new_entries.append({
            "producer": prod_id,
            "in": in_frame,
            "out": out_frame,
            "frames": clip_frames,
            "is_jan25": is_jan25
        })
        
    total_frames = frames_jan25 + frames_today
    print(f"Total video timeline frames: {total_frames} ({total_frames / fps:.2f}s)")
    print(f"  Jan 25th segment: {frames_jan25} frames ({frames_jan25 / fps:.2f}s)")
    print(f"  Today segment:    {frames_today} frames ({frames_today / fps:.2f}s)")

    # Get music durations
    dur_music_jan25 = get_duration(music_jan25_path)
    dur_music_today = get_duration(music_today_path)
    frames_music_jan25 = int(round(dur_music_jan25 * fps))
    frames_music_today = int(round(dur_music_today * fps))

    # 3. Create the final MLT XML structure
    mlt = ET.Element("mlt", version="7.19.0", title="GoPro Instagram Auto-Edited", producer="main_bin")
    
    # Configure Profile
    w, h, aspect_num, aspect_den = ("2160", "2700", "4", "5") if args.aspect == "4:5" else ("2160", "2160", "1", "1")
    profile = ET.SubElement(mlt, "profile", 
                            id="custom", 
                            width=w, 
                            height=h, 
                            sample_aspect_num="1", 
                            sample_aspect_den="1", 
                            display_aspect_num=aspect_num, 
                            display_aspect_den=aspect_den, 
                            frame_rate_num=str(fps_num), 
                            frame_rate_den=str(fps_den), 
                            colorspace="709", 
                            progressive="1")
    
    # Add video producers/chains with Crop filter and muted original sound
    # Copy from original MLT but modify properties
    for tag in ["producer", "chain"]:
        for elem in root.findall(tag):
            prod_id = elem.get("id")
            res_elem = elem.find("property[@name='resource']")
            if res_elem is not None:
                new_elem = ET.SubElement(mlt, tag, id=prod_id)
                new_elem.set("in", elem.get("in", "0"))
                new_elem.set("out", elem.get("out", "0"))
                for k, v in elem.attrib.items():
                    if k not in ["id", "in", "out"]:
                        new_elem.set(k, v)
                for child in elem:
                    if child.tag == "property":
                        name = child.get("name")
                        if name == "audio_index":
                            ET.SubElement(new_elem, "property", name="audio_index").text = "-1"
                        else:
                            prop = ET.SubElement(new_elem, "property", name=name)
                            prop.text = child.text
                            for k, v in child.attrib.items():
                                if k != "name":
                                    prop.set(k, v)
                audio_idx_elem = new_elem.find("property[@name='audio_index']")
                if audio_idx_elem is None:
                    ET.SubElement(new_elem, "property", name="audio_index").text = "-1"
            
    # Add music producers
    prod_music_jan25 = ET.SubElement(mlt, "producer", id="producer_music_jan25", attrib={"in": "0", "out": str(frames_music_jan25 - 1)})
    ET.SubElement(prod_music_jan25, "property", name="resource").text = music_jan25_path
    # Volume filter to 40%
    vol_filter = ET.SubElement(prod_music_jan25, "filter", id="filter_volume_jan25")
    ET.SubElement(vol_filter, "property", name="mlt_service").text = "volume"
    ET.SubElement(vol_filter, "property", name="level").text = "0.4"
    
    prod_music_today = ET.SubElement(mlt, "producer", id="producer_music_today", attrib={"in": "0", "out": str(frames_music_today - 1)})
    ET.SubElement(prod_music_today, "property", name="resource").text = music_today_path

    # Playlists
    main_bin = ET.SubElement(mlt, "playlist", id="main_bin")
    ET.SubElement(main_bin, "property", name="xml_retain").text = "1"
    for prod_id in producers_map.keys():
        ET.SubElement(main_bin, "entry", producer=prod_id)
    ET.SubElement(main_bin, "entry", producer="producer_music_jan25")
    ET.SubElement(main_bin, "entry", producer="producer_music_today")

    # Track V1: Sliced Video Playlist with Autofit Crop Filter
    playlist_video = ET.SubElement(mlt, "playlist", id="playlist_video")
    ET.SubElement(playlist_video, "property", name="shotcut:video").text = "1"
    ET.SubElement(playlist_video, "property", name="shotcut:name").text = "V1"
    
    for item in new_entries:
        entry = ET.SubElement(playlist_video, "entry", producer=item["producer"], attrib={"in": str(item["in"]), "out": str(item["out"])})
        # Add Crop Center filter to fit the conformed resolution without black bars
        crop_filt = ET.SubElement(entry, "filter", id=f"crop_{item['producer']}_{item['in']}")
        ET.SubElement(crop_filt, "property", name="mlt_service").text = "crop"
        ET.SubElement(crop_filt, "property", name="center").text = "1"
        ET.SubElement(crop_filt, "property", name="center_bias").text = "0"

    # Add Text Overlays on Video Track V1
    # 1. Title Overlay (First 3 seconds)
    title_duration = min(int(round(3.0 * fps)), total_frames)
    title_filt = ET.SubElement(playlist_video, "filter", id="filter_title_overlay", attrib={"in": "0", "out": str(title_duration - 1)})
    ET.SubElement(title_filt, "property", name="mlt_service").text = "dynamictext"
    ET.SubElement(title_filt, "property", name="shotcut:filter").text = "simpleText"
    ET.SubElement(title_filt, "property", name="argument").text = args.title
    ET.SubElement(title_filt, "property", name="geometry").text = f"0 0 {w} {h} 1"
    ET.SubElement(title_filt, "property", name="font").text = "Segoe UI Semibold"
    ET.SubElement(title_filt, "property", name="size").text = "64"
    ET.SubElement(title_filt, "property", name="fgcolour").text = "0xffffffff"
    ET.SubElement(title_filt, "property", name="bgcolour").text = "0x00000000"
    ET.SubElement(title_filt, "property", name="olcolour").text = "0x000000ff"
    ET.SubElement(title_filt, "property", name="outline").text = "3"
    ET.SubElement(title_filt, "property", name="halign").text = "center"
    ET.SubElement(title_filt, "property", name="valign").text = "middle"

    # 2. End Credits Overlay (Last 3 seconds)
    end_duration = min(int(round(3.0 * fps)), total_frames)
    end_start_frame = max(0, total_frames - end_duration)
    end_filt = ET.SubElement(playlist_video, "filter", id="filter_end_overlay", attrib={"in": str(end_start_frame), "out": str(total_frames - 1)})
    ET.SubElement(end_filt, "property", name="mlt_service").text = "dynamictext"
    ET.SubElement(end_filt, "property", name="shotcut:filter").text = "simpleText"
    ET.SubElement(end_filt, "property", name="argument").text = args.end
    ET.SubElement(end_filt, "property", name="geometry").text = f"0 0 {w} {h} 1"
    ET.SubElement(end_filt, "property", name="font").text = "Segoe UI Semibold"
    ET.SubElement(end_filt, "property", name="size").text = "56"
    ET.SubElement(end_filt, "property", name="fgcolour").text = "0xffffffff"
    ET.SubElement(end_filt, "property", name="bgcolour").text = "0x00000000"
    ET.SubElement(end_filt, "property", name="olcolour").text = "0x000000ff"
    ET.SubElement(end_filt, "property", name="outline").text = "3"
    ET.SubElement(end_filt, "property", name="halign").text = "center"
    ET.SubElement(end_filt, "property", name="valign").text = "middle"

    # Track A1: Audio Playlist (looped Вечер for Jan 25th cuts, then blank)
    playlist_audio_jan25 = ET.SubElement(mlt, "playlist", id="playlist_audio_jan25")
    ET.SubElement(playlist_audio_jan25, "property", name="shotcut:audio").text = "1"
    ET.SubElement(playlist_audio_jan25, "property", name="shotcut:name").text = "A1"
    
    rem = frames_jan25
    while rem > 0:
        if rem >= frames_music_jan25:
            ET.SubElement(playlist_audio_jan25, "entry", producer="producer_music_jan25", attrib={"in": "0", "out": str(frames_music_jan25 - 1)})
            rem -= frames_music_jan25
        else:
            ET.SubElement(playlist_audio_jan25, "entry", producer="producer_music_jan25", attrib={"in": "0", "out": str(rem - 1)})
            rem = 0
            
    if frames_today > 0:
        ET.SubElement(playlist_audio_jan25, "blank", length=str(frames_today))

    # Track A2: Audio Playlist (blank first, then looped Аморе for today's cuts)
    playlist_audio_today = ET.SubElement(mlt, "playlist", id="playlist_audio_today")
    ET.SubElement(playlist_audio_today, "property", name="shotcut:audio").text = "1"
    ET.SubElement(playlist_audio_today, "property", name="shotcut:name").text = "A2"
    
    if frames_jan25 > 0:
        ET.SubElement(playlist_audio_today, "blank", length=str(frames_jan25))
        
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

    # Pretty print XML and write to file
    ET.indent(mlt, space="  ")
    final_mlt_path = os.path.join(gopro_dir, "final.mlt").replace("\\", "/")
    tree_final = ET.ElementTree(mlt)
    tree_final.write(final_mlt_path, encoding="utf-8", xml_declaration=True)
    print(f"\n[Pipeline] Polished Shotcut project saved to: {final_mlt_path}")

    # 4. Render Video via melt.exe
    output_video_path = os.path.join(gopro_dir, "final_post.mp4").replace("\\", "/")
    if args.render:
        print("\n[Pipeline] Starting 4K render in background...")
        # Melt command to export
        # We specify the profile and output settings
        vcodec = "h264_nvenc" if args.gpu else "libx264"
        render_cmd = [
            "C:/Program Files/Shotcut/melt.exe",
            final_mlt_path,
            "-consumer", f"avformat:{output_video_path}",
            f"vcodec={vcodec}", "acodec=aac", "g=30", "real_time=-1",
            "threads=0" # uses all CPU cores for fast rendering
        ]
        if args.gpu:
            render_cmd.extend([
                "rc=vbr",
                "cq=21",
                "b=0"
            ])
        else:
            render_cmd.extend([
                "crf=21"
            ])
        
        try:
            run_cmd(render_cmd)
            print(f"[Pipeline] Rendering finished! Video saved to: {output_video_path}")
        except Exception as e:
            print(f"[Pipeline] Rendering failed: {e}")
            sys.exit(1)

    # 5. Boot QR Code Transfer Server
    if os.path.exists(output_video_path):
        ip = get_local_ip()
        port = 8080
        download_url = f"http://{ip}:{port}/video.mp4"
        
        # Start server in background thread
        server = start_server(output_video_path, port)
        
        # Generate QR code in terminal
        print("\n" + "="*50)
        print("          INSTANT MOBILE DOWNLOAD SERVER          ")
        print("="*50)
        print(f"Scan this QR code with your phone camera to download:")
        print(f"Download link: {download_url}\n")
        
        qr = qrcode.QRCode()
        qr.add_data(download_url)
        qr.make(fit=True)
        # Windows console needs invert=True to print black pixels as blocks and white space as white
        qr.print_ascii(invert=True)
        
        print("\nPress Ctrl+C to close the download server when finished.")
        try:
            # Keep main thread alive
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            server.shutdown()
            print("Server closed.")

if __name__ == "__main__":
    main()
