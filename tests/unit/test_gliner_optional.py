"""Test that GLiNER is properly optional."""

import sys
import unittest
from unittest.mock import MagicMock, patch
import warnings

import pytest

from redactyl.types import PIIEntity, PIIType


class TestGLiNEROptional(unittest.TestCase):
    """Test GLiNER optional dependency handling."""

    def test_gliner_parser_without_gliner(self):
        """Test that GlinerNameParser handles missing GLiNER gracefully."""
        # Mock the gliner import to fail
        with patch.dict(sys.modules, {"gliner": None}):
            # Remove gliner from sys.modules if it exists
            if "gliner" in sys.modules:
                del sys.modules["gliner"]
            
            # Now import should work even without GLiNER
            from redactyl.detectors.gliner_parser import GlinerNameParser
            
            # Create parser - should not raise
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                parser = GlinerNameParser()
                
                # Try to parse - should return None
                entity = PIIEntity(
                    type=PIIType.PERSON,
                    value="John Doe",
                    start=0,
                    end=8,
                    confidence=0.9
                )
                result = parser.parse_name_components(entity)
                
                # Should return None when GLiNER is not available
                self.assertIsNone(result)
                
                # Should have warned about missing GLiNER
                self.assertTrue(any("GLiNER is not installed" in str(warning.message) 
                                  for warning in w))

    def test_presidio_detector_without_gliner(self):
        """Test that PresidioDetector handles missing GLiNER gracefully."""
        # Mock the gliner import to fail
        with patch.dict(sys.modules, {"gliner": None}):
            if "gliner" in sys.modules:
                del sys.modules["gliner"]
            
            # Import should work
            from redactyl.detectors.presidio import PresidioDetector
            
            # Create detector with GLiNER requested
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                detector = PresidioDetector(use_gliner_for_names=True)
                
                # Should have warned about GLiNER not being available
                self.assertTrue(
                    any("GLiNER" in str(warning.message) for warning in w),
                    f"Expected GLiNER warning, got: {[str(w.message) for w in w]}"
                )

    def test_presidio_detector_with_gliner_disabled(self):
        """Test that PresidioDetector works with GLiNER explicitly disabled."""
        from redactyl.detectors.presidio import PresidioDetector
        
        # Should not try to load GLiNER
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            detector = PresidioDetector(use_gliner_for_names=False)
            
            # Should not have any GLiNER-related warnings
            gliner_warnings = [warning for warning in w 
                             if "GLiNER" in str(warning.message)]
            self.assertEqual(len(gliner_warnings), 0)
            
            # Parser should be None
            self.assertIsNone(detector._gliner_parser)

    @patch("redactyl.detectors.gliner_parser.GLiNER")
    def test_gliner_parser_with_mock_gliner(self, mock_gliner_class):
        """Test GlinerNameParser with mocked GLiNER."""
        from redactyl.detectors.gliner_parser import GlinerNameParser
        
        # Setup mock
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = [
            {"label": "first_name", "text": "John", "score": 0.9},
            {"label": "last_name", "text": "Doe", "score": 0.85}
        ]
        mock_gliner_class.from_pretrained.return_value = mock_model
        
        # Create parser
        parser = GlinerNameParser()
        
        # Parse entity
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="John Doe",
            start=0,
            end=8,
            confidence=0.9
        )
        
        components = parser.parse_name_components(entity)
        
        # Should have parsed components
        self.assertIsNotNone(components)
        self.assertEqual(len(components), 2)
        self.assertEqual(components[0].type, PIIType.NAME_FIRST)
        self.assertEqual(components[0].value, "John")
        self.assertEqual(components[1].type, PIIType.NAME_LAST)
        self.assertEqual(components[1].value, "Doe")

    def test_gliner_parser_properties(self):
        """Test GlinerNameParser properties and methods."""
        with patch.dict(sys.modules, {"gliner": None}):
            if "gliner" in sys.modules:
                del sys.modules["gliner"]
            
            # Also patch the module-level GLiNER variable
            import redactyl.detectors.gliner_parser as gliner_module
            original_gliner = gliner_module.GLiNER
            gliner_module.GLiNER = None
            
            # Clear the cache to ensure fresh initialization
            gliner_module._clear_gliner_cache()
            
            try:
                from redactyl.detectors.gliner_parser import GlinerNameParser
                
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    parser = GlinerNameParser()
                
                    # Check availability
                    self.assertFalse(parser.is_available)
                    
                    # Test parse_single_name with unavailable GLiNER
                    result = parser.parse_single_name("John Doe")
                    expected = {"title": "", "first": "", "middle": "", "last": ""}
                    self.assertEqual(result, expected)
            finally:
                # Restore the original GLiNER
                gliner_module.GLiNER = original_gliner


@pytest.mark.skipif(
    "gliner" in sys.modules or any("gliner" in mod for mod in sys.modules),
    reason="Skip when GLiNER is installed to test without it"
)
class TestWithoutGLiNER:
    """Tests that run only when GLiNER is not installed."""
    
    def test_import_without_gliner(self):
        """Verify imports work without GLiNER installed."""
        # These imports should not fail
        from redactyl.detectors.presidio import PresidioDetector
        from redactyl.detectors.gliner_parser import GlinerNameParser
        
        assert PresidioDetector is not None
        assert GlinerNameParser is not None