"""在临时容器中仅执行密码参数读取片段，不启动数据库或站点。"""
import argparse
import subprocess
import unittest
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--image", required=True)
args, remaining = parser.parse_known_args()
script = (Path(__file__).resolve().parents[1] / "docker/entrypoint.sh").read_text(encoding="utf-8")
header = script.split("export SITE_NAME", 1)[0]


class DefaultTests(unittest.TestCase):
    def check(self, environment, assertions, prelude=""):
        command = ["docker", "run", "--rm", "-i", "--pull", "never", "--network", "none",
                   "--entrypoint", "/bin/bash"]
        for key, value in environment.items():
            command.extend(["-e", key + "=" + value])
        command.extend([args.image, "-c", prelude + "\n" + header + "\n" + assertions])
        subprocess.run(command, input="", text=True, capture_output=True, check=True)

    def test_defaults(self):
        self.check({"DB_ROOT_PASSWORD": "", "ADMIN_PASSWORD": ""},
                   '[[ "$DB_ROOT_PASSWORD" == Pass1234 && "$ADMIN_PASSWORD" == Pass1234 ]]')

    def test_environment_override(self):
        self.check({"DB_ROOT_PASSWORD": "demo1", "ADMIN_PASSWORD": "demo2"},
                   '[[ "$DB_ROOT_PASSWORD" == demo1 && "$ADMIN_PASSWORD" == demo2 ]]')

    def test_file_overrides_environment_and_default(self):
        self.check({"DB_ROOT_PASSWORD": "demo1", "DB_ROOT_PASSWORD_FILE": "/tmp/test-password", "ADMIN_PASSWORD": ""},
                   '[[ "$DB_ROOT_PASSWORD" == file && "$ADMIN_PASSWORD" == Pass1234 ]]',
                   "printf '%s' file > /tmp/test-password")


if __name__ == "__main__":
    unittest.main(argv=["test_defaults"] + remaining)
