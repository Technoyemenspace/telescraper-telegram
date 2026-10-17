import unittest
from pathlib import Path


class FreeHostingTests(unittest.TestCase):
    def test_render_uses_free_plan_without_paid_disk(self):
        config = (Path(__file__).resolve().parents[2] / 'render.yaml').read_text()
        self.assertIn('    plan: free\n', config)
        self.assertNotIn('    disk:', config)


if __name__ == '__main__':
    unittest.main()