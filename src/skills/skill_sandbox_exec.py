"""Skill: sandbox_exec — Execute LLM-generated Python code in a safe sandbox.

Uses AST validation to block dangerous operations, restricted builtins,
a thread-based timeout, and emits SocketIO skill_status events so the
web UI never waits forever for a callback.

The heartbeat system (module_heartbeat) is used as a watchdog: if the
sandbox doesn't complete within the timeout, the heartbeat fires and
emits a failure status to the UI.
"""

import ast
import sys
import threading
import io
import traceback
from datetime import datetime

SKILL = {
    "name": "sandbox_exec",
    "required_params": ["code"],
    "followup": True,
    "description": "Execute Python code in a sandboxed environment",
    "prompt": """sandbox_exec
   Triggers: When you need to execute Python code to answer the user's question. Use this for:
     * Mathematical calculations, data processing, or logic that benefits from real computation
     * Generating, transforming, or analyzing data structures (lists, dicts, JSON)
     * Any task where writing and running code is more accurate than reasoning alone
     * Creating reusable utility functions or one-off scripts
   Parameters:
     {{"code": "<python code string>", "description": "<brief description of what the code does>"}}
   CRITICAL: The code runs in a restricted sandbox. Only safe builtins and whitelisted modules are available.
   CRITICAL: Use print() to produce output. Set a variable named 'result' for structured return values.
   Available modules: math, random, json, datetime, collections, itertools, functools, re, string, hashlib, base64, statistics
   NOT available: os, sys, subprocess, socket, requests, file I/O, network access
   Timeout: Code must complete within 10 seconds.
   Example: {{"function": "sandbox_exec", "parameters": {{"code": "import math\\nresult = math.factorial(20)\\nprint(f'20! = {{result}}')", "description": "calculate 20 factorial"}}}}""",
    "examples": [
        """Example - code execution:
User: "What's the sum of all prime numbers under 100?"
Response: {{"reply": "Let me calculate that for you.", "function_calls": [{{"function": "sandbox_exec", "parameters": {{"code": "def is_prime(n):\\n    if n < 2: return False\\n    for i in range(2, int(n**0.5)+1):\\n        if n % i == 0: return False\\n    return True\\nprimes = [n for n in range(100) if is_prime(n)]\\nresult = sum(primes)\\nprint(f'Primes under 100: {{primes}}')\\nprint(f'Sum: {{result}}')", "description": "sum primes under 100"}}}}], "new_memories": []}}""",
        """Example - data transformation:
User: "Sort these names by length: Alice, Bob, Christopher, Di, Elizabeth"
Response: {{"reply": "Let me sort those for you.", "function_calls": [{{"function": "sandbox_exec", "parameters": {{"code": "names = ['Alice', 'Bob', 'Christopher', 'Di', 'Elizabeth']\\nsorted_names = sorted(names, key=len)\\nresult = ', '.join(sorted_names)\\nprint(f'Sorted by length: {{result}}')", "description": "sort names by length"}}}}], "new_memories": []}}""",
    ],
    "order": 50,
}

# ── Configuration ──────────────────────────────────────────────────────────────

_TIMEOUT_SECONDS = 10
_MAX_OUTPUT_CHARS = 2000
_HEARTBEAT_PREFIX = "sandbox_"

# Modules the sandbox is allowed to import
_ALLOWED_MODULES = frozenset({
    "math", "random", "json", "datetime", "collections",
    "itertools", "functools", "re", "string", "hashlib",
    "base64", "statistics", "decimal", "fractions",
    "textwrap", "operator", "copy",
})

# Builtins exposed to sandbox code
_SAFE_BUILTIN_NAMES = frozenset({
    "abs", "all", "any", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "dir", "divmod",
    "enumerate", "filter", "float", "format", "frozenset",
    "hash", "hex", "id", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next",
    "object", "oct", "ord", "pow", "print", "range",
    "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "zip",
    "True", "False", "None",
})

