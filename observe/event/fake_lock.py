class FakeLock:
    """
    A fake lock object to let the code run without errors when running in a single thread and single process.

    Example:
    ```
    with FakeLock():
        print("Locked")

    print("Unlocked")
    ```
    """
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
