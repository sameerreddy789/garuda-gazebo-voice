#!/usr/bin/env python3
"""
GarudaOne — PicoDet-S Detector Test Script
===========================================
Tests the object detector with real model weights or stub mode.

Usage:
    python scripts/test_detector.py                    # Stub mode
    python scripts/test_detector.py --image photo.jpg  # Test on image
    python scripts/test_detector.py --webcam            # Test on webcam
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from garuda.core.config import Config
from garuda.perception.detector import PicoDetector


def test_stub_mode():
    """Test detector in stub mode (no real model)."""
    print("\n" + "=" * 60)
    print("  Testing PicoDet-S in STUB mode")
    print("=" * 60)

    config = Config()
    detector = PicoDetector(config)
    detector.load_model()

    print(f"\n  Backend: {detector.backend}")
    assert detector.backend == "stub", f"Expected stub, got {detector.backend}"

    # Generate a synthetic test frame
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Run detection
    detections = detector.detect(frame)

    print(f"\n  Detections: {len(detections)}")
    for det in detections:
        print(f"    - bbox=({det.x_center:.2f}, {det.y_center:.2f}) "
              f"size=({det.width:.2f}x{det.height:.2f}) "
              f"conf={det.confidence:.2f}")

    # Benchmark
    n_frames = 1000  # More frames for stable measurement on fast stubs
    print(f"\n  Benchmarking stub detector ({n_frames} frames)...")
    start = time.time()
    for _ in range(n_frames):
        detector.detect(frame)
    elapsed = time.time() - start
    fps = n_frames / elapsed if elapsed > 0 else float("inf")
    print(f"  FPS: {fps:.1f}" + (" (instant)" if fps == float("inf") else ""))

    print("\n  ✓ Stub detector test PASSED")


def test_image(image_path: str):
    """Test detector on a real image (requires real model)."""
    import cv2
    import numpy as np

    print("\n" + "=" * 60)
    print(f"  Testing PicoDet-S on image: {image_path}")
    print("=" * 60)

    config = Config()
    detector = PicoDetector(config)
    detector.load_model()

    if detector.backend == "stub":
        print("\n  ⚠ Running in stub mode — no real model loaded.")
        print("    Download models first: python scripts/download_models.py")

    # Load image
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"  ✗ Could not load image: {image_path}")
        return

    print(f"\n  Image size: {frame.shape[1]}x{frame.shape[0]}")
    print(f"  Backend: {detector.backend}")

    # Run detection
    detections = detector.detect(frame)

    print(f"\n  Detections: {len(detections)}")
    for det in detections:
        print(f"    - bbox=({det.x_center:.2f}, {det.y_center:.2f}) "
              f"size=({det.width:.2f}x{det.height:.2f}) "
              f"conf={det.confidence:.2f}")

        # Draw bounding box on image
        h, w = frame.shape[:2]
        x1 = int((det.x_center - det.width / 2) * w)
        y1 = int((det.y_center - det.height / 2) * h)
        x2 = int((det.x_center + det.width / 2) * w)
        y2 = int((det.y_center + det.height / 2) * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            frame,
            f"person {det.confidence:.2f}",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
        )

    # Save annotated image
    output_path = "detection_result.jpg"
    cv2.imwrite(output_path, frame)
    print(f"\n  Result saved to: {output_path}")
    print("  ✓ Image test complete")


def test_webcam():
    """Test detector on webcam feed in real-time."""
    import cv2

    print("\n" + "=" * 60)
    print("  Testing PicoDet-S on webcam (press 'q' to quit)")
    print("=" * 60)

    config = Config()
    detector = PicoDetector(config)
    detector.load_model()

    print(f"\n  Backend: {detector.backend}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("  ✗ Could not open webcam")
        return

    print("\n  Webcam opened. Press 'q' to quit.")

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        detections = detector.detect(frame)

        # Draw detections
        h, w = frame.shape[:2]
        for det in detections:
            x1 = int((det.x_center - det.width / 2) * w)
            y1 = int((det.y_center - det.height / 2) * h)
            x2 = int((det.x_center + det.width / 2) * w)
            y2 = int((det.y_center + det.height / 2) * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # FPS counter
        frame_count += 1
        fps = frame_count / (time.time() - start_time)
        cv2.putText(
            frame,
            f"FPS: {fps:.1f} [{detector.backend}] Detections: {len(detections)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
        )

        cv2.imshow("PicoDet-S Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n  Average FPS: {fps:.1f}")
    print("  ✓ Webcam test complete")


def main():
    parser = argparse.ArgumentParser(description="Test PicoDet-S detector")
    parser.add_argument("--image", type=str, help="Test on an image file")
    parser.add_argument("--webcam", action="store_true", help="Test on webcam")
    args = parser.parse_args()

    if args.image:
        test_image(args.image)
    elif args.webcam:
        test_webcam()
    else:
        test_stub_mode()


if __name__ == "__main__":
    main()