# AST node names that are forbidden
_FORBIDDEN_NAMES = frozenset({
    "exec", "eval", "compile", "__import__", "open",
    "breakpoint", "exit", "quit", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "memoryview", "super",
})

_FORBIDDEN_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "signal", "ctypes",
    "socket", "http", "urllib", "requests", "ftplib", "smtplib",
    "pickle", "shelve", "marshal", "importlib", "runpy",
    "code", "codeop", "compileall", "py_compile",
    "multiprocessing", "threading", "asyncio", "_thread",
    "gc", "inspect", "builtins", "__builtin__",
    "io", "tempfile", "pathlib", "glob", "fnmatch",
    "webbrowser", "antigravity", "turtle",
})


# ── AST Safety Validator ──────────────────────────────────────────────────────

class _SafetyError(Exception):
    pass


def _validate_ast(code_str):
    """Parse and validate code AST. Raises _SafetyError if unsafe."""
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise _SafetyError(f"Syntax error: {e}")

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                if mod in _FORBIDDEN_MODULES:
                    raise _SafetyError(f"Forbidden import: {mod}")
                if mod not in _ALLOWED_MODULES:
                    raise _SafetyError(f"Module not whitelisted: {mod}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split('.')[0]
                if mod in _FORBIDDEN_MODULES:
                    raise _SafetyError(f"Forbidden import: {mod}")
                if mod not in _ALLOWED_MODULES:
                    raise _SafetyError(f"Module not whitelisted: {mod}")

        # Check function calls by name
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
                raise _SafetyError(f"Forbidden function: {func.id}")
            elif isinstance(func, ast.Attribute):
                if func.attr in ("system", "popen", "exec", "eval", "remove",
                                 "rmdir", "unlink", "write", "read"):
                    # Check if it's on a forbidden module
                    if isinstance(func.value, ast.Name) and func.value.id in _FORBIDDEN_MODULES:
                        raise _SafetyError(f"Forbidden call: {func.value.id}.{func.attr}")

        # Check name access for dunder attributes
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith('__') and node.attr.endswith('__'):
                if node.attr not in ('__name__', '__doc__', '__class__'):
                    raise _SafetyError(f"Forbidden dunder access: {node.attr}")

        # Check name references
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                raise _SafetyError(f"Forbidden name: {node.id}")

    return tree


# ── Sandbox Environment ───────────────────────────────────────────────────────

def _create_safe_builtins():
    """Build a dict of safe builtins for the sandbox."""
    import builtins
    safe = {}
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    # Add a restricted __import__ that only allows whitelisted modules
    def safe_import(name, *args, **kwargs):
        mod = name.split('.')[0]
        if mod in _FORBIDDEN_MODULES:
            raise ImportError(f"Import blocked: {name}")
        if mod not in _ALLOWED_MODULES:
            raise ImportError(f"Module not available in sandbox: {name}")
        return __builtins__.__import__(name, *args, **kwargs) if hasattr(__builtins__, '__import__') else __import__(name, *args, **kwargs)
    safe['__import__'] = safe_import
    safe['__name__'] = '__sandbox__'
    safe['__builtins__'] = safe
    return safe


def _run_code_in_thread(code_str, result_holder):
    """Execute code in a restricted namespace, capturing output."""
    stdout_capture = io.StringIO()
    safe_builtins = _create_safe_builtins()
    # Override print to capture to our StringIO
    safe_builtins['print'] = lambda *args, **kwargs: print(*args, file=stdout_capture, **kwargs)

    namespace = {'__builtins__': safe_builtins}

    try:
        compiled = compile(code_str, '<sandbox>', 'exec')
        exec(compiled, namespace)

        output = stdout_capture.getvalue()
        # Check for 'result' variable
        sandbox_result = namespace.get('result', None)

        if sandbox_result is not None and not output.strip():
            output = str(sandbox_result)
        elif sandbox_result is not None:
            output = f"{output.rstrip()}\nResult: {sandbox_result}"

        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n...[output truncated]"

        result_holder['output'] = output.strip() if output.strip() else "(code executed successfully, no output)"
        result_holder['success'] = True

    except Exception as e:
        tb = traceback.format_exc()
        # Only show the relevant part of the traceback
        lines = tb.split('\n')
        relevant = [l for l in lines if '<sandbox>' in l or not l.startswith('  File')]
        result_holder['output'] = f"Error: {e}"
        result_holder['success'] = False
    finally:
        stdout_capture.close()


# ── Status Emission ───────────────────────────────────────────────────────────

def _emit_status(status, description="", output=""):
    """Emit skill execution status to the web UI via SocketIO."""
    try:
        from modules.module_chatui import socketio
        socketio.emit('skill_status', {
            'skill': 'sandbox_exec',
            'status': status,  # 'running', 'completed', 'failed', 'timeout'
            'description': description,
            'output': output[:500] if output else "",
            'timestamp': datetime.now().strftime("%H:%M:%S"),
        })
    except Exception:
        pass


# ── Main Execute ──────────────────────────────────────────────────────────────

def execute(parameters, context):
    """Execute sandboxed Python code with timeout and heartbeat watchdog."""
    from modules.module_messageQue import queue_message

    code = parameters.get("code", "")
    description = parameters.get("description", "execute code")

    if not code or not code.strip():
        return "No code provided to execute."

    # Unescape common escape sequences from JSON
    code = code.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')

    queue_message(f"SANDBOX: Executing — {description}")
    _emit_status('running', description)

    # Step 1: AST validation
    try:
        _validate_ast(code)
    except _SafetyError as e:
        msg = f"Code rejected for safety: {e}"
        queue_message(f"SANDBOX: {msg}")
        _emit_status('failed', description, msg)
        return msg

    # Step 2: Set up heartbeat watchdog
    # If the sandbox thread hangs, the heartbeat fires and emits a timeout status
    task_id = f"{_HEARTBEAT_PREFIX}{id(code)}_{threading.current_thread().ident}"
    watchdog_fired = threading.Event()

    def _watchdog_timeout():
        """Called by heartbeat if sandbox exceeds timeout."""
        watchdog_fired.set()
        queue_message(f"SANDBOX: TIMEOUT after {_TIMEOUT_SECONDS}s — {description}")
        _emit_status('timeout', description, f"Execution exceeded {_TIMEOUT_SECONDS}s limit")

    try:
        from modules.module_heartbeat import schedule_once, cancel_task
        schedule_once(
            task_id=task_id,
            delay_seconds=_TIMEOUT_SECONDS + 1,  # +1s grace for thread join
            callback=_watchdog_timeout,
        )
    except Exception:
        pass  # Heartbeat not available — still use thread timeout

    # Step 3: Run code in a daemon thread with timeout
    result_holder = {'output': '', 'success': False}
    exec_thread = threading.Thread(
        target=_run_code_in_thread,
        args=(code, result_holder),
        daemon=True,
    )
    exec_thread.start()
    exec_thread.join(timeout=_TIMEOUT_SECONDS)

    # Step 4: Cancel heartbeat watchdog (sandbox finished or timed out)
    try:
        from modules.module_heartbeat import cancel_task
        cancel_task(task_id)
    except Exception:
        pass

    # Step 5: Handle results
    if exec_thread.is_alive() or watchdog_fired.is_set():
        msg = f"Code execution timed out after {_TIMEOUT_SECONDS} seconds."
        queue_message(f"SANDBOX: {msg}")
        _emit_status('timeout', description, msg)
        return msg

    output = result_holder.get('output', '')
    success = result_holder.get('success', False)

    if success:
        queue_message(f"SANDBOX: Success — {output[:200]}")
        _emit_status('completed', description, output)
        return f"Code output:\n{output}"
    else:
        queue_message(f"SANDBOX: Failed — {output[:200]}")
        _emit_status('failed', description, output)
        return f"Code execution error: {output}"
