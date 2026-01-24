"""Precision Loss Validation Tests.

Tests for validating precision compatibility across heterogeneous GPU devices:
- Float32 to Float16 conversion
- Quantization compatibility (INT8, INT4)
- Precision-loss accumulation in multi-device chains
- Numerical stability in distributed inference
"""

import numpy as np
import pytest


class TestPrecisionConversions:
    """Test precision conversion operations."""

    def test_float32_to_float16_conversion(self):
        """Test converting float32 to float16."""
        # Create test data
        data_f32 = np.array([1.0, -2.5, 3.14159, 0.0, 1e-3], dtype=np.float32)
        
        # Convert to float16
        data_f16 = data_f32.astype(np.float16)
        
        # Convert back
        data_f32_back = data_f16.astype(np.float32)
        
        # Calculate error
        error = np.abs(data_f32 - data_f32_back)
        max_error = np.max(error)
        
        # Error should be small but non-zero (except for exact representable values)
        assert max_error < 0.001  # Tolerance for float16

    def test_float16_range_limits(self):
        """Test float16 range limitations."""
        # Float16 max is ~65500
        large_f32 = np.array([100000.0, -100000.0], dtype=np.float32)
        f16 = large_f32.astype(np.float16)
        
        # Very large values become inf
        assert np.any(np.isinf(f16))

    def test_float16_precision_loss(self):
        """Test precision loss in float16."""
        # Float16 has limited precision (~3-4 decimal places)
        precision_test = np.array(
            [1.23456789, 9.87654321, 0.00123456],
            dtype=np.float32
        )
        
        f16 = precision_test.astype(np.float16)
        f32_back = f16.astype(np.float32)
        
        # Check that we lost precision but not catastrophically
        error = np.abs(precision_test - f32_back) / np.abs(precision_test)
        assert np.all(error < 0.01)  # < 1% error


class TestQuantizationCompatibility:
    """Test INT8 and INT4 quantization compatibility."""

    def test_int8_quantization(self):
        """Test INT8 quantization (weights and activations)."""
        # Typical weight range: -1.0 to +1.0
        weights_f32 = np.random.uniform(-1.0, 1.0, 100).astype(np.float32)
        
        # Quantize to INT8 (-128 to 127)
        scale = 127.0 / np.max(np.abs(weights_f32))
        weights_i8 = np.round(weights_f32 * scale).astype(np.int8)
        
        # Dequantize
        weights_recovered = weights_i8.astype(np.float32) / scale
        
        # Check reconstruction error
        error = np.abs(weights_f32 - weights_recovered)
        max_error = np.max(error)
        
        assert max_error < 0.01  # Acceptable quantization error

    def test_int4_quantization_extreme(self):
        """Test INT4 quantization (more aggressive)."""
        # INT4: -8 to 7 (16 levels)
        values = np.array([-1.0, -0.5, 0.0, 0.5, 1.0], dtype=np.float32)
        
        # Quantize to INT4
        scale = 7.0 / np.max(np.abs(values))
        values_i4 = np.round(values * scale).astype(np.int8)
        
        # Dequantize
        values_recovered = values_i4.astype(np.float32) / scale
        
        # INT4 has larger quantization error
        error = np.abs(values - values_recovered)
        max_error = np.max(error)
        
        # INT4 error will be larger but still manageable
        assert max_error < 0.15  # ~15% tolerance for INT4

    def test_symmetric_vs_asymmetric_quantization(self):
        """Compare symmetric vs asymmetric quantization."""
        data = np.array([0.1, 0.5, 1.0, 1.5, 2.0], dtype=np.float32)
        
        # Symmetric: range from -max to +max
        max_val = np.max(np.abs(data))
        symmetric_scale = 127.0 / max_val
        symmetric_q = np.round(data * symmetric_scale).astype(np.int8)
        symmetric_recovered = symmetric_q.astype(np.float32) / symmetric_scale
        
        # Asymmetric: min to max
        min_val, max_val = np.min(data), np.max(data)
        asymmetric_scale = 255.0 / (max_val - min_val)
        asymmetric_q = np.round((data - min_val) * asymmetric_scale).astype(np.uint8)
        asymmetric_recovered = asymmetric_q.astype(np.float32) / asymmetric_scale + min_val
        
        symmetric_error = np.mean(np.abs(data - symmetric_recovered))
        asymmetric_error = np.mean(np.abs(data - asymmetric_recovered))
        
        # Asymmetric should generally be better for skewed ranges
        assert asymmetric_error <= symmetric_error


