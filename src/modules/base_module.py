# security-worker/modules/base_module.py

from abc import ABC, abstractmethod

class BaseScanner(ABC):
    def __init__(self):
        self.name = "Base Scanner"
        self.description = "Abstract Base Class for Scanners"

    @abstractmethod
    def scan(self, url: str, params: dict) -> list:
        """
        Main logic for scanning.
        Args:
            url (str): The target URL.
            params (dict): The parameters to fuzz (e.g., {'q': 'test'}).
        Returns:
            list: List of findings/vulnerabilities.
        """
        pass