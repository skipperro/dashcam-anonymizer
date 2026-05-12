"""
Encoder thread module.

Contains the encoder thread implementation for video processing pipeline.
Handles frame encoding with audio preservation and source-preserving encoding parameters.
"""

import threading
import time
import os
import subprocess
from typing import Dict, Any, Optional
from queue import Queue, Empty
import structlog
import ffmpeg

from .models import ProcessingSettings


class EncoderThread:
    """
    Encoder thread implementation for video processing pipeline.
    
    Handles frame encoding with audio preservation and flow control.
    """
    
    def __init__(self, config, queue_timeout: float = 0.1):
        """
        Initialize encoder thread.
        
        Args:
            config: Configuration object
            queue_timeout: Timeout for queue operations in seconds
        """
        self.config = config
        self.queue_timeout = queue_timeout
        self.logger = structlog.get_logger("encoder_thread")
        
        # Timing stats
        self.thread_timings = {
            'encoder_time': 0.0,
            'total_frame_encode_time': 0.0
        }
        
        # Processing stats
        self.processing_stats = {}
    
    def run(self, input_queue: Queue, input_path: str, output_path: str,
            video_info: Dict[str, Any], processing_settings: ProcessingSettings, 
            task_id: str, stop_event: threading.Event,
            progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Run the encoder thread using direct FFmpeg streaming for video-only encoding,
        then combine with original audio.
        
        Args:
            input_queue: Queue containing (frame_number, frame) tuples
            input_path: Path to original input video
            output_path: Path for final output video
            video_info: Video information dictionary
            processing_settings: Processing configuration
            task_id: Unique task identifier
            stop_event: Threading event to signal stop
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary containing processing statistics
        """
        start_time = time.time()
        total_frame_encode_time = 0.0
        
        try:
            # Get encoding parameters that preserve source characteristics
            encoding_params = self._get_source_preserving_encoding_params(video_info)
            
            # Check if input video has audio stream
            probe = ffmpeg.probe(input_path)
            has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
            
            # Create temporary video file (video-only)
            temp_video_path = f"/tmp/{task_id}_temp_video.mp4"
            
            # Build FFmpeg command for video-only streaming
            input_video = ffmpeg.input('pipe:', format='rawvideo', pix_fmt='bgr24', 
                                     s=f"{video_info['width']}x{video_info['height']}", 
                                     r=video_info['fps'])
            
            stream = ffmpeg.output(
                input_video,
                temp_video_path,
                **encoding_params
            )
            
            # Start FFmpeg process.
            # IMPORTANT: Do NOT use quiet=True with run_async — it pipes stdout+stderr
            # but nobody reads them, causing FFmpeg to deadlock when pipe buffers fill.
            # Instead use subprocess.DEVNULL to silence FFmpeg output safely.
            ffmpeg_args = stream.overwrite_output().compile()
            process = subprocess.Popen(
                ffmpeg_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            frame_count = 0
            last_checkpoint = time.time()
            self.logger.info("Encoder thread started with direct FFmpeg streaming (video-only)", 
                           temp_video_path=temp_video_path, has_audio=has_audio)
            
            while not stop_event.is_set():
                try:
                    # Non-blocking get to start processing frames immediately as they arrive
                    frame_number, frame = input_queue.get(timeout=self.queue_timeout)
                    
                    if frame_number is None:  # End signal
                        self.logger.info("Encoder thread received end signal", frames_written=frame_count)
                        break
                    
                    # Time the frame encoding
                    encode_start = time.time()
                    
                    # Write frame to FFmpeg stdin
                    try:
                        process.stdin.write(frame.tobytes())
                        process.stdin.flush()
                    except BrokenPipeError:
                        self.logger.error("FFmpeg process terminated unexpectedly")
                        stop_event.set()
                        break
                    
                    encode_time = time.time() - encode_start
                    total_frame_encode_time += encode_time
                    
                    # Explicitly delete frame to free memory
                    del frame
                    
                    frame_count += 1
                    
                    # Log every frame for detailed monitoring
                    self.logger.info("ENCODER_FRAME", 
                                   thread="Encoder", 
                                   frame_number=frame_number, 
                                   frames_written=frame_count,
                                   input_queue_size=input_queue.qsize(),
                                   timestamp=time.time())
                    
                    # Additional progress logging every 100 frames
                    if frame_count % 100 == 0:
                        self.logger.info("ENCODER_PROGRESS", 
                                       thread="Encoder", 
                                       frames_written=frame_count,
                                       total_frames=video_info['frame_count'],
                                       progress_pct=round((frame_count / video_info['frame_count']) * 100, 1),
                                       timestamp=time.time())
                    
                    # Update progress and checkpoint
                    if progress_callback and hasattr(self.config, 'processing') and hasattr(self.config.processing, 'checkpoint_interval'):
                        if time.time() - last_checkpoint >= self.config.processing.checkpoint_interval:
                            progress_callback(task_id, frame_count, video_info['frame_count'])
                            last_checkpoint = time.time()
                    
                except Empty:
                    # No frame available, brief pause to avoid busy waiting
                    continue
                except Exception as e:
                    self.logger.error("Encoder thread processing error", error=str(e), frame_number=frame_number if 'frame_number' in locals() else 'unknown')
                    break
            
            # Close stdin to signal end of input
            process.stdin.close()
            
            # Wait for FFmpeg to finish video encoding (2-hour max safety timeout)
            try:
                return_code = process.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                self.logger.error("FFmpeg encoding timed out after 2 hours, killing process")
                process.kill()
                process.wait()
                stop_event.set()
                return {
                    'processed_frames': 0,
                    'encoder_time': 0.0,
                    'total_frame_encode_time': 0.0,
                    'error': 'FFmpeg encoding timed out'
                }
            if return_code != 0:
                self.logger.error("FFmpeg video encoding failed", return_code=return_code)
                stop_event.set()
                return {
                    'processed_frames': 0,
                    'encoder_time': 0.0,
                    'total_frame_encode_time': 0.0,
                    'error': f'FFmpeg failed with return code {return_code}'
                }
            
            self.logger.info("Video encoding completed", frames_written=frame_count)
            
            # Combine video with original audio (if audio exists)
            if has_audio:
                self.logger.info("Combining video with original audio", 
                               temp_video=temp_video_path, output=output_path)
                self._combine_video_with_audio(temp_video_path, input_path, output_path, video_info, processing_settings)
            else:
                # No audio, just move the temp file to final output
                self.logger.info("No audio in original, moving video to final output")
                os.rename(temp_video_path, output_path)
            
            # Clean up temporary file (only if it still exists)
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            
            # Store timing results
            total_time = time.time() - start_time
            self.thread_timings['encoder_time'] = total_time
            self.thread_timings['total_frame_encode_time'] = total_frame_encode_time
            
            self.logger.info("Encoder thread completed", 
                           final_frame_count=frame_count,
                           total_time=total_time,
                           frame_encode_time=total_frame_encode_time)
            
            return {
                'processed_frames': frame_count,
                'encoder_time': total_time,
                'total_frame_encode_time': total_frame_encode_time
            }
            
        except Exception as e:
            self.logger.error("Encoder thread error", error=str(e))
            stop_event.set()
            return {
                'processed_frames': 0,
                'encoder_time': 0.0,
                'total_frame_encode_time': 0.0,
                'error': str(e)
            }
    
    def _combine_video_with_audio(self, video_path: str, input_path: str, output_path: str, 
                                video_info: Dict[str, Any], processing_settings: ProcessingSettings):
        """Combine processed video with original audio using FFmpeg."""
        try:
            # Create input streams
            input_video = ffmpeg.input(video_path)
            input_audio = ffmpeg.input(input_path)
            
            # Create output stream combining video and audio
            stream = ffmpeg.output(
                input_video['v'],  # Video stream from processed video
                input_audio['a'],  # Audio stream from original video
                output_path,
                acodec='copy',  # Copy audio without re-encoding
                vcodec='copy'   # Copy video without re-encoding (already processed)
            )
            
            # Run FFmpeg
            stream.overwrite_output().run(quiet=True)
            
            self.logger.info("Video and audio combined successfully", 
                           video_source=video_path, 
                           audio_source=input_path, 
                           output=output_path)
            
        except ffmpeg.Error as e:
            self.logger.error("FFmpeg audio combining failed", error=str(e))
            raise
    
    def _get_source_preserving_encoding_params(self, video_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get encoding parameters that preserve the source video characteristics."""
        params = {}
        
        # Determine codec - try to use equivalent modern codec
        source_codec = video_info.get('codec_name', 'unknown').lower()
        
        codec_preserved = False
        if source_codec in ['h264', 'avc']:
            params['vcodec'] = 'libx264'
            codec_preserved = True
        elif source_codec in ['h265', 'hevc']:
            params['vcodec'] = 'libx265'
            codec_preserved = True
        elif source_codec in ['vp9']:
            params['vcodec'] = 'libvpx-vp9'
            codec_preserved = True
        elif source_codec in ['vp8']:
            params['vcodec'] = 'libvpx'
            codec_preserved = True
        else:
            # Default to libx264 for maximum compatibility
            params['vcodec'] = 'libx264'
            codec_preserved = False
            self.logger.info("Using default codec for unknown source", 
                           source_codec=source_codec, output_codec='libx264')
        
        # Update stats
        self.processing_stats['output_codec'] = params['vcodec']
        self.processing_stats['codec_preserved'] = codec_preserved
        
        # Preserve bitrate if available
        bitrate_preserved = False
        source_bitrate = video_info.get('bit_rate')
        if source_bitrate:
            try:
                bitrate_mbps = int(source_bitrate) / 1000000
                # Set target bitrate slightly lower to account for processing changes
                target_bitrate = max(int(bitrate_mbps * 0.95), 1)  # 95% of source, min 1 Mbps
                params['b:v'] = f"{target_bitrate}M"
                
                # Set max bitrate buffer for variable content
                params['maxrate'] = f"{int(target_bitrate * 1.2)}M"
                params['bufsize'] = f"{int(target_bitrate * 2)}M"
                
                bitrate_preserved = True
                self.logger.debug("Preserving source bitrate", 
                                source_mbps=bitrate_mbps,
                                target_mbps=target_bitrate)
            except (ValueError, TypeError):
                # Fallback to CRF if bitrate parsing fails
                params['crf'] = 23
                self.logger.warning("Could not parse source bitrate, using CRF", 
                                  source_bitrate=source_bitrate)
        else:
            # No bitrate info available, use reasonable CRF
            params['crf'] = 23
            self.logger.debug("No source bitrate available, using CRF=23")
        
        # Update stats
        self.processing_stats['bitrate_preserved'] = bitrate_preserved
        
        # Preserve pixel format if possible
        source_pix_fmt = video_info.get('pix_fmt', 'unknown')
        if source_pix_fmt in ['yuv420p', 'yuv422p', 'yuv444p', 'yuv420p10le']:
            params['pix_fmt'] = source_pix_fmt
        else:
            params['pix_fmt'] = 'yuv420p'  # Most compatible default
        
        # Use faster preset for better performance
        params['preset'] = 'fast'
        
        # Copy other relevant encoding parameters if available
        if video_info.get('profile') and video_info['profile'] != 'unknown':
            profile = video_info['profile'].lower()
            if profile in ['baseline', 'main', 'high']:
                params['profile:v'] = profile
        
        return params
