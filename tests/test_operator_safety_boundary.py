from __future__ import annotations

import ast
from pathlib import Path
import unittest


class OperatorSafetyBoundaryTests(unittest.TestCase):
    def test_every_raw_mt5_write_is_inside_guard_wrapper(self):
        operator_dir = Path(__file__).resolve().parents[1] / "Operador"
        owners: list[tuple[str, str, str]] = []
        mt5_write_methods = {"order_send", "order_delete"}

        for source_path in operator_dir.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue
                    func = child.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr in mt5_write_methods
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "mt5"
                    ):
                        owners.append((source_path.name, func.attr, node.name))

        self.assertEqual(
            sorted(owners),
            [
                ("daemon.py", "order_delete", "_mt5_order_delete"),
                ("daemon.py", "order_send", "_mt5_order_send"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
