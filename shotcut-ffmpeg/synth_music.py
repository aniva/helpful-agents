import os
import sys
import wave
import struct
import subprocess
import numpy as np

# Reconfigure stdout for UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    return res.stdout

# Note frequencies in Hz (Equal temperament, A4 = 440Hz)
# Octave 3 (Bass)
C3, D3, E3, F3, G3, A3, B3 = 130.81, 146.83, 164.81, 174.61, 196.00, 220.00, 246.94
# Octave 4 (Melody / Chord)
C4, D4, E4, F4, G4, A4, B4 = 261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88
# Octave 5 (High Chimes)
C5, D5, E5, F5, G5, A5, B5 = 523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77
C6, D6, E6, E6_flat = 1046.50, 1174.66, 1318.51, 1244.51

SAMPLE_RATE = 44100

def get_chime_wave(frequency, duration, sample_rate=SAMPLE_RATE):
    """Generates a music-box/chime sound with exponential decay and subtle harmonics."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Fundamental frequency
    wave_data = np.sin(2 * np.pi * frequency * t)
    
    # 2nd harmonic (octave above) - gives it a bell-like chime quality
    wave_data += 0.35 * np.sin(2 * np.pi * (frequency * 2) * t)
    
    # 3rd harmonic
    wave_data += 0.15 * np.sin(2 * np.pi * (frequency * 3) * t)
    
    # Exponential decay envelope (quick strike, gradual release)
    decay = np.exp(-t / 0.45)  # 0.45s decay constant for a richer, spacious ring
    wave_data = wave_data * decay
    
    # Normalize to -1.0 to 1.0 range
    max_val = np.max(np.abs(wave_data))
    if max_val > 0:
        wave_data = wave_data / max_val
        
    return wave_data
 
def mix_audio(tracks, length):
    """Mixes multiple audio tracks together."""
    mixed = np.zeros(length)
    for track in tracks:
        # truncate or pad track to match length
        track_len = len(track)
        if track_len > length:
            mixed += track[:length]
        else:
            mixed[:track_len] += track
    return mixed
 
def generate_lullaby_waltz(duration_sec):
    print("Synthesizing copyright-free nostalgic lullaby in 3/4 waltz time...")
    bpm = 70  # Slightly slower tempo (70 BPM) for a more peaceful, cozy lullaby
    beat_duration = 60.0 / bpm  # 0.857 seconds per beat
    bar_duration = beat_duration * 3  # 2.57 seconds per bar (3 beats per bar)
    
    total_samples = int(SAMPLE_RATE * duration_sec)
    
    # We will build three layers: Bass, Arpeggio Chords, and a Melody.
    bass_track = np.zeros(total_samples)
    chord_track = np.zeros(total_samples)
    melody_track = np.zeros(total_samples)
    
    # 8-bar emotional chord progression (C -> G -> Am -> Em -> F -> C -> Dm -> G)
    chords = [
        {"bass": C3, "chord": [E4, G4, C5]}, # Bar 1: C maj
        {"bass": G3, "chord": [D4, G4, B4]}, # Bar 2: G maj
        {"bass": A3, "chord": [E4, A4, C5]}, # Bar 3: A min
        {"bass": E3, "chord": [G4, B4, E5]}, # Bar 4: E min
        {"bass": F3, "chord": [F4, A4, C5]}, # Bar 5: F maj
        {"bass": C3, "chord": [E4, G4, C5]}, # Bar 6: C maj
        {"bass": D3, "chord": [F4, A4, D5]}, # Bar 7: D min
        {"bass": G3, "chord": [D4, G4, B4]}  # Bar 8: G maj
    ]
    
    # Sweet, classic music box melody waltz loop (8 bars)
    melody_notes = [
        # Bar 1: G5 -> E5
        [(0, G5), (2, E5)],
        # Bar 2: G5 -> D5
        [(0, G5), (2, D5)],
        # Bar 3: C5 -> E5 -> A5
        [(0, C5), (1, E5), (2, A5)],
        # Bar 4: G5 (hold)
        [(0, G5)],
        # Bar 5: A5 -> C6
        [(0, A5), (2, C6)],
        # Bar 6: G5 -> E5
        [(0, G5), (2, E5)],
        # Bar 7: F5 -> D5
        [(0, F5), (2, D5)],
        # Bar 8: C5 (hold)
        [(0, C5)]
    ]
    
    num_bars = int(np.ceil(duration_sec / bar_duration))
    
    for bar_idx in range(num_bars):
        bar_start_sample = int(bar_idx * bar_duration * SAMPLE_RATE)
        if bar_start_sample >= total_samples:
            break
            
        chord_info = chords[bar_idx % len(chords)]
        
        # 1. Bass: Play root note on beat 1
        bass_note = get_chime_wave(chord_info["bass"], beat_duration * 1.5)
        bass_len = len(bass_note)
        if bar_start_sample + bass_len < total_samples:
            bass_track[bar_start_sample : bar_start_sample + bass_len] += bass_note * 0.5
            
        # 2. Chord Arpeggio: Play notes on beat 2 and 3
        # Beat 2
        b2_start = bar_start_sample + int(beat_duration * SAMPLE_RATE)
        # Mix the first two notes of the chord on beat 2
        for note in chord_info["chord"][:2]:
            note_wave = get_chime_wave(note, beat_duration * 1.2)
            n_len = len(note_wave)
            if b2_start + n_len < total_samples:
                chord_track[b2_start : b2_start + n_len] += note_wave * 0.25
                
        # Beat 3
        b3_start = bar_start_sample + int(beat_duration * 2 * SAMPLE_RATE)
        # Mix the last two notes of the chord on beat 3
        for note in chord_info["chord"][1:]:
            note_wave = get_chime_wave(note, beat_duration * 1.2)
            n_len = len(note_wave)
            if b3_start + n_len < total_samples:
                chord_track[b3_start : b3_start + n_len] += note_wave * 0.25

        # 3. Melody: Play melody notes
        melody_bar = melody_notes[bar_idx % len(melody_notes)]
        for beat_offset, note in melody_bar:
            m_start = bar_start_sample + int(beat_offset * beat_duration * SAMPLE_RATE)
            m_wave = get_chime_wave(note, beat_duration * 2.0)
            m_len = len(m_wave)
            if m_start + m_len < total_samples:
                melody_track[m_start : m_start + m_len] += m_wave * 0.4

    # Mix layers together and master the volume
    mixed = mix_audio([bass_track, chord_track, melody_track], total_samples)
    
    # Normalize final audio to avoid clipping
    max_val = np.max(np.abs(mixed))
    if max_val > 0:
        mixed = (mixed / max_val) * 0.8
        
    return mixed

def save_wav(filename, data):
    print(f"Saving WAV file to: {filename}")
    with wave.open(filename, 'wb') as wav_file:
        # Mono, 16-bit PCM, 44100Hz
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        
        # Convert float data (-1.0 to 1.0) to 16-bit signed integer (-32768 to 32767)
        int_data = (data * 32767).astype(np.int16)
        
        # Write all frames instantly from numpy buffer
        wav_file.writeframes(int_data.tobytes())
    print("WAV file saved!")

def main():
    gopro_dir = "E:/20260627_GoPro"
    wav_path = os.path.join(gopro_dir, "synth_lullaby.wav").replace("\\", "/")
    mp3_path = os.path.join(gopro_dir, "synth_lullaby.mp3").replace("\\", "/")
    
    # Generate 125 seconds of music (slightly longer than the 117s video segment)
    music_data = generate_lullaby_waltz(125.0)
    save_wav(wav_path, music_data)
    
    # Convert WAV to MP3 using ffmpeg
    print("Converting WAV to MP3 using ffmpeg...")
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path]
    run_cmd(cmd)
    
    # Clean up temporary WAV
    if os.path.exists(wav_path):
        os.remove(wav_path)
    print(f"Generated soundtrack saved successfully to: {mp3_path}")

if __name__ == "__main__":
    main()
