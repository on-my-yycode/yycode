from typing import List, Generator


def fibonacci(n: int) -> int:
    """Calculate the nth number in the Fibonacci sequence.
    
    Args:
        n: A non-negative integer indicating the term to calculate.
        
    Returns:
        The nth number in the Fibonacci sequence.
        
    Raises:
        ValueError: If n is a negative integer or not an integer type.
    """
    if type(n) is not int or n < 0:
        raise ValueError("n must be a non-negative integer")
    
    if n == 0:
        return 0
    elif n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def fibonacci_generator(n: int) -> Generator[int, None, None]:
    """Generate the first n+1 terms of the Fibonacci sequence (starting from term 0).
    
    Args:
        n: A non-negative integer indicating the last term to generate.
        
    Yields:
        Integers representing the Fibonacci sequence from term 0 to term n.
        
    Raises:
        ValueError: If n is a negative integer or not an integer type.
    """
    if type(n) is not int or n < 0:
        raise ValueError("n must be a non-negative integer")
    
    a, b = 0, 1
    for _ in range(n + 1):
        yield a
        a, b = b, a + b


def fibonacci_list(n: int) -> List[int]:
    """Generate a list of the first n+1 terms of the Fibonacci sequence (starting from term 0).
    
    Args:
        n: A non-negative integer indicating the last term to include in the list.
        
    Returns:
        A list containing the Fibonacci sequence from term 0 to term n.
        
    Raises:
        ValueError: If n is a negative integer or not an integer type.
    """
    return list(fibonacci_generator(n))
