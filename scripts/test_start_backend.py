"""Verify .env loading using synthetic files only, never real service keys."""

import os
import tempfile
import unittest
from pathlib import Path

from env_file import read_env_file
from start_backend import initialize_env, runtime_environment


class EnvironmentConfiguration(unittest.TestCase):
    project = {
        "supabase": {
            "url": "https://example.supabase.co",
            "storage_bucket": "original-pdfs",
        }
    }
    keys = {
        "DATABASE_URL": "postgresql://fixture:fixture@localhost/fixture",
        "SUPABASE_SERVICE_ROLE_KEY": "test-storage",
        "MISTRAL_API_KEY": "test-mistral",
    }

    def read_fixture(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "configuration.txt"
            path.write_bytes(data)
            return read_env_file(path)

    def test_file_settings_configure_both_processes_without_prompting(self):
        data = "\n".join(f"{name}={value}" for name, value in self.keys.items())
        loaded = self.read_fixture(data.encode())
        values = runtime_environment({}, self.project, loaded)
        self.assertEqual(values["MISTRAL_API_KEY"], "test-mistral")
        self.assertEqual(values["SUPABASE_URL"], "https://example.supabase.co")
        self.assertNotIn("SUPABASE_URL", loaded)

    def test_server_environment_takes_precedence_over_file(self):
        original = {"MISTRAL_API_KEY": "environment-key"}
        values = runtime_environment(original, self.project, self.keys)
        self.assertEqual(values["MISTRAL_API_KEY"], "environment-key")
        self.assertNotIn("DATABASE_URL", original)

    def test_quotes_comments_equals_and_shell_syntax_are_literal(self):
        values = self.read_fixture(b'''# configuration
export A="space # equals=and$literal" # comment
B='$(never-execute) ${NEVER_EXPAND}'
C=token#hash=tail # comment
D="escaped\\\"quote\\\\slash"
E= # empty
''')
        self.assertEqual(values["A"], "space # equals=and$literal")
        self.assertEqual(values["B"], "$(never-execute) ${NEVER_EXPAND}")
        self.assertEqual(values["C"], "token#hash=tail")
        self.assertEqual(values["D"], 'escaped"quote\\slash')
        self.assertEqual(values["E"], "")

    def test_missing_file_allows_environment_only_deployment(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(read_env_file(Path(folder) / "missing.txt"), {})
        values = runtime_environment(self.keys, self.project)
        self.assertEqual(values["MISTRAL_API_KEY"], "test-mistral")

    def test_missing_or_removed_settings_fail_without_disclosing_values(self):
        with self.assertRaisesRegex(ValueError, "root .env") as error:
            runtime_environment({}, self.project, {"MISTRAL_API_KEY": "private-value"})
        self.assertNotIn("private-value", str(error.exception))
        with self.assertRaisesRegex(ValueError, "APP_MODE"):
            runtime_environment({}, self.project, {**self.keys, "APP_MODE": "obsolete"})

    def test_invalid_file_never_discloses_its_contents(self):
        for data in (b"private-invalid-assignment", b'A="private-unclosed', b"A=private\x00value"):
            with self.subTest(data=data), self.assertRaises(ValueError) as error:
                self.read_fixture(data)
            self.assertNotIn("private", str(error.exception))
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.read_fixture(b"A=\xff")

    def test_file_size_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            self.read_fixture(b"A=" + b"x" * (64 * 1024))

    def test_private_settings_with_control_characters_fail_before_provider_calls(self):
        for name in self.keys:
            for character in ("\n", "\r", "\t", "\x1f", "\x7f"):
                with self.subTest(name=name, character=repr(character)):
                    values = {**self.keys, name: "private-token" + character}
                    with self.assertRaisesRegex(ValueError, name) as error:
                        runtime_environment({}, self.project, values)
                    self.assertNotIn("private-token", str(error.exception))
        loaded = self.read_fixture(b'MISTRAL_API_KEY="private-token\\n"')
        with self.assertRaisesRegex(ValueError, "MISTRAL_API_KEY") as error:
            runtime_environment({}, self.project, {**self.keys, **loaded})
        self.assertNotIn("private-token", str(error.exception))

    def test_initialization_preserves_existing_file_and_owner_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "configuration.txt"
            initialize_env(path, "MISTRAL_API_KEY=\n")
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text("MISTRAL_API_KEY=existing-test-value\n")
            with self.assertRaises(FileExistsError):
                initialize_env(path, "MISTRAL_API_KEY=\n")
            self.assertEqual(path.read_text(), "MISTRAL_API_KEY=existing-test-value\n")


if __name__ == "__main__":
    unittest.main()
