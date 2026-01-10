

import sounddevice as sd
import numpy as np
import sys

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def list_all_devices():
    print_header("ALL AUDIO DEVICES")
    
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        print(f"\n[{idx}] {device['name']}")
        print(f"    Input Channels:  {device['max_input_channels']}")
        print(f"    Output Channels: {device['max_output_channels']}")
        print(f"    Default Rate:    {device['default_samplerate']} Hz")
        print(f"    Host API:        {sd.query_hostapis(device['hostapi'])['name']}")

def get_default_input():
    print_header("DEFAULT INPUT DEVICE")
    
    try:
        default_idx = sd.default.device[0]
        if default_idx is None:
            print("ERROR: No default input device found!")
            return None
        
        device = sd.query_devices(default_idx, kind='input')
        print(f"Device Index: {default_idx}")
        print(f"Name:         {device['name']}")
        print(f"Channels:     {device['max_input_channels']}")
        print(f"Default Rate: {device['default_samplerate']} Hz")
        print(f"Host API:     {sd.query_hostapis(device['hostapi'])['name']}")
        
        return default_idx
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def test_sample_rates(device_idx=None):
    print_header("SAMPLE RATE TESTING")
    
    test_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000]
    working_rates = []
    
    print("\nTesting sample rates (this may take a moment)...\n")
    print(f"{'Sample Rate':<15} {'Status':<20} {'Details'}")
    print("-" * 70)
    
    for rate in test_rates:
        try:
            # Try to open and read from the stream
            with sd.InputStream(
                samplerate=rate, 
                channels=1, 
                dtype='int16',
                device=device_idx,
                blocksize=4096
            ) as stream:
                # Try to actually read some data
                data, overflowed = stream.read(1024)
                status = "✓ WORKS"
                details = f"Read {len(data)} samples"
                working_rates.append(rate)
                print(f"{rate:<15} {status:<20} {details}")
        except Exception as e:
            status = "✗ FAILED"
            error_msg = str(e).split('\n')[0][:40]  # First line, truncated
            print(f"{rate:<15} {status:<20} {error_msg}")
    
    return working_rates

def test_recording(rate, duration=2):
    print(f"\nTesting {duration}-second recording at {rate} Hz...")
    try:
        print("Recording... ", end='', flush=True)
        recording = sd.rec(
            int(duration * rate),
            samplerate=rate,
            channels=1,
            dtype='float32'
        )
        sd.wait()
        
        # Calculate some stats
        max_amplitude = np.max(np.abs(recording))
        rms = np.sqrt(np.mean(recording**2))
        
        print("✓ SUCCESS")
        print(f"  Max amplitude: {max_amplitude:.4f}")
        print(f"  RMS level:     {rms:.4f}")
        
        if max_amplitude < 0.001:
            print("  ⚠ WARNING: Very low audio level - check microphone!")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def main():
    """Main testing function"""
    print("\n" + "=" * 70)
    print("  COMPREHENSIVE AUDIO DEVICE TESTING")
    print("=" * 70)
    
    # List all devices
    list_all_devices()
    
    # Get default input
    default_idx = get_default_input()
    
    if default_idx is None:
        print("\n No input device available!")
        return
    
    # Test sample rates
    working_rates = test_sample_rates(default_idx)
    
    # Summary
    print_header("SUMMARY")
    print(f"\nTotal working sample rates: {len(working_rates)}")
    if working_rates:
        print(f"Supported rates: {', '.join(map(str, working_rates))} Hz")
        
        # Recommend best rate
        print("\nRECOMMENDATIONS:")
        if 16000 in working_rates:
            print("  16000 Hz - PERFECT for speech recognition (recommended)")
        elif 48000 in working_rates:
            print("  48000 Hz - Standard rate, will need resampling for STT")
        elif 44100 in working_rates:
            print("  44100 Hz - CD quality, will need resampling for STT")
        
        # Test actual recording with the best available rate
        if 16000 in working_rates:
            best_rate = 16000
        elif working_rates:
            best_rate = working_rates[0]
        else:
            best_rate = None
        
        if best_rate:
            print(f"\n📝 Testing actual recording at {best_rate} Hz...")
            test_recording(best_rate, duration=2)
    else:
        print("\n No working sample rates found!")
        print("\nTroubleshooting steps:")
        print("1. Check if microphone is connected")
        print("2. Run: arecord -l")
        print("3. Check ALSA configuration")

    
    print("\n" + "=" * 70)
    print("Testing complete!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTesting interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n ERROR: {e}")
        sys.exit(1)