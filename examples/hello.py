from typing import List


def say_hello(name: str) -> str:
    """Generate a greeting message for a given name.
    
    Args:
        name: The name of the person to greet.
        
    Returns:
        A formatted greeting string.
    """
    return f"Hello, {name}!"


def greet_everyone(names: List[str]) -> List[str]:
    """Generate greeting messages for multiple people.
    
    Args:
        names: A list of names to greet.
        
    Returns:
        A list of formatted greeting strings, one for each name.
    """
    greetings = []
    for name in names:
        greetings.append(say_hello(name))
    return greetings


def main() -> None:
    """Main function to demonstrate the greeting functions."""
    print("Hello World!")
    names = ["Alice", "Bob", "Charlie"]
    print(greet_everyone(names))


if __name__ == "__main__":
    main()
