from typing import List


def say_hello(name: str) -> str:
    """Generate a greeting message for a given name.
    
    Args:
        name: The name of the person to greet.
        
    Returns:
        A formatted greeting string.
        
    Raises:
        TypeError: If name is not a string type.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string type")
    return f"Hello, {name}!"


def greet_everyone(names: List[str]) -> List[str]:
    """Generate greeting messages for multiple people.
    
    Args:
        names: A list of names to greet.
        
    Returns:
        A list of formatted greeting strings, one for each name.
        
    Raises:
        TypeError: If names is not a list or any element is not a string.
    """
    if not isinstance(names, list):
        raise TypeError("names must be a list")
    if not all(isinstance(name, str) for name in names):
        raise TypeError("all elements in names must be strings")
    return [say_hello(name) for name in names]


def main() -> None:
    """Main function to demonstrate the greeting functions."""
    print("Hello World!")
    names = ["Alice", "Bob", "Charlie"]
    print(greet_everyone(names))


if __name__ == "__main__":
    main()
