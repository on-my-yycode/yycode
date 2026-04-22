"""Tests for hello.py module."""

import pytest
from hello import say_hello, greet_everyone


class TestSayHello:
    """Tests for the say_hello function."""
    
    def test_say_hello_with_name(self):
        """Test say_hello with a regular name."""
        result = say_hello("Alice")
        assert result == "Hello, Alice!"
    
    def test_say_hello_with_empty_string(self):
        """Test say_hello with an empty string."""
        result = say_hello("")
        assert result == "Hello, !"
    
    def test_say_hello_with_numbers(self):
        """Test say_hello with numbers in the name."""
        result = say_hello("Bob123")
        assert result == "Hello, Bob123!"
    
    def test_say_hello_with_special_characters(self):
        """Test say_hello with special characters."""
        result = say_hello("Chärlie!")
        assert result == "Hello, Chärlie!!"


class TestGreetEveryone:
    """Tests for the greet_everyone function."""
    
    def test_greet_everyone_with_multiple_names(self):
        """Test greet_everyone with a list of names."""
        names = ["Alice", "Bob", "Charlie"]
        result = greet_everyone(names)
        expected = ["Hello, Alice!", "Hello, Bob!", "Hello, Charlie!"]
        assert result == expected
    
    def test_greet_everyone_with_empty_list(self):
        """Test greet_everyone with an empty list."""
        result = greet_everyone([])
        assert result == []
    
    def test_greet_everyone_with_one_name(self):
        """Test greet_everyone with a single name in the list."""
        result = greet_everyone(["Alice"])
        assert result == ["Hello, Alice!"]
    
    def test_greet_everyone_with_duplicate_names(self):
        """Test greet_everyone with duplicate names."""
        names = ["Alice", "Alice", "Bob"]
        result = greet_everyone(names)
        expected = ["Hello, Alice!", "Hello, Alice!", "Hello, Bob!"]
        assert result == expected


def test_main_function_execution():
    """Test that main function can be executed without errors."""
    from hello import main
    # Just verify it runs without exceptions
    main()
