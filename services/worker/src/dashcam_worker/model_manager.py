"""
Model management module.

Handles YOLO model loading, caching, and management as specified
in the worker specification.
"""

import os
from ultralytics import YOLO
from typing import Dict, Any, List
import structlog

from .config import get_config
from .hardware import get_worker_capabilities


class ModelManager:
    """
    YOLO model management and caching.
    
    Handles model loading based on size requirements and hardware capabilities.
    Implements caching to avoid repeated downloads.
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = structlog.get_logger("model_manager")
        self.loaded_models: Dict[str, Any] = {}
        self.capabilities = get_worker_capabilities()
        
        # Ensure model cache directory exists
        os.makedirs(self.config.processing.model_cache_dir, exist_ok=True)
    
    def load_model(self, model_size: str, detection_type: str = "bbox") -> Any:
        """
        Load YOLO12 model based on size specification and detection type.
        
        Args:
            model_size: "nano", "small", "medium", "large", or "xlarge"
            detection_type: "bbox" for detection or "segmentation" for instance segmentation
        
        Returns:
            Loaded YOLO12 model
        
        Raises:
            Exception: If model loading fails or size not supported
        """
        # Create cache key that includes detection type
        cache_key = f"{model_size}_{detection_type}"
        
        if cache_key in self.loaded_models:
            self.logger.debug("Using cached model", model_size=model_size, detection_type=detection_type)
            return self.loaded_models[cache_key]
        
        # Check model size against capabilities and warn if beyond recommendation
        if not self._can_load_model_size(model_size):
            self.logger.warning("Requested model size exceeds recommended capabilities", 
                              requested=model_size, 
                              recommended_max=self.capabilities.max_model_size,
                              gpu_memory_gb=self.capabilities.gpu_memory_gb,
                              message="Attempting to load anyway - may cause out of memory errors")
        
        try:
            model_path = self._get_model_path(model_size, detection_type)
            
            self.logger.info("Loading YOLO model", 
                           model_size=model_size,
                           detection_type=detection_type,
                           model_path=model_path,
                           device=self.capabilities.compute_device)
            
            # Load model from our models directory
            model = YOLO(model_path)
            
            # Move to appropriate device
            if self.capabilities.compute_device == "cuda":
                model.to('cuda')
            elif self.capabilities.compute_device == "mps":
                model.to('mps')
            else:
                model.to('cpu')
            
            # Cache the model with the detection type key
            self.loaded_models[cache_key] = model
            
            self.logger.info("Model loaded successfully", 
                           model_size=model_size,
                           detection_type=detection_type,
                           device=self.capabilities.compute_device)
            
            return model
            
        except Exception as e:
            self.logger.error("Failed to load model", 
                            model_size=model_size, detection_type=detection_type, error=str(e))
            # Try fallback only if not already using the smallest model
            if model_size != "nano":
                self.logger.info("Attempting fallback to nano model")
                return self.load_model("nano", detection_type)
            else:
                raise Exception(f"Failed to load any model: {str(e)}")
    
    def _can_load_model_size(self, model_size: str) -> bool:
        """
        Check if worker can handle requested model size.
        
        Args:
            model_size: Requested model size
        
        Returns:
            True if model size is supported
        """
        size_hierarchy = ["nano", "small", "medium", "large", "xlarge"]
        max_index = size_hierarchy.index(self.capabilities.max_model_size)
        requested_index = size_hierarchy.index(model_size)
        
        return requested_index <= max_index
    
    def _get_fallback_model_size(self, requested_size: str) -> str:
        """
        Get fallback model size based on capabilities.
        
        Args:
            requested_size: Originally requested size
        
        Returns:
            Supported fallback size
        """
        size_hierarchy = ["nano", "small", "medium", "large", "xlarge"]
        max_index = size_hierarchy.index(self.capabilities.max_model_size)
        
        # Return the largest supported size
        return size_hierarchy[max_index]
    
    def _get_model_path(self, model_size: str, detection_type: str = "bbox") -> str:
        """
        Get model file path, downloading if necessary.
        
        Args:
            model_size: Model size specification
            detection_type: "bbox" for detection or "segmentation" for instance segmentation
        
        Returns:
            Path to model file in our models directory
        """
        # Model mapping upgraded to YOLO12 with expanded size options
        if detection_type == "segmentation":
            # Segmentation models - Note: YOLO12 segmentation models will be available soon
            # For now, we'll use YOLO11 segmentation models as they're compatible
            model_mapping = {
                "nano": "yolo11n-seg.pt",     # ~4MB  - Ultra lightweight segmentation
                "small": "yolo11s-seg.pt",    # ~14MB - Small segmentation
                "medium": "yolo11m-seg.pt",   # ~32MB - Balanced segmentation  
                "large": "yolo11l-seg.pt",    # ~58MB - High accuracy segmentation
                "xlarge": "yolo11x-seg.pt"    # ~75MB - Maximum accuracy segmentation
            }
        else:
            # Detection models (bbox)
            model_mapping = {
                "nano": "yolo12n.pt",     # ~3MB  - Ultra lightweight for edge devices
                "small": "yolo12s.pt",    # ~11MB - Small and efficient
                "medium": "yolo12m.pt",   # ~26MB - Balanced performance
                "large": "yolo12l.pt",    # ~52MB - High accuracy
                "xlarge": "yolo12x.pt"    # ~69MB - Maximum accuracy
            }
        
        model_filename = model_mapping[model_size]
        model_path = os.path.join(self.config.processing.model_cache_dir, model_filename)
        
        # Check if model exists locally in our models directory
        if os.path.exists(model_path):
            self.logger.debug("Using cached model file", path=model_path)
            return model_path
        
        # Model doesn't exist in our cache, need to download it
        self.logger.info("Model not found in cache, downloading", 
                        model_size=model_size, filename=model_filename)
        
        # Let ultralytics download to its default location first
        temp_model = YOLO(model_filename)
        
        # Find where ultralytics downloaded the model
        from ultralytics.utils import WEIGHTS_DIR
        default_model_path = os.path.join(WEIGHTS_DIR, model_filename)
        
        if os.path.exists(default_model_path):
            # Copy the model to our models directory
            import shutil
            shutil.copy2(default_model_path, model_path)
            self.logger.info("Model downloaded and copied to cache", 
                           from_path=default_model_path,
                           to_path=model_path)
        else:
            # Fallback: check current working directory and other common locations
            possible_locations = [
                model_filename,  # Current working directory
                os.path.join(os.getcwd(), model_filename),
                os.path.join(os.path.expanduser("~/.cache/ultralytics"), model_filename),
                os.path.join(os.path.expanduser("~"), model_filename)
            ]
            
            for location in possible_locations:
                if os.path.exists(location):
                    import shutil
                    shutil.copy2(location, model_path)
                    self.logger.info("Model found and copied to cache",
                                   from_path=location,
                                   to_path=model_path)
                    # Remove from the original location to avoid clutter
                    if location != model_path:
                        try:
                            os.remove(location)
                            self.logger.debug("Removed model from original location", path=location)
                        except Exception as e:
                            self.logger.warning("Could not remove model from original location", 
                                              path=location, error=str(e))
                    break
            else:
                # If we still can't find it, something went wrong
                self.logger.error("Could not locate downloaded model", filename=model_filename)
                raise FileNotFoundError(f"Downloaded model {model_filename} not found in expected locations")
        
        return model_path
    
    def get_model_info(self, model_size: str) -> Dict[str, Any]:
        """
        Get information about a model size.
        
        Args:
            model_size: Model size specification
        
        Returns:
            Dictionary with model information
        """
        model_info = {
            "nano": {
                "filename": "yolo12n.pt",
                "size_mb": 3,
                "mAP": 40.6,
                "description": "Ultra lightweight model for edge devices and CPU-only systems"
            },
            "small": {
                "filename": "yolo12s.pt", 
                "size_mb": 11,
                "mAP": 48.0,
                "description": "Small and efficient model for resource-constrained environments"
            },
            "medium": {
                "filename": "yolo12m.pt",
                "size_mb": 26,
                "mAP": 52.5,
                "description": "Balanced performance model for general-purpose use"
            },
            "large": {
                "filename": "yolo12l.pt",
                "size_mb": 52,
                "mAP": 53.7,
                "description": "High accuracy model for demanding applications"
            },
            "xlarge": {
                "filename": "yolo12x.pt",
                "size_mb": 69,
                "mAP": 55.2,
                "description": "Maximum accuracy model for highest precision requirements"
            }
        }
        
        return model_info.get(model_size, {})
    
    def clear_cache(self) -> None:
        """Clear all cached models from memory."""
        self.loaded_models.clear()
        self.logger.info("Model cache cleared")
    
    def is_model_loaded(self, model_size: str, detection_type: str = "bbox") -> bool:
        """
        Check if a model of the specified size and detection type is already loaded.
        
        Args:
            model_size: Model size to check
            detection_type: "bbox" for detection or "segmentation" for instance segmentation
            
        Returns:
            True if model is loaded, False otherwise
        """
        cache_key = f"{model_size}_{detection_type}"
        return cache_key in self.loaded_models
    
    def get_loaded_models(self) -> List[str]:
        """
        Get list of currently loaded model sizes.
        
        Returns:
            List of loaded model size names
        """
        return list(self.loaded_models.keys())
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about currently cached models.
        
        Returns:
            Dictionary with cache information
        """
        cache_info = {
            "loaded_models": list(self.loaded_models.keys()),
            "model_cache_dir": self.config.processing.model_cache_dir,
            "worker_capabilities": {
                "max_model_size": self.capabilities.max_model_size,
                "compute_device": self.capabilities.compute_device,
                "gpu_memory_gb": self.capabilities.gpu_memory_gb
            }
        }
        
        return cache_info