class TestMultiDevicePrecisionChain:
    """Test precision loss accumulation in device chains."""

    def test_precision_loss_single_transfer(self):
        """Test precision loss in single device transfer."""
        # Simulate transfer through low-precision device
        data_f32 = np.random.randn(100).astype(np.float32)
        
        # Degrade to float16 (simulating transfer)
        data_degraded = data_f32.astype(np.float16).astype(np.float32)
        
        error = np.mean(np.abs((data_f32 - data_degraded) / (np.abs(data_f32) + 1e-7)))
        assert error < 0.01  # < 1% average error

    def test_precision_loss_chain_accumulation(self):
        """Test precision loss accumulation over device chain."""
        data = np.random.randn(100).astype(np.float32)
        
        # Device 1: f32 -> f16
        data = data.astype(np.float16).astype(np.float32)
        error_1 = np.mean(np.abs(np.gradient(data)))
        
        # Device 2: f32 -> f16 -> f32
        data = data.astype(np.float16).astype(np.float32)
        error_2 = np.mean(np.abs(np.gradient(data)))
        
        # Device 3: f32 -> f16 -> f32
        data = data.astype(np.float16).astype(np.float32)
        error_3 = np.mean(np.abs(np.gradient(data)))
        
        # Error should accumulate but remain bounded
        assert error_3 > error_1  # Accumulation
        assert error_3 < 0.1  # But still bounded

    def test_heterogeneous_precision_compatibility(self):
        """Test that heterogeneous precisions can coexist."""
        # Device A: float32
        # Device B: float16
        # Device C: INT8 quantized
        
        data_a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        data_b = data_a.astype(np.float16)  # Device B precision
        
        # INT8 quantization
        scale = 127.0 / np.max(np.abs(data_a))
        data_c = np.round(data_a * scale).astype(np.int8)
        data_c = data_c.astype(np.float32) / scale  # Device C precision
        
        # All should be usable together
        combined = np.concatenate([data_a, data_b.astype(np.float32), data_c])
        assert combined.shape == (9,)


class TestNumericalStability:
    """Test numerical stability in distributed operations."""

    def test_accumulation_order_matters(self):
        """Test that accumulation order affects numerical precision."""
        values = np.array([1.0, 1e-7, 1e-7, 1e-7] * 25, dtype=np.float32)
        
        # Forward accumulation
        sum_forward = np.sum(values)
        
        # Reversed accumulation
        sum_reverse = np.sum(values[::-1])
        
        # Results might differ due to floating point rounding
        assert abs(sum_forward - sum_reverse) < 0.001

    def test_batch_norm_stability(self):
        """Test batch normalization stability across precision levels."""
        data = np.random.randn(1000).astype(np.float32)
        
        # Normalize
        mean = np.mean(data)
        std = np.std(data)
        normalized_f32 = (data - mean) / (std + 1e-5)
        
        # Same operation in float16
        normalized_f16 = (data.astype(np.float16).astype(np.float32) - mean) / (std + 1e-5)
        
        error = np.mean(np.abs(normalized_f32 - normalized_f16))
        assert error < 0.01  # Should be stable

    def test_gradient_scaling_numerical_issues(self):
        """Test gradient scaling for mixed precision (common in AI inference)."""
        # Very small gradients can underflow in float16
        gradients_f32 = np.array([1e-4, 1e-5, 1e-6], dtype=np.float32)
        
        # With scaling
        scale = 1e4
        scaled = gradients_f32 * scale
        scaled_f16 = scaled.astype(np.float16)  # Still representable
        unscaled = scaled_f16.astype(np.float32) / scale
        
        # Should preserve gradient sign and rough magnitude
        assert np.all(np.sign(unscaled) == np.sign(gradients_f32))


class TestPrecisionInferenceValidation:
    """Validate precision compatibility for actual inference scenarios."""

    def test_attention_precision_stability(self):
        """Test precision in attention mechanism (softmax + matrix mult)."""
        # Query, Key shapes typical for attention
        q = np.random.randn(32, 8, 64).astype(np.float32)  # [batch, heads, d_k]
        k = np.random.randn(32, 8, 64).astype(np.float32)
        
        # Attention scores
        scores_f32 = np.matmul(q, k.transpose(0, 2, 1)) / np.sqrt(64)
        
        # Degrade to float16 (simulating device boundary)
        scores_f16 = scores_f32.astype(np.float16).astype(np.float32)
        
        # Error in attention scores
        error = np.mean(np.abs(scores_f32 - scores_f16))
        assert error < 1.0  # Attention scores should be roughly preserved

    def test_embedding_lookup_precision(self):
        """Test precision in embedding operations."""
        # Embedding matrix
        embeddings = np.random.randn(10000, 768).astype(np.float32)
        indices = np.array([0, 100, 1000, 5000], dtype=np.int32)
        
        # Lookup in original precision
        result_f32 = embeddings[indices]
        
        # Lookup after degradation
        embeddings_f16 = embeddings.astype(np.float16)
        result_f16 = embeddings_f16[indices].astype(np.float32)
        
        # Precision loss in embeddings
        error = np.mean(np.abs(result_f32 - result_f16))
        assert error < 0.1

    def test_layer_norm_precision(self):
        """Test layer normalization across precision boundaries."""
        batch = np.random.randn(32, 512).astype(np.float32)
        
        # Layer norm in original precision
        mean = np.mean(batch, axis=-1, keepdims=True)
        var = np.var(batch, axis=-1, keepdims=True)
        normalized_f32 = (batch - mean) / np.sqrt(var + 1e-5)
        
        # Layer norm after float16 conversion
        batch_f16 = batch.astype(np.float16)
        mean_f16 = np.mean(batch_f16, axis=-1, keepdims=True)
        var_f16 = np.var(batch_f16, axis=-1, keepdims=True)
        normalized_f16 = (batch_f16.astype(np.float32) - mean_f16.astype(np.float32)) / \
                         np.sqrt(var_f16.astype(np.float32) + 1e-5)
        
        error = np.mean(np.abs(normalized_f32 - normalized_f16))
        assert error < 0.01  # Should be stable


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
