"""Static inventory of committed V03 sources. Never imports application modules."""
import argparse
import ast
from collections import Counter, defaultdict
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parent
PRIVATE_DIRS = frozenset(('donnees', 'archives', 'backups', 'secrets', 'credentials',
                          '__pycache__', '.git', '.venv', 'venv', 'node_modules'))
PRIVATE_NAMES = frozenset(('config.json', 'preparation.json', 'credentials.json'))
PRIVATE_SUFFIXES = frozenset(('.sqlite', '.sqlite3', '.db', '.pem', '.key', '.pfx',
                              '.p12', '.dpapi', '.pyc'))
MAX_PYTHON_BYTES = 2_000_000


def git(cwd, *args):
    # A committed snapshot, not working-tree contents. No network commands.
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
               GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output(['git', *args], cwd=cwd, env=env)


def private(path):
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    name = parts[-1]
    return (any(p in PRIVATE_DIRS or p.startswith(('.env', '.git', '.aes-')) for p in parts)
            or name in PRIVATE_NAMES or PurePosixPath(name).suffix in PRIVATE_SUFFIXES)


def category(path):
    p = PurePosixPath(path)
    if p.suffix != '.py':
        return 'asset'
    if ('tests' in p.parts[:-1] or p.name.startswith(('test_', 'smoke_'))):
        return 'test'
    if p.name.startswith(('build_', 'apply_', 'prepare_')) or p.name == 'audit_repository.py':
        return 'tooling'
    return 'runtime'


def module_name(path):
    p = PurePosixPath(path)
    parts = list(p.parts[:-1])
    if p.name != '__init__.py':
        parts.append(p.stem)
    if not parts or not all(x.isidentifier() for x in parts):
        return None
    return '.'.join(parts)


class Imports(ast.NodeVisitor):
    def __init__(self):
        self.depth = 0
        self.records = []
        self.dynamic_calls = []

    def visit_FunctionDef(self, node):
        # Defaults/decorators/annotations contain expressions, not import statements.
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef

    def visit_Import(self, node):
        for alias in node.names:
            self.records.append((alias.name, (), 0, node.lineno, self.depth > 0))

    def visit_ImportFrom(self, node):
        self.records.append((node.module or '', tuple(x.name for x in node.names),
                             node.level, node.lineno, self.depth > 0))

    def visit_Call(self, node):
        fn = node.func
        if (isinstance(fn, ast.Name) and fn.id in ('__import__', 'import_module')
                or isinstance(fn, ast.Attribute) and fn.attr == 'import_module'):
            self.dynamic_calls.append(node.lineno)
        self.generic_visit(node)


def import_targets(source, is_package, name, symbols, level, modules):
    if level:
        package = source.split('.') if is_package else source.split('.')[:-1]
        if level > len(package):
            return set()
        prefix = package[:len(package) - level + 1]
        name = '.'.join(prefix + ([name] if name else []))
    candidates = {name} if name else set()
    # from pkg import child may load the child module as well as the package.
    candidates.update(name + '.' + x for x in symbols if name and x != '*')
    return (candidates & modules) - {source}


def cyclic_groups(nodes, edges):
    """Strongly connected components; only components with >=2 modules."""
    graph = {n: set() for n in nodes}
    for a, b in edges:
        if a in graph and b in graph:
            graph[a].add(b)
    index = {}
    low = {}
    stack = []
    active = set()
    groups = []

    def visit(node):
        index[node] = low[node] = len(index)
        stack.append(node)
        active.add(node)
        for other in sorted(graph[node]):
            if other not in index:
                visit(other)
                low[node] = min(low[node], low[other])
            elif other in active:
                low[node] = min(low[node], index[other])
        if low[node] == index[node]:
            group = []
            while True:
                other = stack.pop()
                active.remove(other)
                group.append(other)
                if other == node:
                    break
            if len(group) > 1:
                groups.append(sorted(group))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return sorted(groups)


