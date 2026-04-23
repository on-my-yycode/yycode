"""Tests for utils.py module."""

import pytest
from utils import fibonacci, fibonacci_generator, fibonacci_list


class TestFibonacci:
    """Tests for the fibonacci function."""
    
    def test_fibonacci_base_cases(self):
        """Test fibonacci with base cases."""
        assert fibonacci(0) == 0
        assert fibonacci(1) == 1
        assert fibonacci(2) == 1
    
    def test_fibonacci_small_numbers(self):
        """Test fibonacci with small numbers."""
        assert fibonacci(3) == 2
        assert fibonacci(5) == 5
        assert fibonacci(10) == 55
    
    def test_fibonacci_large_number(self):
        """Test fibonacci with a larger number."""
        assert fibonacci(20) == 6765
    
    def test_fibonacci_negative_input(self):
        """Test that negative input raises ValueError."""
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            fibonacci(-1)
    
    def test_fibonacci_non_integer_input(self):
        """Test that non-integer input raises ValueError."""
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            fibonacci(3.14)
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            fibonacci("10")
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            fibonacci(True)  # bool is a subclass of int, but we reject it


class TestFibonacciGenerator:
    """Tests for the fibonacci_generator function."""
    
    def test_fibonacci_generator_basic(self):
        """Test fibonacci_generator generates correct sequence."""
        gen = fibonacci_generator(5)
        assert list(gen) == [0, 1, 1, 2, 3, 5]
    
    def test_fibonacci_generator_zero(self):
        """Test fibonacci_generator with n=0."""
        gen = fibonacci_generator(0)
        assert list(gen) == [0]
    
    def test_fibonacci_generator_one(self):
        """Test fibonacci_generator with n=1."""
        gen = fibonacci_generator(1)
        assert list(gen) == [0, 1]
    
    def test_fibonacci_generator_negative_input(self):
        """Test that negative input raises ValueError."""
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            list(fibonacci_generator(-1))


class TestFibonacciList:
    """Tests for the fibonacci_list function."""
    
    def test_fibonacci_list_basic(self):
        """Test fibonacci_list returns correct list."""
        assert fibonacci_list(0) == [0]
        assert fibonacci_list(1) == [0, 1]
        assert fibonacci_list(5) == [0, 1, 1, 2, 3, 5]
        assert fibonacci_list(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
    
    def test_fibonacci_list_negative_input(self):
        """Test that negative input raises ValueError."""
        with pytest.raises(ValueError, match="n must be a non-negative integer"):
            fibonacci_list(-1)
