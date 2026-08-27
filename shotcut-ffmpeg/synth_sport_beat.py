import os
import sys
import wave
import struct
import subprocess
import numpy as np

# Reconfigure stdout for UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SAMPLE_RATE = 44100

def get_kick(duration=0.18, sample_rate=SAMPLE_RATE):
    """Generates a deep 808-style kick sweep (heartbeat thump)."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Pitch sweep from 140Hz down to 35Hz
    freq = 140 - (140 - 35) * (t / duration)
    wave_data = np.sin(2 * np.pi * freq * t)
    # Fast decay envelope
    env = np.exp(-t / 0.05)
    return wave_data * env

def get_hihat(duration=0.06, sample_rate=SAMPLE_RATE):
    """Generates a crisp white-noise hi-hat click."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    noise = np.random.uniform(-1.0, 1.0, len(t))
    # Quick decay envelope
    env = np.exp(-t / 0.015)
    return noise * env * 0.25

def get_snare(duration=0.22, sample_rate=SAMPLE_RATE):
    """Generates a sporty electronic snare."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # White noise snap
    noise = np.random.uniform(-1.0, 1.0, len(t)) * np.exp(-t / 0.07)
    # 170Hz punch body
    body = np.sin(2 * np.pi * 170 * t) * np.exp(-t / 0.04)
    return (noise + body * 0.5) * 0.4

def get_bass(freq, duration, sample_rate=SAMPLE_RATE):
    """Generates a warm triangle-wave synth bass note."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Triangle wave
    wave_data = np.arcsin(np.sin(2 * np.pi * freq * t)) * (2.0 / np.pi)
    # Apply low-pass characteristic using decay
    env = np.exp(-t / (duration * 0.8))
    return wave_data * env * 0.35

def mix_segment(target, source, start_sample):
    """Safely mixes source audio into target audio at a specific sample offset."""
    s_len = len(source)
    t_len = len(target)
    if start_sample >= t_len:
        return
    end_sample = min(start_sample + s_len, t_len)
    target[start_sample:end_sample] += source[:end_sample - start_sample]

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    return res.stdout

def generate_sporty_heartbeat_beat(duration_sec):
    print("Synthesizing copyright-free sporty heartbeat synthwave track...")
    bpm = 120  # 120 BPM matches a running/active heart rate!
    beat_duration = 60.0 / bpm  # 0.5s per beat
    subdivision_duration = beat_duration / 4  # 0.125s per sixteenth note (16 steps per bar)
    bar_duration = beat_duration * 4  # 2.0s per bar
    
    total_samples = int(SAMPLE_RATE * duration_sec)
    output_audio = np.zeros(total_samples)
    
    # Bass Notes frequencies (Octave 2: A2, F2, G2)
    A2, F2, G2 = 110.00, 87.31, 98.00
    
    num_bars = int(np.ceil(duration_sec / bar_duration))
    
    # Sound assets cache
    kick = get_kick()
    snare = get_snare()
    hihat = get_hihat()
    
    for bar_idx in range(num_bars):
        bar_start_sample = int(bar_idx * bar_duration * SAMPLE_RATE)
        
        # Bass note progression
        if bar_idx % 8 in [0, 1, 2, 3]:
            bass_freq = A2
        elif bar_idx % 8 in [4, 5]:
            bass_freq = F2
        else:
            bass_freq = G2
            
        for step in range(16):
            step_start_sample = bar_start_sample + int(step * subdivision_duration * SAMPLE_RATE)
            if step_start_sample >= total_samples:
                break
                
            # 1. Heartbeat Kick (Double thump on Beat 1 and Beat 3)
            # Double thump: step 0 & 1, step 8 & 9
            if step in [0, 1, 8, 9]:
                # Step 1 is slightly quieter to mimic the second thump of a heartbeat
                volume = 0.85 if step in [0, 8] else 0.55
                mix_segment(output_audio, kick * volume, step_start_sample)
                
            # 2. Snare on Beat 2 and 4 (step 4 and step 12)
            if step in [4, 12]:
                mix_segment(output_audio, snare, step_start_sample)
                
            # 3. Offbeat Hi-hats (steps 2, 6, 10, 14)
            if step in [2, 6, 10, 14]:
                mix_segment(output_audio, hihat, step_start_sample)
                
            # 4. Driving Rhythmic Bassline (eighth notes: steps 0, 2, 4, 6, 8, 10, 12, 14)
            if step % 2 == 0:
                bass_note = get_bass(bass_freq, subdivision_duration * 1.5)
                mix_segment(output_audio, bass_note, step_start_sample)
                
    # Normalize
    max_val = np.max(np.abs(output_audio))
    if max_val > 0:
        output_audio = (output_audio / max_val) * 0.85
        
    return output_audio

def save_wav(filename, data):
    print(f"Saving WAV file to: {filename}")
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        int_data = (data * 32767).astype(np.int16)
        wav_file.writeframes(int_data.tobytes())
    print("WAV file saved!")

def main():
    gopro_dir = "E:/20260627_GoPro"
    wav_path = os.path.join(gopro_dir, "synth_sport_beat.wav").replace("\\", "/")
    mp3_path = os.path.join(gopro_dir, "synth_sport_beat.mp3").replace("\\", "/")
    
    # Generate 125 seconds of music
    music_data = generate_sporty_heartbeat_beat(125.0)
    save_wav(wav_path, music_data)
    
    print("Converting WAV to MP3 using ffmpeg...")
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path]
    run_cmd(cmd)
    
    if os.path.exists(wav_path):
        os.remove(wav_path)
    print(f"Generated sporty beat saved to: {mp3_path}")

if __name__ == "__main__":
    main()