def audit(root=ROOT, revision='HEAD'):
    root = Path(root)
    prefix = git(root, 'rev-parse', '--show-prefix').decode().strip()
    repo = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel').rstrip(b'\r\n')))
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options',
                 revision + '^{commit}').decode().strip()
    raw = git(repo, 'ls-tree', '-r', '-l', '-z', commit, '--', prefix or '.')
    inventory, skipped = [], []
    private_count = 0
    parsed = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        meta, path = record.split(b'\t', 1)
        mode, kind, oid, size = meta.decode().split()
        path = os.fsdecode(path)
        if prefix and not path.startswith(prefix):
            raise ValueError('Unexpected Git tree path')
        rel = path[len(prefix):]
        if private(rel):
            private_count += 1
            continue
        row = {'path': rel, 'kind': category(rel), 'mode': mode,
               'bytes': int(size) if size != '-' else None}
        inventory.append(row)
        if row['kind'] == 'asset':
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            skipped.append({'path': rel, 'reason': 'non_regular_python'})
            continue
        if row['bytes'] is None or row['bytes'] > MAX_PYTHON_BYTES:
            skipped.append({'path': rel, 'reason': 'size_limit'})
            continue
        module = module_name(rel)
        if module is None:
            skipped.append({'path': rel, 'reason': 'not_importable_path'})
            continue
        data = git(repo, 'cat-file', 'blob', oid)
        try:
            tree = ast.parse(data, filename=rel)
        except (SyntaxError, ValueError) as error:
            skipped.append({'path': rel, 'reason': 'parse_error',
                            'line': getattr(error, 'lineno', None)})
            continue
        visitor = Imports()
        visitor.visit(tree)
        row['module'] = module
        row['lines'] = len(data.splitlines())
        row['imports'] = len(visitor.records)
        row['dynamic_import_hints'] = sorted(set(visitor.dynamic_calls))
        parsed[rel] = (row, visitor.records)

    by_module = defaultdict(list)
    for path, (row, _) in parsed.items():
        by_module[row['module']].append(path)
    ambiguous = {m: sorted(paths) for m, paths in by_module.items() if len(paths) > 1}
    known = set(by_module) - set(ambiguous)
    runtime = {row['module'] for row, _ in parsed.values()
               if row['kind'] == 'runtime' and row['module'] in known}
    edges = defaultdict(set)
    unresolved = []
    for path, (row, records) in parsed.items():
        source = row['module']
        if source not in known:
            continue
        for name, symbols, level, line, deferred in records:
            scope = 'deferred' if deferred else 'module_scope'
            targets = import_targets(source, PurePosixPath(path).name == '__init__.py',
                                     name, symbols, level, known)
            for target in targets:
                edges[(source, target)].add((scope, line))
            if not targets:
                # External/stdlib, unresolved or self-only imports are not guessed.
                unresolved.append({'source': source, 'line': line,
                                   'scope': scope, 'relative': bool(level)})
    dependencies = [{'source': a, 'target': b,
                     'references': [{'scope': scope, 'line': line}
                                    for scope, line in sorted(refs)]}
                    for (a, b), refs in sorted(edges.items())]
    module_edges = [(a, b) for (a, b), refs in edges.items()
                    if any(scope == 'module_scope' for scope, _ in refs)]
    return {
        'schema_version': 1, 'commit': commit, 'scope': prefix or '.',
        'counts': dict(sorted(Counter(row['kind'] for row in inventory).items())),
        'excluded_private_paths': private_count,
        'parsed_python': len(parsed), 'runtime_modules': len(runtime),
        'files': sorted(inventory, key=lambda r: r['path']),
        'skipped_python': sorted(skipped, key=lambda r: r['path']),
        'ambiguous_modules': ambiguous, 'dependencies': dependencies,
        'unresolved_or_external_imports': sorted(unresolved, key=lambda r: (r['source'], r['line'], r['scope'])),
        'runtime_cycles_all_scopes': cyclic_groups(runtime, edges),
        'runtime_cycles_module_scope': cyclic_groups(runtime, module_edges),
        'limitations': [
            'Committed Git blobs only; working-tree and ignored files are not inspected.',
            'Static Python imports only; dynamic imports are hints, not resolved.',
            'Module-scope imports can be conditional; cycles are not proof of failure.',
            'Exact local module resolution; implicit package loading, aliases and sys.path changes are not inferred.',
            'Private path exclusions are name-based, not a secret scanner.',
            'No JavaScript dependency analysis, dead-code proof or coverage measurement.'
        ]
    }


def summary(report):
    return {k: report[k] for k in ('commit', 'scope', 'counts', 'excluded_private_paths',
                                  'parsed_python', 'runtime_modules', 'skipped_python',
                                  'ambiguous_modules', 'runtime_cycles_all_scopes',
                                  'runtime_cycles_module_scope')} | {
        'dependency_pairs': len(report['dependencies']),
        'unresolved_or_external_imports': len(report['unresolved_or_external_imports']),
        'dynamic_import_hint_files': sum(bool(r.get('dynamic_import_hints')) for r in report['files'])
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--output', type=Path, help='New JSON file; refuses overwrite')
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()
    report = audit(revision=args.revision)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=True, sort_keys=True)
            stream.write('\n')
    print(json.dumps(summary(report) if args.summary else report, indent=2,
                     ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
