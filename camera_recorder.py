#!/usr/bin/env python3
"""
Camera Recording Script with 30-Second Buffer

Continuously captures frames from USB camera, maintains a rolling 30-second buffer,
and saves buffered frames to MP4 when button is pressed.
"""

import cv2
import tkinter as tk
from tkinter import ttk
import threading
from collections import deque
from datetime import datetime
import os
from PIL import Image, ImageTk
import argparse
import time


class CameraRecorder:
    def __init__(self, buffer_duration=15, output_dir="."):
        """
        Initialize the camera recorder.
        
        Args:
            buffer_duration: Duration in seconds to keep in buffer (default: 15)
            output_dir: Directory to save video files (default: current directory)
        """
        self.buffer_duration = buffer_duration
        self.output_dir = os.path.abspath(output_dir)
        self.cap = None
        self.frame_buffer = deque(maxlen=1)  # Will be set based on FPS
        self.fps = 30  # Default FPS, will be updated from camera
        self.is_recording = False
        self.is_saving = False
        self.lock = threading.Lock()
        self.preview_width = 1280
        self.preview_height = 720
        self.video_width = 1920
        self.video_height = 1080
        self.last_preview_update = 0
        self.last_status_update = 0
        self.preview_update_interval = 1.0 / 30.0  # Update preview at 30 FPS max
        self.status_update_interval = 0.1  # Update status every 100ms
        self.frame_count = 0
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"Output directory: {self.output_dir}")
        
        # Initialize camera
        self.init_camera()
        
        # Setup GUI
        self.setup_gui()
        
    def init_camera(self):
        """Initialize the camera and determine FPS."""
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise Exception("Could not open camera")
            
            # Set camera resolution to Full HD
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.video_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.video_height)
            
            # Allow OpenCV to buffer frames internally so we can capture ALL frames
            # Setting a reasonable buffer size (e.g., 3-5 frames) allows OpenCV to queue
            # frames while we process them, preventing frame drops
            # Using default buffer (not setting it) or a small buffer works best
            
            # Verify the resolution was set (camera may not support exact resolution)
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"Camera resolution: {actual_width}x{actual_height} (requested: {self.video_width}x{self.video_height})")
            
            # Get camera FPS
            self.fps = int(self.cap.get(cv2.CAP_PROP_FPS))
            if self.fps <= 0:
                self.fps = 30  # Default if FPS not available
            
            # Calculate buffer size
            buffer_size = self.fps * self.buffer_duration
            self.frame_buffer = deque(maxlen=buffer_size)
            
            print(f"Camera initialized: FPS={self.fps}, Buffer size={buffer_size} frames")
            
        except Exception as e:
            print(f"Error initializing camera: {e}")
            self.cap = None
    
    def setup_gui(self):
        """Setup the tkinter GUI."""
        self.root = tk.Tk()
        self.root.title("Camera Recorder")
        # Window size: preview width + padding, preview height + space for controls
        window_width = self.preview_width + 40
        window_height = self.preview_height + 250
        self.root.geometry(f"{window_width}x{window_height}")
        
        # Preview label for camera feed
        self.preview_label = tk.Label(
            self.root,
            text="Initializing camera...",
            bg="black",
            width=self.preview_width,
            height=self.preview_height
        )
        self.preview_label.pack(pady=10)
        
        # Status label - make it more prominent
        self.status_label = tk.Label(
            self.root,
            text="Camera ready. Buffer: 0 seconds",
            font=("Arial", 14, "bold"),
            pady=10,
            bg="lightgray",
            relief=tk.RAISED,
            borderwidth=2
        )
        self.status_label.pack()
        
        # Buffer size slider frame
        slider_frame = tk.Frame(self.root)
        slider_frame.pack(pady=5)
        
        # Buffer size label
        self.buffer_label = tk.Label(
            slider_frame,
            text=f"Buffer Duration: {self.buffer_duration} seconds",
            font=("Arial", 10)
        )
        self.buffer_label.pack(side=tk.LEFT, padx=5)
        
        # Buffer size slider
        self.buffer_slider = tk.Scale(
            slider_frame,
            from_=5,
            to=30,
            orient=tk.HORIZONTAL,
            length=200,
            command=self.on_buffer_slider_changed
        )
        self.buffer_slider.set(self.buffer_duration)
        self.buffer_slider.pack(side=tk.LEFT, padx=5)
        
        # Save button
        self.save_button = ttk.Button(
            self.root,
            text="Save Video",
            command=self.on_save_button_clicked,
            state="normal" if self.cap else "disabled"
        )
        self.save_button.pack(pady=10)
        
        # Info label
        self.info_label = tk.Label(
            self.root,
            text="Click 'Save Video' or press Spacebar to save the buffered video",
            font=("Arial", 10),
            fg="gray"
        )
        self.info_label.pack()
        
        # Bind spacebar key to save function
        self.root.bind('<space>', lambda event: self.on_save_button_clicked())
        self.root.focus_set()  # Allow window to receive keyboard events
    
    def on_buffer_slider_changed(self, value):
        """Handle buffer size slider change."""
        new_duration = int(float(value))
        if new_duration != self.buffer_duration:
            self.update_buffer_size(new_duration)
    
    def update_buffer_size(self, new_duration):
        """Update the buffer size to a new duration."""
        with self.lock:
            # Calculate new buffer size
            new_buffer_size = self.fps * new_duration
            
            # Get current frames
            current_frames = list(self.frame_buffer)
            
            # Create new buffer with new maxlen
            new_buffer = deque(maxlen=new_buffer_size)
            
            # Copy frames from old buffer to new buffer
            # If new buffer is smaller, only keep the most recent frames
            frames_to_keep = min(len(current_frames), new_buffer_size)
            for frame in current_frames[-frames_to_keep:]:
                new_buffer.append(frame)
            
            # Replace old buffer with new buffer
            self.frame_buffer = new_buffer
            self.buffer_duration = new_duration
            
            # Update label
            self.buffer_label.config(text=f"Buffer Duration: {self.buffer_duration} seconds")
            
            print(f"Buffer size updated to {new_duration} seconds ({new_buffer_size} frames)")
        
    def capture_loop(self):
        """Main loop to capture frames and update buffer.
        This loop runs as fast as possible to capture ALL frames from the camera."""
        if not self.cap or not self.cap.isOpened():
            return
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("Failed to read frame from camera")
                break
            
            self.frame_count += 1
            current_time = time.time()
            
            # Resize frame to Full HD if needed (do this before adding to buffer)
            frame_height, frame_width = frame.shape[:2]
            if frame_width != self.video_width or frame_height != self.video_height:
                frame = cv2.resize(frame, (self.video_width, self.video_height))
            
            # Add frame to buffer immediately (minimize lock time - only hold for append)
            # This ensures we capture every frame the camera provides
            with self.lock:
                self.frame_buffer.append(frame.copy())
                buffer_seconds = len(self.frame_buffer) / self.fps
            
            # Throttle preview updates to avoid queueing too many GUI updates
            # This doesn't affect frame capture - we still capture all frames
            if current_time - self.last_preview_update >= self.preview_update_interval:
                preview_frame = cv2.resize(frame, (self.preview_width, self.preview_height))
                self.root.after(0, self.update_preview, preview_frame)
                self.last_preview_update = current_time
            
            # Throttle status updates (doesn't affect frame capture)
            if current_time - self.last_status_update >= self.status_update_interval:
                self.root.after(0, self.update_status, buffer_seconds)
                self.last_status_update = current_time
    
    def update_preview(self, frame):
        """Update the preview display with a new frame."""
        try:
            # Frame is already resized to preview size in capture_loop
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            img = Image.fromarray(frame_rgb)
            
            # Convert to ImageTk
            imgtk = ImageTk.PhotoImage(image=img)
            
            # Update label
            self.preview_label.config(image=imgtk)
            self.preview_label.image = imgtk  # Keep a reference
        except Exception as e:
            print(f"Error updating preview: {e}")
    
    def update_status(self, buffer_seconds):
        """Update the status label in the GUI."""
        if self.is_saving:
            self.status_label.config(
                text=f"⏳ SAVING VIDEO... Buffer: {buffer_seconds:.1f} seconds",
                bg="orange",
                fg="white"
            )
        else:
            self.status_label.config(
                text=f"Camera ready. Buffer: {buffer_seconds:.1f} seconds",
                bg="lightgray",
                fg="black"
            )
    
    def on_save_button_clicked(self):
        """Handle save button click - start saving video in background thread."""
        if self.is_saving:
            return  # Already saving
        
        with self.lock:
            if len(self.frame_buffer) == 0:
                self.status_label.config(
                    text="⚠️ No frames in buffer to save",
                    bg="yellow",
                    fg="black"
                )
                # Reset after 3 seconds
                self.root.after(3000, lambda: self.status_label.config(
                    text=f"Camera ready. Buffer: 0.0 seconds",
                    bg="lightgray",
                    fg="black"
                ))
                return
            
            # Get current buffer (copy to avoid modification during save)
            frames_to_save = list(self.frame_buffer)
            buffer_seconds = len(frames_to_save) / self.fps
        
        # Update button and status to show saving state
        self.save_button.config(state="disabled", text="Saving...")
        self.is_saving = True
        self.status_label.config(
            text=f"⏳ SAVING VIDEO... ({len(frames_to_save)} frames)",
            bg="orange",
            fg="white"
        )
        
        # Start save thread
        save_thread = threading.Thread(
            target=self.save_video,
            args=(frames_to_save,),
            daemon=True
        )
        save_thread.start()
    
    def save_video(self, frames):
        """Save frames to MP4 file in a separate thread."""
        try:
            # Calculate video start time: current time minus buffer duration
            # This represents when the first frame in the buffer was captured
            video_duration = len(frames) / self.fps
            video_start_time = datetime.now().timestamp() - video_duration
            timestamp = datetime.fromtimestamp(video_start_time).strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(self.output_dir, f"{timestamp}.mp4")
            
            if len(frames) == 0:
                print("No frames to save")
                return
            
            # Ensure all frames are Full HD
            processed_frames = []
            for frame in frames:
                frame_height, frame_width = frame.shape[:2]
                if frame_width != self.video_width or frame_height != self.video_height:
                    frame = cv2.resize(frame, (self.video_width, self.video_height))
                processed_frames.append(frame)
            
            # Setup video writer with Full HD resolution
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(filename, fourcc, self.fps, (self.video_width, self.video_height))
            
            # Write frames
            for frame in processed_frames:
                out.write(frame)
            
            out.release()
            
            print(f"Video saved: {filename} ({len(frames)} frames, {len(frames)/self.fps:.1f} seconds, {self.video_width}x{self.video_height})")
            
            # Update GUI (show just the filename, not full path)
            filename_display = os.path.basename(filename)
            self.root.after(0, self.on_save_complete, filename_display)
            
        except Exception as e:
            print(f"Error saving video: {e}")
            self.root.after(0, self.on_save_error, str(e))
    
    def on_save_complete(self, filename):
        """Called when video save is complete."""
        self.is_saving = False
        self.save_button.config(state="normal", text="Save Video")
        
        # Show success message prominently
        with self.lock:
            buffer_seconds = len(self.frame_buffer) / self.fps
        
        self.status_label.config(
            text=f"✅ VIDEO SAVED: {filename}",
            bg="green",
            fg="white"
        )
        
        # Reset status after 5 seconds (longer to see the success message)
        self.root.after(5000, lambda: self.status_label.config(
            text=f"Camera ready. Buffer: {buffer_seconds:.1f} seconds",
            bg="lightgray",
            fg="black"
        ))
    
    def on_save_error(self, error_msg):
        """Called when video save encounters an error."""
        self.is_saving = False
        self.save_button.config(state="normal", text="Save Video")
        self.status_label.config(
            text=f"❌ ERROR: {error_msg}",
            bg="red",
            fg="white"
        )
        
        # Reset status after 5 seconds
        self.root.after(5000, lambda: self.status_label.config(
            text=f"Camera ready. Buffer: {len(self.frame_buffer) / self.fps:.1f} seconds",
            bg="lightgray",
            fg="black"
        ))
    
    def run(self):
        """Start the application."""
        if not self.cap:
            self.status_label.config(text="Error: Camera not available")
            return
        
        # Start capture thread
        capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        capture_thread.start()
        
        # Start GUI main loop
        self.root.mainloop()
    
    def cleanup(self):
        """Cleanup resources."""
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()


def main():
    """Main entry point."""
    # Default output directory: script location + "clips"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output_dir = os.path.join(script_dir, "clips")
    
    parser = argparse.ArgumentParser(
        description="Camera recorder with 30-second buffer",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=default_output_dir,
        help=f"Directory to save video files (default: {default_output_dir})"
    )
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=15,
        help="Buffer duration in seconds (default: 15, range: 5-30)"
    )
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    recorder = CameraRecorder(buffer_duration=args.duration, output_dir=args.output_dir)
    try:
        recorder.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        recorder.cleanup()


if __name__ == "__main__":
    main()

