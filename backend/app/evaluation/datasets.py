"""Labelled benchmark dataset for ARCAS evaluation."""

from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class Sample:
    name: str
    language: str
    code: str
    expected_categories: Set[str] = field(default_factory=set)
    is_safe: bool = False


BENCHMARK: List[Sample] = [
    Sample(
        name="command_injection",
        language="python",
        expected_categories={"command_injection"},
        code=(
            "import subprocess\n"
            "def run(cmd):\n"
            "    return subprocess.call(cmd, shell=True)\n"
        ),
    ),
    Sample(
        name="sql_injection",
        language="python",
        expected_categories={"sql_injection"},
        code=(
            "import sqlite3\n"
            "def get_user(conn, name):\n"
            "    cur = conn.cursor()\n"
            "    cur.execute(\"SELECT * FROM users WHERE name = '\" "
            "+ name + \"'\")\n"
            "    return cur.fetchone()\n"
        ),
    ),
    Sample(
        name="insecure_deserialization",
        language="python",
        expected_categories={"deserialization"},
        code=(
            "import pickle\n"
            "def load(data):\n"
            "    return pickle.loads(data)\n"
        ),
    ),
    Sample(
        name="weak_hash",
        language="python",
        expected_categories={"weak_crypto"},
        code=(
            "import hashlib\n"
            "def digest(password):\n"
            "    return hashlib.md5(password.encode()).hexdigest()\n"
        ),
    ),
    Sample(
        name="hardcoded_secret",
        language="python",
        expected_categories={"hardcoded_secret"},
        code=(
            "API_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"
            "def connect():\n"
            "    return API_KEY\n"
        ),
    ),
    Sample(
        name="code_injection_eval",
        language="python",
        expected_categories={"code_injection"},
        code=(
            "def calculate(expr):\n"
            "    # Directly evaluates attacker-controlled input.\n"
            "    return eval(expr)\n"
        ),
    ),
    Sample(
        name="path_traversal_read",
        language="python",
        expected_categories={"path_traversal"},
        code=(
            "def read_file(filename):\n"
            "    # No sanitisation - '../' lets callers escape the base dir.\n"
            "    with open('/var/data/' + filename) as fh:\n"
            "        return fh.read()\n"
        ),
    ),
    Sample(
        name="reflected_xss",
        language="python",
        expected_categories={"xss"},
        code=(
            "def render_greeting(name):\n"
            "    # Unescaped interpolation into HTML -> reflected XSS.\n"
            "    return '<h1>Hello ' + name + '</h1>'\n"
        ),
    ),
    Sample(
        name="ssrf_fetch",
        language="python",
        expected_categories={"ssrf"},
        code=(
            "import requests\n"
            "def fetch(url):\n"
            "    # Server fetches an attacker-supplied URL -> SSRF.\n"
            "    return requests.get(url).text\n"
        ),
    ),
    Sample(
        name="insecure_token_random",
        language="python",
        expected_categories={"insecure_random"},
        code=(
            "import random\n"
            "def make_token():\n"
            "    # Predictable PRNG used for a security token.\n"
            "    return str(random.random())\n"
        ),
    ),
    Sample(
        name="yaml_unsafe_load",
        language="python",
        expected_categories={"deserialization"},
        code=(
            "import yaml\n"
            "def parse(config):\n"
            "    return yaml.load(config)\n"
        ),
    ),
    Sample(
        name="safe_addition",
        language="python",
        is_safe=True,
        code=(
            "def add(a, b):\n"
            "    \"\"\"Return the sum of two numbers.\"\"\"\n"
            "    return a + b\n"
        ),
    ),
    Sample(
        name="safe_greeting",
        language="python",
        is_safe=True,
        code=(
            "def greet(name):\n"
            "    \"\"\"Return a greeting for the given name.\"\"\"\n"
            "    return f'Hello, {name}!'\n"
        ),
    ),
    Sample(
        name="safe_parameterized_query",
        language="python",
        is_safe=True,
        code=(
            "def find_user(cursor, user_id):\n"
            "    \"\"\"Fetch a user by id using a parameterized query.\"\"\"\n"
            "    cursor.execute(\n"
            "        \"SELECT * FROM users WHERE id = %s\", (user_id,)\n"
            "    )\n"
            "    return cursor.fetchone()\n"
        ),
    ),
]


CATEGORY_KEYWORDS = {
    "command_injection": ["shell", "command", "subprocess", "os-system"],
    "sql_injection": ["sql", "injection", "query"],
    "deserialization": ["pickle", "deserial", "yaml.load", "marshal"],
    "weak_crypto": ["md5", "sha1", "weak", "insecure-hash", "crypto"],
    "hardcoded_secret": ["secret", "hardcoded", "credential", "api-key", "token"],
    "code_injection": ["eval", "exec", "code-injection", "compile"],
    "path_traversal": ["path-traversal", "traversal", "directory", "open-redirect"],
    "xss": ["xss", "cross-site", "innerhtml", "unescaped"],
    "ssrf": ["ssrf", "request-forgery", "url-fetch"],
    "insecure_random": ["random", "insecure-random", "predictable"],
}
