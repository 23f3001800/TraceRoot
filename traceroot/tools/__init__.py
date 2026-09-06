from .reproduction import run_reproduction
from .logs import read_logs
from .code_search import search_code
from .file_reader import read_file
from .database import inspect_database
from .tests import run_tests

TOOLS = {fn.__name__: fn for fn in (
    run_reproduction, read_logs, search_code, read_file, inspect_database, run_tests,
)}
