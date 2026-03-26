class SimpleTools:
    def add_numbers(self, a: float, b: float) -> dict:
        """Add two numbers together and return the result."""
        return {"success": True, "result": a + b, "expression": f"{a} + {b} = {a + b}"}

    def reverse_text(self, text: str) -> dict:
        """Reverse a string of text."""
        return {"success": True, "original": text, "reversed": text[::-1]}

    def list_files(self, directory: str = ".") -> dict:
        """List files in a directory."""
        import os
        try:
            files = os.listdir(directory)
            return {"success": True, "directory": directory, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}