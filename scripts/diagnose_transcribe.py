import argparse
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from echoframe.transcriber import transcribe_audio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", help="Path to audio file to transcribe.")
    parser.add_argument("--model", default="small", help="Whisper model name.")
    parser.add_argument("--language", help="Language code (e.g., en).")
    parser.add_argument("--device", help="Device preference (cpu/cuda).")
    parser.add_argument("--compute-type", help="Compute type (int8/float16).")
    args = parser.parse_args()

    progress_state = {"last": -1}

    def _progress_cb(ratio: float) -> None:
        percent = int(ratio * 100)
        if percent >= progress_state["last"] + 5:
            progress_state["last"] = percent
            print(f"Progress {percent}%")

    started = time.time()
    segments = transcribe_audio(
        args.audio_path,
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        progress_cb=_progress_cb,
    )
    elapsed = time.time() - started
    print(f"Segments: {len(segments)}")
    print(f"Elapsed: {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
